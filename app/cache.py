"""Tiny SQLite TTL cache. Stale entries can still be served when an upstream API is down."""
import json
import sqlite3
import time
from contextlib import closing

from .config import settings


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)"
    )
    return conn


def get(key: str, allow_stale: bool = False):
    with closing(_conn()) as conn:
        row = conn.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    value, expires = row
    if expires < time.time() and not allow_stale:
        return None
    return json.loads(value)


def set(key: str, value, ttl_seconds: int) -> None:  # noqa: A001 - mirrors dict-style API
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl_seconds),
        )
        conn.commit()
