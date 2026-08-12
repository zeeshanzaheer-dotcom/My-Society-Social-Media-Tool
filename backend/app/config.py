"""Minimal .env loader (no dependency on python-dotenv).

Importing this module reads backend/.env (if present) into os.environ, without
overriding variables already set in the real environment. Import it before any
os.getenv() that should see .env values.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_env() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env()
