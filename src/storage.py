"""JSON storage helpers for the Twitter Timeline Digest project."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")


def ensure_dir(path: Path) -> None:
    """Create a directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Write JSON atomically to avoid partial files."""
    ensure_dir(path.parent)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_json(path: Path, default: Any) -> Any:
    """Load JSON from disk and return a default value on failure."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.exception("Failed to load JSON: %s", path)
        return default


def today_key() -> str:
    """Return the current America/New_York date key."""
    return datetime.now(EASTERN).strftime("%Y-%m-%d")


def path_for_day(data_dir: Path, stem: str, day: str | None = None) -> Path:
    """Build a per-day JSON path."""
    date_key = day or today_key()
    return data_dir / f"{stem}_{date_key}.json"


def append_unique_records(path: Path, records: list[dict[str, Any]], *, id_key: str) -> int:
    """Append records to a JSON array, deduplicated by an ID field."""
    existing = load_json(path, [])
    if not isinstance(existing, list):
        existing = []
    seen = {str(item.get(id_key)) for item in existing if isinstance(item, dict) and item.get(id_key)}
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get(id_key) or "")
        if not record_id or record_id in seen:
            continue
        existing.append(record)
        seen.add(record_id)
    atomic_write_json(path, existing)
    return len(existing)


def save_raw_tweets(data_dir: Path, tweets: list[dict[str, Any]], *, day: str | None = None) -> int:
    """Save raw tweets for a given day."""
    return append_unique_records(path_for_day(data_dir, "raw", day), tweets, id_key="id")


def save_candidates(data_dir: Path, tweets: list[dict[str, Any]], *, day: str | None = None) -> int:
    """Save candidate tweets for a given day."""
    return append_unique_records(path_for_day(data_dir, "candidates", day), tweets, id_key="id")


def save_digest(data_dir: Path, digest: dict[str, Any], *, day: str | None = None) -> Path:
    """Save digest output for a given day."""
    path = path_for_day(data_dir, "digest", day)
    atomic_write_json(path, digest)
    return path


def save_buzz(data_dir: Path, buzz: list[dict[str, Any]], *, day: str | None = None) -> Path:
    """Save buzz clusters for a given day."""
    path = path_for_day(data_dir, "buzz", day)
    atomic_write_json(path, buzz)
    return path


def load_recent_candidates(data_dir: Path, *, days: int) -> list[dict[str, Any]]:
    """Load candidate tweets across the recent time window."""
    results: list[dict[str, Any]] = []
    now = datetime.now(EASTERN)
    for offset in range(days):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        path = path_for_day(data_dir, "candidates", day)
        payload = load_json(path, [])
        if isinstance(payload, list):
            results.extend([item for item in payload if isinstance(item, dict)])
    return results


def cleanup_old_files(data_dir: Path, *, retention_days: int) -> None:
    """Remove dated JSON files older than the retention window."""
    ensure_dir(data_dir)
    cutoff = datetime.now(EASTERN) - timedelta(days=retention_days)
    for path in data_dir.glob("*_????-??-??.json"):
        try:
            day_str = path.stem.rsplit("_", 1)[1]
            file_day = datetime.strptime(day_str, "%Y-%m-%d")
        except Exception:
            continue
        if file_day < cutoff.replace(tzinfo=None):
            path.unlink(missing_ok=True)
            LOGGER.info("Removed old file: %s", path.name)
