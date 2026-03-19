"""Fetch Following and For You timelines from an authenticated X/Twitter tab via CDP."""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import websocket
import yaml

from src.prefilter import filter_candidates
from src.storage import cleanup_old_files, save_candidates, save_raw_tweets

LOGGER = logging.getLogger(__name__)
DEFAULT_FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration from disk."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def cdp_ws_url(config: dict[str, Any]) -> str:
    """Build the target WebSocket URL from config."""
    cdp = config["cdp"]
    return f"ws://{cdp['host']}:{cdp['port']}/devtools/page/{cdp['target_id']}"


def build_graphql_endpoint(config: dict[str, Any], feed: str) -> str:
    """Build a GraphQL endpoint path for the requested feed."""
    graphql = config["twitter"]["graphql"]
    if feed == "following":
        return f"{graphql['following_query_id']}/{graphql['following_operation']}"
    if feed == "for_you":
        return f"{graphql['for_you_query_id']}/{graphql['for_you_operation']}"
    raise ValueError(f"Unknown feed: {feed}")


def build_fetch_js(config: dict[str, Any], feed: str, *, cursor: str | None = None, count: int | None = None) -> str:
    """Build injected JavaScript that fetches a timeline GraphQL endpoint in-page."""
    endpoint = build_graphql_endpoint(config, feed)
    page_size = count or int(config["twitter"]["page_size"])
    features = json.dumps(DEFAULT_FEATURES, separators=(",", ":"))
    variables = {
        "count": page_size,
        "includePromotedContent": False,
        "latestControlAvailable": True,
        "requestContext": "launch",
    }
    if cursor:
        variables["cursor"] = cursor
    variables_json = json.dumps(variables, separators=(",", ":"))
    bearer_env = config["twitter"]["bearer_token_env"]
    return f"""
(async function() {{
  const bearer = globalThis.__OPEN_SOURCE_BEARER || null;
  if (!bearer) {{
    return JSON.stringify({{ error: 'missing_bearer_token', env: '{bearer_env}' }});
  }}
  const csrfMatch = document.cookie.match(/(?:^|;\\s*)ct0=([^;]+)/);
  if (!csrfMatch) {{
    return JSON.stringify({{ error: 'missing_ct0_cookie' }});
  }}
  const variables = {json.dumps(variables_json)};
  const features = {json.dumps(features)};
  const url = `https://x.com/i/api/graphql/{endpoint}?variables=${{encodeURIComponent(variables)}}&features=${{encodeURIComponent(features)}}`;
  const response = await fetch(url, {{
    credentials: 'include',
    headers: {{
      'authorization': bearer,
      'x-csrf-token': csrfMatch[1],
      'x-twitter-auth-type': 'OAuth2Session',
      'x-twitter-active-user': 'yes'
    }}
  }});
  if (!response.ok) {{
    return JSON.stringify({{ error: `http_${{response.status}}` }});
  }}
  const payload = await response.json();
  const instructions = payload?.data?.home?.home_timeline_urt?.instructions || [];
  const entries = instructions.flatMap(item => item?.entries || []);
  const tweets = [];
  let nextCursor = null;
  for (const entry of entries) {{
    if (entry?.content?.cursorType === 'Bottom') {{
      nextCursor = entry?.content?.value || nextCursor;
      continue;
    }}
    const result = entry?.content?.itemContent?.tweet_results?.result;
    if (!result) continue;
    const tweetNode = result.__typename === 'TweetWithVisibilityResults' ? result.tweet : result;
    const legacy = tweetNode?.legacy;
    const userNode = tweetNode?.core?.user_results?.result;
    const userLegacy = userNode?.legacy;
    if (!legacy || !userLegacy) continue;
    let quotedText = null;
    let quotedAuthor = null;
    if (legacy.is_quote_status && tweetNode?.quoted_status_result?.result) {{
      const quotedResult = tweetNode.quoted_status_result.result;
      const quotedNode = quotedResult.__typename === 'TweetWithVisibilityResults' ? quotedResult.tweet : quotedResult;
      quotedText = quotedNode?.legacy?.full_text || null;
      quotedAuthor = quotedNode?.core?.user_results?.result?.legacy?.screen_name || null;
    }}
    tweets.push({{
      id: legacy.id_str || tweetNode?.rest_id,
      text: legacy.full_text || '',
      author: userLegacy.screen_name || '',
      author_name: userLegacy.name || '',
      author_followers: userLegacy.followers_count || 0,
      created_at: legacy.created_at || '',
      like_count: legacy.favorite_count || 0,
      retweet_count: legacy.retweet_count || 0,
      reply_count: legacy.reply_count || 0,
      quoted_text: quotedText,
      quoted_author: quotedAuthor,
      lang: legacy.lang || '',
      source: '{feed}',
      url: `https://x.com/${{userLegacy.screen_name || ''}}/status/${{legacy.id_str || tweetNode?.rest_id || ''}}`
    }});
  }}
  return JSON.stringify({{ tweets, cursor: nextCursor, feed: '{feed}' }});
}})()
"""


def build_set_bearer_js(token: str) -> str:
    """Build JavaScript that exposes the bearer token on the page context."""
    return "globalThis.__OPEN_SOURCE_BEARER = " + json.dumps(f"Bearer {token}") + "; 'ok';"


def send_cdp_command(ws: websocket.WebSocket, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send a CDP command and return the response payload."""
    command = {"id": int(time.time() * 1000) % 1000000, "method": method, "params": params}
    ws.send(json.dumps(command))
    while True:
        raw = ws.recv()
        payload = json.loads(raw)
        if payload.get("id") == command["id"]:
            return payload


def evaluate_js(ws: websocket.WebSocket, expression: str) -> Any:
    """Evaluate JavaScript in the active page via Runtime.evaluate."""
    response = send_cdp_command(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": True, "returnByValue": True},
    )
    if "error" in response:
        raise RuntimeError(str(response["error"]))
    result = response.get("result", {}).get("result", {})
    if "value" in result:
        return result["value"]
    raise RuntimeError(f"Unexpected CDP evaluate response: {response}")


def fetch_page(url: str) -> list[dict[str, Any]]:
    """Fetch JSON from an HTTP endpoint."""
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_target_id(config: dict[str, Any]) -> str:
    """Resolve the CDP target ID from /json/list when not explicitly configured."""
    target_id = str(config["cdp"].get("target_id") or "").strip()
    if target_id:
        return target_id
    cdp = config["cdp"]
    targets = fetch_page(f"http://{cdp['host']}:{cdp['port']}/json/list")
    for target in targets:
        url = str(target.get("url") or "")
        if "x.com/home" in url or "twitter.com/home" in url:
            return str(target["id"])
    raise ValueError("Could not auto-detect a logged-in x.com home tab; set cdp.target_id explicitly.")


def fetch_feed(ws: websocket.WebSocket, config: dict[str, Any], feed: str, *, rounds: int = 1) -> list[dict[str, Any]]:
    """Fetch one feed, following pagination cursors across rounds."""
    cursor: str | None = None
    all_tweets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for _ in range(rounds):
        payload = evaluate_js(ws, build_fetch_js(config, feed, cursor=cursor))
        data = json.loads(payload)
        if data.get("error"):
            raise RuntimeError(f"{feed} fetch failed: {data['error']}")
        for tweet in data.get("tweets", []):
            tweet_id = str(tweet.get("id") or "")
            if tweet_id and tweet_id not in seen_ids:
                all_tweets.append(tweet)
                seen_ids.add(tweet_id)
        cursor = data.get("cursor")
        if not cursor:
            break
        if feed == "for_you":
            evaluate_js(ws, "window.scrollTo(0, document.body.scrollHeight); 'ok';")
            time.sleep(1.5)
    return all_tweets


def run_fetch(config_path: Path) -> dict[str, Any]:
    """Run a single fetch cycle and return summary stats."""
    import os
    config = load_config(config_path)
    token = os.environ.get(config["twitter"]["bearer_token_env"], "")
    if not token:
        raise ValueError(f"Missing environment variable: {config['twitter']['bearer_token_env']}")
    config["cdp"]["target_id"] = resolve_target_id(config)
    data_dir = Path(config["storage"]["data_dir"])
    ws = websocket.create_connection(cdp_ws_url(config), timeout=30)
    try:
        evaluate_js(ws, build_set_bearer_js(token))
        following = fetch_feed(ws, config, "following", rounds=1)
        for_you = fetch_feed(ws, config, "for_you", rounds=int(config["twitter"]["for_you_scroll_rounds"]))
    finally:
        ws.close()
    raw = following + for_you
    # Cross-feed dedup: if same tweet appears in both feeds, keep the "following" version
    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    # Following first so it takes priority
    for tweet in following:
        tid = str(tweet.get("id") or "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            deduped.append(tweet)
    for tweet in for_you:
        tid = str(tweet.get("id") or "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            deduped.append(tweet)
    raw = deduped
    candidates = filter_candidates(raw, config)
    cleanup_old_files(data_dir, retention_days=int(config["storage"]["retention_days"]))
    raw_total = save_raw_tweets(data_dir, raw)
    candidate_total = save_candidates(data_dir, candidates)
    summary = {
        "status": "ok",
        "following": len(following),
        "for_you": len(for_you),
        "raw_saved": raw_total,
        "candidate_saved": candidate_total,
        "new_raw": len(raw),
        "new_candidates": len(candidates),
    }
    LOGGER.info("Fetch summary: %s", summary)
    return summary
