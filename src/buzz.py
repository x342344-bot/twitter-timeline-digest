"""Buzz aggregation across authors and entities."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

HANDLE_RE = re.compile(r"@(\w+)")
CASHTAG_RE = re.compile(r"\$([A-Z]{2,10})\b")


def extract_entities(tweet: dict[str, Any]) -> set[str]:
    """Extract handles and cashtags from a tweet."""
    text = f"{tweet.get('text', '')} {tweet.get('quoted_text', '')}"
    handles = {f"@{match.lower()}" for match in HANDLE_RE.findall(text)}
    cashtags = {f"${match.upper()}" for match in CASHTAG_RE.findall(text)}
    return handles | cashtags


def aggregate_buzz(tweets: list[dict[str, Any]], *, min_authors: int) -> list[dict[str, Any]]:
    """Aggregate entities mentioned by multiple authors."""
    by_entity: dict[str, set[str]] = defaultdict(set)
    tweet_ids: dict[str, list[str]] = defaultdict(list)
    for tweet in tweets:
        author = str(tweet.get("author") or "").lower()
        entities = extract_entities(tweet)
        for entity in entities:
            if author:
                by_entity[entity].add(author)
            if tweet.get("id"):
                tweet_ids[entity].append(str(tweet["id"]))
    results: list[dict[str, Any]] = []
    for entity, authors in by_entity.items():
        if len(authors) < min_authors:
            continue
        results.append({
            "entity": entity,
            "authors": sorted(authors),
            "author_count": len(authors),
            "tweet_ids": sorted(set(tweet_ids[entity])),
        })
    results.sort(key=lambda item: (item["author_count"], item["entity"]), reverse=True)
    return results
