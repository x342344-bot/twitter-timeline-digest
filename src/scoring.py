"""Ranking logic for candidate tweets."""
from __future__ import annotations

import math
import re
from typing import Any

CRYPTO_RE = re.compile(r"btc|bitcoin|eth|ethereum|sol|solana|defi|airdrop|token|crypto|onchain|stablecoin|l2|rollup", re.I)
ALPHA_RE = re.compile(r"alpha|launch|launchpool|tge|funding round|hack|exploit|listing|bridge|wallet|staking|yield|points", re.I)
ETF_FLOW_RE = re.compile(r"etf|net inflow|net outflow|blackrock|grayscale|ibit|fbtc", re.I)
PAYMENT_WALLET_RE = re.compile(r"wallet|payment|payments|stablecoin|usdc|usdt|stripe|payfi", re.I)
COMPLIANCE_RE = re.compile(r"sec|cftc|compliance|kyc|aml|license|tax|regulation", re.I)
SECURITY_RE = re.compile(r"hack|hacked|exploit|breach|attack|drain|stolen|phishing", re.I)
CASHTAG_RE = re.compile(r"\$([A-Z]{2,10})\b")
COMMON_STOCKS = {"AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "SPY", "QQQ", "USD"}


def tweet_text(tweet: dict[str, Any]) -> str:
    """Return combined tweet text including quoted content."""
    return " ".join(part.strip() for part in [tweet.get("text", ""), tweet.get("quoted_text", "")] if part and part.strip())


def has_crypto_cashtag(text: str) -> bool:
    """Return True when text contains non-stock cashtags."""
    return any(tag not in COMMON_STOCKS for tag in CASHTAG_RE.findall(text))


def score_tweet(tweet: dict[str, Any], config: dict[str, Any], *, mention_count: int = 1) -> float:
    """Score a tweet using engagement plus selective content boosts."""
    scoring = config["scoring"]
    selective = scoring["selective_boosts"]
    institutional = {item.lower() for item in config["filters"].get("institutional_accounts", [])}

    likes = int(tweet.get("like_count") or 0)
    retweets = int(tweet.get("retweet_count") or 0)
    followers = int(tweet.get("author_followers") or 0)
    author = str(tweet.get("author") or "").lower()
    text = tweet_text(tweet)
    lower = text.lower()

    base = likes + retweets * 3 + math.log10(max(followers, 1)) * 2
    if CRYPTO_RE.search(lower) or has_crypto_cashtag(text):
        base *= scoring["crypto_boost"]
    if ALPHA_RE.search(lower):
        base *= scoring["alpha_boost"]
    if ETF_FLOW_RE.search(lower):
        base *= selective["etf_flow"]
    if PAYMENT_WALLET_RE.search(lower):
        base *= selective["payment_wallet"]
    if COMPLIANCE_RE.search(lower):
        base *= selective["compliance"]
    if SECURITY_RE.search(lower):
        base *= selective["security"]
    if tweet.get("source") == "for_you":
        base *= scoring["for_you_boost"]
    if author in institutional and base < scoring["institutional_floor"]:
        base = float(scoring["institutional_floor"])

    if mention_count >= 10:
        base *= 3.0
    elif mention_count >= 6:
        base *= 2.0
    elif mention_count >= 3:
        base *= 1.5

    return round(base, 2)


def score_candidates(tweets: list[dict[str, Any]], config: dict[str, Any], mention_counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Attach scores to candidate tweets and sort descending."""
    mention_counts = mention_counts or {}
    scored: list[dict[str, Any]] = []
    for tweet in tweets:
        item = dict(tweet)
        item["score"] = score_tweet(tweet, config, mention_count=mention_counts.get(str(tweet.get("event_key") or ""), 1))
        scored.append(item)
    scored.sort(key=lambda item: (float(item.get("score") or 0), int(item.get("like_count") or 0)), reverse=True)
    return scored
