"""Event-level deduplication helpers."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at", "by", "with", "from",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "will", "would", "can", "could",
    "rt", "amp", "http", "https", "com", "www", "x", "twitter", "status"
}


def normalize_event_text(text: str) -> str:
    """Normalize tweet text for event fingerprinting."""
    normalized = (text or "").lower()
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[@#]\w+", " ", normalized)
    normalized = re.sub(r"\$[a-zA-Z]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def event_fingerprint(tweet: dict[str, Any]) -> str:
    """Build a loose event key so the same event clusters across authors."""
    text = normalize_event_text(f"{tweet.get('text', '')} {tweet.get('quoted_text', '')}")
    words = [word for word in re.findall(r"\b\w+\b", text) if len(word) >= 3 and word not in STOPWORDS and not word.isdigit()]
    if not words:
        return ""
    counts = Counter(words)
    top_words = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    return "|".join(word for word, _ in top_words)


def deduplicate_events(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest tweet per event key."""
    best_by_event: dict[str, dict[str, Any]] = {}
    fallback: list[dict[str, Any]] = []
    for tweet in tweets:
        item = dict(tweet)
        event_key = event_fingerprint(item)
        item["event_key"] = event_key
        if not event_key:
            fallback.append(item)
            continue
        existing = best_by_event.get(event_key)
        current_score = float(item.get("score") or 0)
        existing_score = float(existing.get("score") or 0) if existing else -1.0
        if existing is None or current_score > existing_score:
            best_by_event[event_key] = item
    return list(best_by_event.values()) + fallback


def build_mention_counts(tweets: list[dict[str, Any]]) -> dict[str, int]:
    """Count how many tweets map to each event key."""
    counts: Counter[str] = Counter()
    for tweet in tweets:
        key = event_fingerprint(tweet)
        if key:
            counts[key] += 1
    return dict(counts)
