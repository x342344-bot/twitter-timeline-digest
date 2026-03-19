#!/usr/bin/env python3
"""Run one fetch cycle for the Twitter Timeline Digest project."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.fetch_timeline import run_fetch


def main() -> None:
    """CLI entrypoint for single-run fetch."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    summary = run_fetch(Path(args.config))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
