#!/usr/bin/env python3
"""Sanity-check local config, CDP access, and prompt files."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

import yaml


def main() -> None:
    """CLI entrypoint for health checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    cdp = config["cdp"]
    report = {
        "config_exists": True,
        "prompt_exists": Path(config["digest"]["prompt_path"]).exists(),
        "data_dir_exists": Path(config["storage"]["data_dir"]).exists(),
        "bearer_token_present": bool(os.environ.get(config["twitter"]["bearer_token_env"])),
        "openai_key_present": bool(os.environ.get(config["digest"]["api_key_env"])),
        "anthropic_key_present": bool(os.environ.get(config["digest"]["anthropic_api_key_env"])),
    }
    try:
        with urllib.request.urlopen(f"http://{cdp['host']}:{cdp['port']}/json/version", timeout=5) as response:
            version = json.loads(response.read().decode("utf-8"))
        report["cdp_reachable"] = True
        report["browser"] = version.get("Browser")
    except Exception as exc:
        report["cdp_reachable"] = False
        report["cdp_error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
