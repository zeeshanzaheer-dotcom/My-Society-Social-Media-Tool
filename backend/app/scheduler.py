"""The publishing engine.

A background asyncio loop wakes every few seconds, claims any jobs whose time
has come, and pushes them through: scheduled -> publishing -> published / failed.
Failures back off and retry up to MAX_ATTEMPTS. The same routine is exposed as
``run_due_once()`` so the UI can trigger an immediate tick for a live demo.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from . import analytics
from .adapters import AdapterError, PublishPayload, publish_post
from .db import get_conn, utcnow_iso

TICK_SECONDS = 3
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 20

_task: asyncio.Task | None = None
_stop = asyncio.Event()


async def run_due_once() -> dict:
    """Publish every job that is due right now. Returns a small summary."""
    now = utcnow_iso()
    conn = get_conn()
    try:
        due = conn.execute(
            """SELECT * FROM publish_jobs
               WHERE status = 'scheduled' AND scheduled_at <= ?
               ORDER BY scheduled_at ASC""",
            (now,),
        ).fetchall()
    finally:
        conn.close()

    published = 0
    failed = 0
    for job in due:
        ok = await _process_job(job["id"])
        if ok:
            published += 1
        else:
            failed += 1
    return {"checked": len(due), "published": published, "failed": failed}


async def _process_job(job_id: int) -> bool:
    conn = get_conn()
    try:
        job = conn.execute("SELECT * FROM publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None or job["status"] != "scheduled":
            return False

        post = conn.execute("SELECT * FROM posts WHERE id = ?", (job["post_id"],)).fetchone()
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (job["account_id"],)).fetchone()

        # claim the job
        conn.execute(
            "UPDATE publish_jobs SET status = 'publishing', attempts = attempts + 1 WHERE id = ?",
            (job_id,),
        )
        if post is not None and post["status"] in ("scheduled", "failed"):
            conn.execute("UPDATE posts SET status = 'publishing', updated_at = ? WHERE id = ?",
                         (utcnow_iso(), post["id"]))
        conn.commit()

        attempts = job["attempts"] + 1
        payload = PublishPayload(
            platform=job["platform"],
            format=post["format"] if post else "static",
            title=post["title"] if post else "",
            caption=post["caption"] if post else "",
            handle=account["handle"] if account else "",
            account_status=account["status"] if account else "disconnected",
            job_id=job_id,
            media_url=post["media_url"] if post else "",
        )
    finally:
        conn.close()

    # network call happens outside the DB connection
    try:
        result = await publish_post(payload)
    except AdapterError as exc:
        _mark_failure(job_id, attempts, str(exc))
        return False
    except Exception as exc:  # never let one bad job kill the loop
        _mark_failure(job_id, attempts, f"Unexpected error: {exc}")
        return False

    _mark_success(job_id, result.platform_post_id, result.platform_url)
    return True


def _mark_success(job_id: int, platform_post_id: str, platform_url: str) -> None:
    conn = get_conn()
    post_id = None
    account_id = None
    try:
        now = utcnow_iso()
        conn.execute(
            """UPDATE publish_jobs
               SET status = 'published', platform_post_id = ?, platform_url = ?,
                   published_at = ?, last_error = ''
               WHERE id = ?""",
            (platform_post_id, platform_url, now, job_id),
        )
        job = conn.execute("SELECT post_id, account_id FROM publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            post_id, account_id = job["post_id"], job["account_id"]
            _reconcile_post_status(conn, post_id)
        conn.commit()
    finally:
        conn.close()
    # analytics collection: a published post starts producing performance data
    if post_id is not None:
        analytics.record_metrics(post_id, account_id)


def _mark_failure(job_id: int, attempts: int, error: str) -> None:
    conn = get_conn()
    try:
        now = utcnow_iso()
        if attempts >= MAX_ATTEMPTS:
            conn.execute(
                "UPDATE publish_jobs SET status = 'failed', last_error = ? WHERE id = ?",
                (error, job_id),
            )
        else:
            # back off and try again on a later tick
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=BACKOFF_SECONDS)) \
                .strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                """UPDATE publish_jobs
                   SET status = 'scheduled', scheduled_at = ?, last_error = ?
                   WHERE id = ?""",
                (retry_at, error, job_id),
            )
        job = conn.execute("SELECT post_id FROM publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            _reconcile_post_status(conn, job["post_id"], failure=error)
        conn.commit()
    finally:
        conn.close()


def _reconcile_post_status(conn, post_id: int, failure: str | None = None) -> None:
    """A post is only 'published' when all its jobs are; if any finally failed
    and none are still pending, the post is 'failed'."""
    jobs = conn.execute(
        "SELECT status FROM publish_jobs WHERE post_id = ? AND status != 'canceled'",
        (post_id,),
    ).fetchall()
    if not jobs:
        return
    statuses = {j["status"] for j in jobs}
    now = utcnow_iso()
    if statuses <= {"published"}:
        new = "published"
    elif statuses & {"scheduled", "publishing"}:
        new = "publishing" if "publishing" in statuses else "scheduled"
    elif "failed" in statuses:
        new = "failed"
    else:
        return
    conn.execute("UPDATE posts SET status = ?, updated_at = ? WHERE id = ?", (new, now, post_id))


async def _loop() -> None:
    while not _stop.is_set():
        try:
            await run_due_once()
        except Exception as exc:  # keep the loop alive no matter what
            print(f"[scheduler] tick error: {exc}")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass


def start() -> None:
    global _task
    _stop.clear()
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    _stop.set()
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except asyncio.TimeoutError:
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
