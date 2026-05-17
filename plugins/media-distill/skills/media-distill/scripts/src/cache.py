"""Simple SQLite key→JSON cache with TTL. stdlib-only."""

import json
import sqlite3
import time
from pathlib import Path

_CACHE_DIR = Path(__file__).parent.parent / ".cache"
_CACHE_PATH = _CACHE_DIR / "cache.sqlite"
_DEFAULT_TTL_SEC = 30 * 24 * 60 * 60  # 30 days


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_CACHE_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv ("
        "namespace TEXT NOT NULL, "
        "key TEXT NOT NULL, "
        "data TEXT NOT NULL, "
        "fetched_at INTEGER NOT NULL, "
        "PRIMARY KEY (namespace, key))"
    )
    return conn


def get(namespace: str, key: str, ttl_sec: int = _DEFAULT_TTL_SEC) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data, fetched_at FROM kv WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
    if row is None:
        return None
    data_json, fetched_at = row
    if time.time() - fetched_at > ttl_sec:
        return None
    try:
        return json.loads(data_json)
    except json.JSONDecodeError:
        return None


def put(namespace: str, key: str, data: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv (namespace, key, data, fetched_at) VALUES (?, ?, ?, ?)",
            (namespace, key, json.dumps(data, ensure_ascii=False), int(time.time())),
        )
