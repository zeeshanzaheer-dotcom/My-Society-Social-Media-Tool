"""SQLite data layer for Wolfie.

Raw sqlite3 (no ORM) on purpose: zero dependency surprises, fully predictable
behaviour, and easy to read for whoever picks this up next. WAL mode + a short
busy timeout keep the API and the background scheduler out of each other's way.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "wolfie.db"


def utcnow_iso() -> str:
    """Current UTC time as a sortable, fixed-width ISO string (no offset = UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def to_utc_iso(value: str) -> str:
    """Normalise any client ISO datetime to our fixed-width UTC string."""
    v = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name         TEXT NOT NULL,
    initials     TEXT NOT NULL,
    color        TEXT NOT NULL,
    voice        TEXT NOT NULL DEFAULT '',
    never_say    TEXT NOT NULL DEFAULT '',
    cta          TEXT NOT NULL DEFAULT '',
    audience     TEXT NOT NULL DEFAULT '',
    always_say   TEXT NOT NULL DEFAULT '',
    pillars      TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id     INTEGER NOT NULL REFERENCES brands(id),
    platform     TEXT NOT NULL,          -- instagram | facebook | linkedin | tiktok | youtube
    handle       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'connected',  -- connected | disconnected | expired
    connected_at TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        INTEGER NOT NULL REFERENCES brands(id),
    account_id      INTEGER REFERENCES accounts(id),
    format          TEXT NOT NULL DEFAULT 'static',  -- reel | carousel | static | text
    title           TEXT NOT NULL DEFAULT '',
    caption         TEXT NOT NULL DEFAULT '',
    media_url       TEXT NOT NULL DEFAULT '',         -- public image/video URL for real publishing
    status          TEXT NOT NULL DEFAULT 'draft',
    -- draft | in_review | changes_requested | approved | scheduled | publishing | published | failed
    created_by      TEXT NOT NULL DEFAULT 'You',
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id),
    version    INTEGER NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    caption    TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    author     TEXT NOT NULL DEFAULT 'You',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id),
    action     TEXT NOT NULL,   -- submitted | approved | changes_requested
    actor      TEXT NOT NULL DEFAULT 'You',
    comment    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id      INTEGER NOT NULL REFERENCES posts(id),
    account_id   INTEGER REFERENCES accounts(id),
    platform     TEXT NOT NULL,
    format       TEXT NOT NULL,
    pillar       TEXT NOT NULL,
    reach        INTEGER NOT NULL DEFAULT 0,
    impressions  INTEGER NOT NULL DEFAULT 0,
    engagements  INTEGER NOT NULL DEFAULT 0,
    likes        INTEGER NOT NULL DEFAULT 0,
    comments     INTEGER NOT NULL DEFAULT 0,
    shares       INTEGER NOT NULL DEFAULT 0,
    saves        INTEGER NOT NULL DEFAULT 0,
    video_views  INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    handle    TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    initials  TEXT NOT NULL,
    color     TEXT NOT NULL,
    bio       TEXT NOT NULL DEFAULT '',
    following INTEGER NOT NULL DEFAULT 0,   -- 1 = the current user follows them
    suggested INTEGER NOT NULL DEFAULT 0    -- 1 = show in "who to follow"
);

CREATE TABLE IF NOT EXISTS notifications (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    type           TEXT NOT NULL,           -- like | comment | follow | mention | system
    actor_name     TEXT NOT NULL,
    actor_initials TEXT NOT NULL,
    actor_color    TEXT NOT NULL,
    text           TEXT NOT NULL,
    read           INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    author_name     TEXT NOT NULL,
    author_handle   TEXT NOT NULL,
    author_initials TEXT NOT NULL,
    author_color    TEXT NOT NULL,
    platform        TEXT NOT NULL,          -- instagram | linkedin | facebook | tiktok | youtube | wolfie
    text            TEXT NOT NULL,
    media           TEXT NOT NULL DEFAULT '',  -- themed placeholder keyword ('' = text-only)
    likes           INTEGER NOT NULL DEFAULT 0,
    reposts         INTEGER NOT NULL DEFAULT 0,
    comments_count  INTEGER NOT NULL DEFAULT 0,
    liked           INTEGER NOT NULL DEFAULT 0,
    reposted        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_comments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_post_id INTEGER NOT NULL REFERENCES feed_posts(id),
    author       TEXT NOT NULL,
    initials     TEXT NOT NULL DEFAULT 'You',
    text         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

-- Every engagement (like/repost/comment) a user makes in the unified feed is
-- mirrored back onto the post's ORIGIN platform. Each mirror attempt is logged
-- here so it can be surfaced in the feed and totalled in Analytics.
CREATE TABLE IF NOT EXISTS platform_engagements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_post_id INTEGER NOT NULL REFERENCES feed_posts(id),
    platform     TEXT NOT NULL,          -- origin platform the engagement reflects on
    action       TEXT NOT NULL,          -- like | repost | comment
    delta        INTEGER NOT NULL,       -- +1 added, -1 removed
    mirrored     INTEGER NOT NULL DEFAULT 1,  -- 1 = the platform adapter accepted it
    detail       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id          INTEGER NOT NULL REFERENCES posts(id),
    account_id       INTEGER NOT NULL REFERENCES accounts(id),
    platform         TEXT NOT NULL,
    scheduled_at     TEXT NOT NULL,   -- due time (also used as the retry time)
    status           TEXT NOT NULL DEFAULT 'scheduled',
    -- scheduled | publishing | published | failed | canceled
    attempts         INTEGER NOT NULL DEFAULT 0,
    last_error       TEXT NOT NULL DEFAULT '',
    platform_post_id TEXT NOT NULL DEFAULT '',
    platform_url     TEXT NOT NULL DEFAULT '',
    published_at     TEXT,
    created_at       TEXT NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent column adds, so an existing DB picks up new brand fields."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(brands)").fetchall()}
    for name in ("audience", "always_say", "pillars"):
        if name not in cols:
            conn.execute(f"ALTER TABLE brands ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    pcols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)").fetchall()}
    if "media_url" not in pcols:
        conn.execute("ALTER TABLE posts ADD COLUMN media_url TEXT NOT NULL DEFAULT ''")


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
