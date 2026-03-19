"""Rule-based prefilter for candidate tweet selection."""
from __future__ import annotations

import re
from typing import Any

TICKER_RE = re.compile(r"\$[A-Z]{2,10}\b")


def _to_int(value: Any, default: int = 0) -> int:
    """Convert a value to int safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def should_keep_tweet(tweet: dict[str, Any], config: dict[str, Any]) -> bool:
    """Return True when a tweet passes hard-rule candidate filters."""
    filters = config["filters"]
    engagement = filters["engagement"]
    text = f"{tweet.get('text', '')} {tweet.get('quoted_text', '')}".lower()
    author = str(tweet.get("author") or "").lower()
    likes = _to_int(tweet.get("like_count"))
    retweets = _to_int(tweet.get("retweet_count"))
    followers = _to_int(tweet.get("author_followers"))

    if likes >= engagement["high_likes"] or retweets >= engagement["high_retweets"]:
        return True
    if author in {item.lower() for item in filters.get("big_accounts", [])}:
        return True
    if followers >= engagement["follower_floor"]:
        return True
    if any(keyword.lower() in text for keyword in filters["keywords"]["must"]):
        return True
    if any(keyword.lower() in text for keyword in filters["keywords"]["interest"]):
        return True
    if likes >= engagement["soft_likes_with_ticker"] and TICKER_RE.search(tweet.get("text", "")):
        return True
    if likes >= engagement["soft_likes_with_followers"] and followers >= engagement["soft_followers"]:
        return True
    return False


def filter_candidates(tweets: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter raw tweets into the candidate pool."""
    return [tweet for tweet in tweets if should_keep_tweet(tweet, config)]
