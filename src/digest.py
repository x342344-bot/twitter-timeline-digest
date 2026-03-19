"""AI digest generation entrypoint."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


def load_prompt(path: Path) -> str:
    """Load the digest prompt template from disk."""
    return path.read_text(encoding="utf-8")


def build_payload(tweets: list[dict[str, Any]], buzz: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Build a compact LLM payload from scored tweets and buzz clusters."""
    trimmed = []
    for tweet in tweets[:limit]:
        trimmed.append({
            "id": tweet.get("id"),
            "author": tweet.get("author"),
            "text": tweet.get("text"),
            "quoted_text": tweet.get("quoted_text"),
            "likes": tweet.get("like_count"),
            "retweets": tweet.get("retweet_count"),
            "followers": tweet.get("author_followers"),
            "score": tweet.get("score"),
            "event_key": tweet.get("event_key"),
            "source": tweet.get("source"),
        })
    return [{"tweets": trimmed, "buzz": buzz}]


def call_openai(api_key: str, model: str, prompt: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the OpenAI Responses API and parse JSON output."""
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}]},
            ],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    output_text = data.get("output", [{}])[0].get("content", [{}])[0].get("text")
    if not output_text:
        raise ValueError("OpenAI returned no text payload")
    return json.loads(output_text)


def call_anthropic(api_key: str, model: str, prompt: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the Anthropic Messages API and parse JSON output."""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4000,
            "system": prompt,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("content", [])
    text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    if not text:
        raise ValueError("Anthropic returned no text payload")
    return json.loads(text)


def generate_digest(tweets: list[dict[str, Any]], buzz: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Generate a digest using the configured LLM provider."""
    digest_config = config["digest"]
    prompt = load_prompt(Path(digest_config["prompt_path"]))
    payload = build_payload(tweets, buzz, limit=max(int(digest_config["output_count"]) * 6, 50))
    provider = str(digest_config["provider"]).lower()
    if provider == "openai":
        import os
        api_key = os.environ.get(digest_config["api_key_env"], "")
        if not api_key:
            raise ValueError(f"Missing environment variable: {digest_config['api_key_env']}")
        return call_openai(api_key, digest_config["model"], prompt, payload)
    if provider == "anthropic":
        import os
        api_key = os.environ.get(digest_config["anthropic_api_key_env"], "")
        if not api_key:
            raise ValueError(f"Missing environment variable: {digest_config['anthropic_api_key_env']}")
        return call_anthropic(api_key, digest_config["model"], prompt, payload)
    raise ValueError(f"Unsupported digest provider: {provider}")
