#!/usr/bin/env python3
"""Run one digest cycle from stored candidates."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.buzz import aggregate_buzz
from src.dedup import build_mention_counts, deduplicate_events, event_fingerprint
from src.digest import generate_digest
from src.scoring import score_candidates
from src.storage import load_recent_candidates, save_buzz, save_digest


def main() -> None:
    """CLI entrypoint for single-run digest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    data_dir = Path(config["storage"]["data_dir"])
    candidates = load_recent_candidates(data_dir, days=int(config["storage"]["dedup_window_days"]))
    mention_counts = build_mention_counts(candidates)
    for tweet in candidates:
        tweet["event_key"] = event_fingerprint(tweet)
    scored = score_candidates(candidates, config, mention_counts=mention_counts)
    deduped = deduplicate_events(scored)
    buzz = aggregate_buzz(deduped, min_authors=int(config["buzz"]["min_authors"]))
    digest = generate_digest(deduped, buzz, config)
    buzz_path = save_buzz(data_dir, buzz)
    digest_path = save_digest(data_dir, digest)
    print(json.dumps({
        "status": "ok",
        "candidate_input": len(candidates),
        "deduped": len(deduped),
        "buzz_clusters": len(buzz),
        "buzz_path": str(buzz_path),
        "digest_path": str(digest_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
