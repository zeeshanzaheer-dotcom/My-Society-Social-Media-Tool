"""Vercel serverless entrypoint — exposes the FastAPI ASGI app.

Vercel's Python runtime imports `app` from this file and serves it. We point
SQLite at /tmp (the only writable path on Vercel) and disable the background
publish scheduler (serverless can't run a long-lived loop). Demo data is seeded
fresh on each cold start — perfect for the dummy-data demo, not for persistence.
"""
import os
import sys

# make the backend package importable (project root = the `backend` dir)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("WOLFIE_DB_PATH", "/tmp/wolfie.db")
os.environ.setdefault("WOLFIE_DISABLE_SCHEDULER", "1")

from app.main import app  # noqa: E402,F401  (Vercel serves this `app`)
