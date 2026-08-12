"""HTTP API. Thin handlers over the sqlite data layer; the interesting logic is
the approval state machine and the scheduling hand-off to the publish engine.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import adapters, analytics, scheduler, seed
from .ai import get_provider
from .db import get_conn, rows_to_list, row_to_dict, to_utc_iso, utcnow_iso

router = APIRouter(prefix="/api")

# valid transitions for the approval workflow
_ALLOWED = {
    "submit": {"draft", "changes_requested"},          # -> in_review
    "approve": {"in_review"},                            # -> approved
    "request-changes": {"in_review"},                   # -> changes_requested
    "schedule": {"approved"},                            # -> scheduled
}


# --- request bodies ----------------------------------------------------------

class NewPost(BaseModel):
    brand_id: int
    account_id: Optional[int] = None
    format: str = "static"
    title: str = ""
    caption: str = ""
    media_url: str = ""
    created_by: str = "You"


class EditPost(BaseModel):
    title: Optional[str] = None
    caption: Optional[str] = None
    media_url: Optional[str] = None
    author: str = "You"


class Actor(BaseModel):
    actor: str = "You"


class ChangeReq(BaseModel):
    actor: str = "You"
    comment: str = ""


class Schedule(BaseModel):
    scheduled_at: str
    account_ids: Optional[list[int]] = None
    actor: str = "You"


class PublishNow(BaseModel):
    actor: str = "You"


class GenerateReq(BaseModel):
    brand_id: int
    format: str = "static"
    topic: str = ""
    objective: str = ""


class FromRec(BaseModel):
    account_id: Optional[int] = None
    format: str = "reel"
    objective: str = ""
    title: str = ""
    topic: str = ""
    generate: bool = True


class BrandEdit(BaseModel):
    name: Optional[str] = None
    voice: Optional[str] = None
    audience: Optional[str] = None
    cta: Optional[str] = None
    never_say: Optional[str] = None
    always_say: Optional[str] = None
    pillars: Optional[list[str]] = None


class FeedNew(BaseModel):
    text: str
    media: str = ""


class FeedComment(BaseModel):
    text: str


# --- helpers -----------------------------------------------------------------

def _post_or_404(conn, post_id: int):
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Post {post_id} not found")
    return row


def _violations(caption: str, never_say: str) -> list[str]:
    """Brand-safety check: which 'never say' phrases appear in the caption."""
    cap = (caption or "").lower()
    hits = []
    for phrase in (never_say or "").split(","):
        p = phrase.strip()
        if p and p.lower() in cap:
            hits.append(p)
    return hits


def _bump_version(conn, post_id: int, title: str, caption: str, note: str, author: str) -> int:
    row = conn.execute("SELECT current_version FROM posts WHERE id = ?", (post_id,)).fetchone()
    version = (row["current_version"] if row else 0) + 1
    now = utcnow_iso()
    conn.execute(
        "INSERT INTO post_versions (post_id, version, title, caption, note, author, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (post_id, version, title, caption, note, author, now),
    )
    conn.execute("UPDATE posts SET current_version = ?, updated_at = ? WHERE id = ?", (version, now, post_id))
    return version


# --- read --------------------------------------------------------------------

@router.get("/health")
def health():
    return {"ok": True, "time": utcnow_iso()}


@router.get("/state")
def state():
    conn = get_conn()
    try:
        brand = conn.execute("SELECT * FROM brands ORDER BY id LIMIT 1").fetchone()
        brands = conn.execute("SELECT * FROM brands ORDER BY id").fetchall()
        accounts = conn.execute("SELECT * FROM accounts WHERE brand_id = ? ORDER BY id",
                                (brand["id"],)).fetchall() if brand else []
        counts = {
            "in_review": conn.execute("SELECT COUNT(*) c FROM posts WHERE status='in_review'").fetchone()["c"],
            "scheduled": conn.execute("SELECT COUNT(*) c FROM publish_jobs WHERE status='scheduled'").fetchone()["c"],
            "published": conn.execute("SELECT COUNT(*) c FROM publish_jobs WHERE status='published'").fetchone()["c"],
            "failed": conn.execute("SELECT COUNT(*) c FROM publish_jobs WHERE status='failed'").fetchone()["c"],
        }
        following = [r["handle"] for r in
                     conn.execute("SELECT handle FROM people WHERE following = 1").fetchall()]
        unread = conn.execute("SELECT COUNT(*) c FROM notifications WHERE read = 0").fetchone()["c"]
        return {
            "brand": row_to_dict(brand),
            "brands": rows_to_list(brands),
            "accounts": rows_to_list(accounts),
            "counts": counts,
            "following": following,
            "unread": unread,
        }
    finally:
        conn.close()


@router.get("/brands/{brand_id}")
def get_brand(brand_id: int):
    conn = get_conn()
    try:
        b = conn.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
        if b is None:
            raise HTTPException(404, "Brand not found")
        return row_to_dict(b)
    finally:
        conn.close()


@router.patch("/brands/{brand_id}")
def edit_brand(brand_id: int, body: BrandEdit):
    conn = get_conn()
    try:
        b = conn.execute("SELECT id FROM brands WHERE id = ?", (brand_id,)).fetchone()
        if b is None:
            raise HTTPException(404, "Brand not found")
        fields: dict = {}
        for k in ("name", "voice", "audience", "cta", "never_say", "always_say"):
            v = getattr(body, k)
            if v is not None:
                fields[k] = v
        if body.pillars is not None:
            fields["pillars"] = ",".join(p.strip() for p in body.pillars if p.strip())
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE brands SET {sets} WHERE id = ?", (*fields.values(), brand_id))
            conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone())
    finally:
        conn.close()


@router.get("/brands/{brand_id}/accounts")
def brand_accounts(brand_id: int):
    conn = get_conn()
    try:
        return rows_to_list(conn.execute(
            "SELECT * FROM accounts WHERE brand_id = ? ORDER BY id", (brand_id,)).fetchall())
    finally:
        conn.close()


@router.get("/posts")
def list_posts(status: Optional[str] = None, brand_id: Optional[int] = None):
    conn = get_conn()
    try:
        sql = ("SELECT p.*, a.platform, a.handle FROM posts p "
               "LEFT JOIN accounts a ON a.id = p.account_id WHERE 1=1")
        args: list = []
        if status:
            sql += " AND p.status = ?"; args.append(status)
        if brand_id:
            sql += " AND p.brand_id = ?"; args.append(brand_id)
        sql += " ORDER BY p.updated_at DESC"
        result = rows_to_list(conn.execute(sql, args).fetchall())
        never_map = {r["id"]: r["never_say"]
                     for r in conn.execute("SELECT id, never_say FROM brands").fetchall()}
        for p in result:
            p["violations"] = _violations(p.get("caption", ""), never_map.get(p["brand_id"], ""))
        return result
    finally:
        conn.close()


@router.get("/posts/{post_id}")
def get_post(post_id: int):
    conn = get_conn()
    try:
        post = _post_or_404(conn, post_id)
        brand = conn.execute("SELECT never_say FROM brands WHERE id = ?", (post["brand_id"],)).fetchone()
        return {
            **row_to_dict(post),
            "violations": _violations(post["caption"], brand["never_say"] if brand else ""),
            "versions": rows_to_list(conn.execute(
                "SELECT * FROM post_versions WHERE post_id = ? ORDER BY version", (post_id,)).fetchall()),
            "approvals": rows_to_list(conn.execute(
                "SELECT * FROM approvals WHERE post_id = ? ORDER BY id", (post_id,)).fetchall()),
            "jobs": rows_to_list(conn.execute(
                "SELECT * FROM publish_jobs WHERE post_id = ? ORDER BY id", (post_id,)).fetchall()),
        }
    finally:
        conn.close()


@router.get("/calendar")
def calendar(start: Optional[str] = None, end: Optional[str] = None):
    conn = get_conn()
    try:
        sql = ("SELECT j.*, p.title, p.format FROM publish_jobs j "
               "JOIN posts p ON p.id = j.post_id WHERE j.status != 'canceled'")
        args: list = []
        if start:
            sql += " AND j.scheduled_at >= ?"; args.append(to_utc_iso(start))
        if end:
            sql += " AND j.scheduled_at <= ?"; args.append(to_utc_iso(end))
        sql += " ORDER BY j.scheduled_at"
        return rows_to_list(conn.execute(sql, args).fetchall())
    finally:
        conn.close()


@router.get("/jobs")
def list_jobs(status: Optional[str] = None):
    conn = get_conn()
    try:
        sql = ("SELECT j.*, p.title, p.format, a.handle FROM publish_jobs j "
               "JOIN posts p ON p.id = j.post_id JOIN accounts a ON a.id = j.account_id")
        args: list = []
        if status:
            sql += " WHERE j.status = ?"; args.append(status)
        sql += " ORDER BY j.scheduled_at DESC, j.id DESC"
        return rows_to_list(conn.execute(sql, args).fetchall())
    finally:
        conn.close()


# --- create / edit -----------------------------------------------------------

@router.post("/posts")
def create_post(body: NewPost):
    conn = get_conn()
    try:
        now = utcnow_iso()
        cur = conn.execute(
            "INSERT INTO posts (brand_id, account_id, format, title, caption, media_url, status, created_by, "
            "current_version, created_at, updated_at) VALUES (?,?,?,?,?,?, 'draft', ?, 1, ?, ?)",
            (body.brand_id, body.account_id, body.format, body.title, body.caption, body.media_url,
             body.created_by, now, now),
        )
        pid = cur.lastrowid
        conn.execute(
            "INSERT INTO post_versions (post_id, version, title, caption, note, author, created_at) "
            "VALUES (?, 1, ?, ?, 'Created', ?, ?)",
            (pid, body.title, body.caption, body.created_by, now),
        )
        conn.commit()
        return get_post(pid)
    finally:
        conn.close()


@router.patch("/posts/{post_id}")
def edit_post(post_id: int, body: EditPost):
    conn = get_conn()
    try:
        post = _post_or_404(conn, post_id)
        title = body.title if body.title is not None else post["title"]
        caption = body.caption if body.caption is not None else post["caption"]
        media_url = body.media_url if body.media_url is not None else post["media_url"]
        conn.execute("UPDATE posts SET title = ?, caption = ?, media_url = ? WHERE id = ?",
                     (title, caption, media_url, post_id))
        _bump_version(conn, post_id, title, caption, "Edited", body.author)
        conn.commit()
        return get_post(post_id)
    finally:
        conn.close()


# --- approval workflow -------------------------------------------------------

def _transition(post_id: int, action: str, new_status: str, actor: str, comment: str = ""):
    conn = get_conn()
    try:
        post = _post_or_404(conn, post_id)
        if post["status"] not in _ALLOWED[action]:
            raise HTTPException(409, f"Can't {action} a post that is '{post['status']}'.")
        now = utcnow_iso()
        conn.execute("UPDATE posts SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, post_id))
        audit = {"submit": "submitted", "approve": "approved", "request-changes": "changes_requested"}[action]
        conn.execute(
            "INSERT INTO approvals (post_id, action, actor, comment, created_at) VALUES (?,?,?,?,?)",
            (post_id, audit, actor, comment, now),
        )
        conn.commit()
        return get_post(post_id)
    finally:
        conn.close()


@router.post("/posts/{post_id}/submit")
def submit(post_id: int, body: Actor):
    return _transition(post_id, "submit", "in_review", body.actor)


@router.post("/posts/{post_id}/approve")
def approve(post_id: int, body: Actor):
    return _transition(post_id, "approve", "approved", body.actor)


@router.post("/posts/{post_id}/request-changes")
def request_changes(post_id: int, body: ChangeReq):
    return _transition(post_id, "request-changes", "changes_requested", body.actor, body.comment)


# --- scheduling --------------------------------------------------------------

def _schedule(post_id: int, when_iso: str, account_ids: Optional[list[int]]):
    conn = get_conn()
    try:
        post = _post_or_404(conn, post_id)
        if post["status"] not in _ALLOWED["schedule"]:
            raise HTTPException(409, f"Approve the post before scheduling (it's '{post['status']}').")
        targets = account_ids or ([post["account_id"]] if post["account_id"] else [])
        if not targets:
            raise HTTPException(400, "No account to publish to. Attach an account to the post first.")
        now = utcnow_iso()
        for acc_id in targets:
            acc = conn.execute("SELECT * FROM accounts WHERE id = ?", (acc_id,)).fetchone()
            if acc is None:
                raise HTTPException(400, f"Account {acc_id} not found.")
            conn.execute(
                "INSERT INTO publish_jobs (post_id, account_id, platform, scheduled_at, status, created_at) "
                "VALUES (?,?,?,?, 'scheduled', ?)",
                (post_id, acc_id, acc["platform"], when_iso, now),
            )
        conn.execute("UPDATE posts SET status = 'scheduled', updated_at = ? WHERE id = ?", (now, post_id))
        conn.commit()
        return get_post(post_id)
    finally:
        conn.close()


@router.post("/posts/{post_id}/schedule")
def schedule_post(post_id: int, body: Schedule):
    return _schedule(post_id, to_utc_iso(body.scheduled_at), body.account_ids)


@router.post("/posts/{post_id}/publish-now")
def publish_now(post_id: int, body: PublishNow):
    return _schedule(post_id, utcnow_iso(), None)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    conn = get_conn()
    try:
        job = conn.execute("SELECT * FROM publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404, "Job not found")
        if job["status"] in ("published",):
            raise HTTPException(409, "Already published — can't cancel.")
        conn.execute("UPDATE publish_jobs SET status = 'canceled' WHERE id = ?", (job_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/jobs/run-due")
async def run_due():
    """Force the publish engine to process anything due right now — handy for demos."""
    return await scheduler.run_due_once()


# --- AI ----------------------------------------------------------------------

@router.post("/ai/generate")
def ai_generate(body: GenerateReq):
    conn = get_conn()
    try:
        brand = conn.execute("SELECT * FROM brands WHERE id = ?", (body.brand_id,)).fetchone()
        if brand is None:
            raise HTTPException(404, "Brand not found")
        try:
            return get_provider().generate(row_to_dict(brand), body.format, body.topic, body.objective)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))
    finally:
        conn.close()


# --- analytics + recommendations (the learning half of the loop) -------------

@router.get("/analytics/summary")
def analytics_summary():
    return analytics.summary()


@router.get("/recommendations")
def recommendations():
    return analytics.recommendations()


@router.post("/create-from-recommendation")
def create_from_recommendation(body: FromRec):
    conn = get_conn()
    try:
        brand = conn.execute("SELECT * FROM brands ORDER BY id LIMIT 1").fetchone()
        if brand is None:
            raise HTTPException(404, "No brand configured")
        brand_id = brand["id"]
        account_id = body.account_id
        if account_id is None:
            acc = conn.execute(
                "SELECT id FROM accounts WHERE brand_id = ? AND status = 'connected' ORDER BY id LIMIT 1",
                (brand_id,)).fetchone()
            account_id = acc["id"] if acc else None
        brand_dict = row_to_dict(brand)
    finally:
        conn.close()

    title, caption = body.title, ""
    if body.generate:
        try:
            g = get_provider().generate(brand_dict, body.format, body.topic, body.objective)
            title = g.get("title") or title
            caption = g.get("caption", "")
        except RuntimeError as exc:
            raise HTTPException(400, str(exc))

    # reuse the normal create path so it lands as a draft in the pipeline
    return create_post(NewPost(brand_id=brand_id, account_id=account_id, format=body.format,
                               title=title, caption=caption, created_by="You"))


# --- network feed (the home-page social feed) --------------------------------

@router.get("/feed")
def feed_list():
    conn = get_conn()
    try:
        return rows_to_list(conn.execute(
            "SELECT * FROM feed_posts ORDER BY datetime(created_at) DESC, id DESC").fetchall())
    finally:
        conn.close()


@router.post("/feed")
def feed_create(body: FeedNew):
    if not body.text.strip():
        raise HTTPException(400, "Say something before posting.")
    conn = get_conn()
    try:
        now = utcnow_iso()
        cur = conn.execute(
            "INSERT INTO feed_posts (author_name, author_handle, author_initials, author_color, platform, "
            "text, media, likes, reposts, comments_count, liked, reposted, created_at) "
            "VALUES (?,?,?,?,?,?,?,0,0,0,0,0,?)",
            ("Zeeshan Zaheer", "zeeshan", "ZZ", "#6E62D6", "linkedin", body.text.strip(), body.media, now),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM feed_posts WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def _mirror_and_log(conn, fid: int, platform: str, action: str, delta: int) -> dict:
    """Reflect a feed engagement onto its origin platform and log the attempt."""
    mirror = adapters.mirror_engagement(platform, action, delta, ref=str(fid))
    conn.execute(
        "INSERT INTO platform_engagements (feed_post_id, platform, action, delta, mirrored, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (fid, platform, action, delta, 1 if mirror["mirrored"] else 0, mirror["detail"], utcnow_iso()),
    )
    return mirror


def _feed_toggle(fid: int, flag_col: str, count_col: str, action: str):
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM feed_posts WHERE id = ?", (fid,)).fetchone()
        if p is None:
            raise HTTPException(404, "Post not found")
        new_flag = 0 if p[flag_col] else 1
        delta = 1 if new_flag else -1
        conn.execute(f"UPDATE feed_posts SET {flag_col} = ?, {count_col} = {count_col} + ? WHERE id = ?",
                     (new_flag, delta, fid))
        mirror = _mirror_and_log(conn, fid, p["platform"], action, delta)
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM feed_posts WHERE id = ?", (fid,)).fetchone())
        row["mirror"] = mirror
        return row
    finally:
        conn.close()


@router.post("/feed/{fid}/like")
def feed_like(fid: int):
    return _feed_toggle(fid, "liked", "likes", "like")


@router.post("/feed/{fid}/repost")
def feed_repost(fid: int):
    return _feed_toggle(fid, "reposted", "reposts", "repost")


@router.get("/feed/{fid}/comments")
def feed_comments(fid: int):
    conn = get_conn()
    try:
        return rows_to_list(conn.execute(
            "SELECT * FROM feed_comments WHERE feed_post_id = ? ORDER BY id", (fid,)).fetchall())
    finally:
        conn.close()


@router.post("/feed/{fid}/comment")
def feed_comment(fid: int, body: FeedComment):
    if not body.text.strip():
        raise HTTPException(400, "Empty comment.")
    conn = get_conn()
    try:
        p = conn.execute("SELECT platform FROM feed_posts WHERE id = ?", (fid,)).fetchone()
        if p is None:
            raise HTTPException(404, "Post not found")
        conn.execute("INSERT INTO feed_comments (feed_post_id, author, initials, text, created_at) VALUES (?,?,?,?,?)",
                     (fid, "Zeeshan Zaheer", "ZZ", body.text.strip(), utcnow_iso()))
        conn.execute("UPDATE feed_posts SET comments_count = comments_count + 1 WHERE id = ?", (fid,))
        mirror = _mirror_and_log(conn, fid, p["platform"], "comment", 1)
        conn.commit()
        comments = rows_to_list(conn.execute(
            "SELECT * FROM feed_comments WHERE feed_post_id = ? ORDER BY id", (fid,)).fetchall())
        return {"comments": comments, "mirror": mirror}
    finally:
        conn.close()


# --- social graph: people & notifications ------------------------------------

@router.get("/people")
def people_list():
    conn = get_conn()
    try:
        return rows_to_list(conn.execute(
            "SELECT * FROM people ORDER BY following DESC, name").fetchall())
    finally:
        conn.close()


@router.post("/people/{handle}/follow")
def person_follow(handle: str):
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM people WHERE handle = ?", (handle,)).fetchone()
        if p is None:
            raise HTTPException(404, "Person not found")
        new_flag = 0 if p["following"] else 1
        conn.execute("UPDATE people SET following = ? WHERE handle = ?", (new_flag, handle))
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM people WHERE handle = ?", (handle,)).fetchone())
    finally:
        conn.close()


@router.get("/notifications")
def notifications_list():
    conn = get_conn()
    try:
        return rows_to_list(conn.execute(
            "SELECT * FROM notifications ORDER BY datetime(created_at) DESC, id DESC").fetchall())
    finally:
        conn.close()


@router.post("/notifications/read")
def notifications_read():
    conn = get_conn()
    try:
        conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# --- my profile: the user's own posts across every platform ------------------

@router.get("/profile")
def profile():
    conn = get_conn()
    try:
        brand = conn.execute("SELECT * FROM brands ORDER BY id LIMIT 1").fetchone()
        if brand is None:
            raise HTTPException(404, "No brand configured")
        following = conn.execute("SELECT COUNT(*) c FROM people WHERE following = 1").fetchone()["c"]
        accts = conn.execute("SELECT platform, handle, status FROM accounts WHERE brand_id = ?",
                             (brand["id"],)).fetchall()
        # every post the brand has made, joined to its channel's platform and its metrics
        rows = conn.execute(
            "SELECT p.id, p.format, p.title, p.caption, p.status, p.media_url, p.created_at, "
            "       a.platform AS platform, a.handle AS handle, "
            "       COALESCE(m.reach,0) AS reach, COALESCE(m.engagements,0) AS engagements, "
            "       COALESCE(m.likes,0) AS likes, COALESCE(m.comments,0) AS comments, "
            "       COALESCE(m.shares,0) AS shares "
            "FROM posts p "
            "LEFT JOIN accounts a ON a.id = p.account_id "
            "LEFT JOIN (SELECT post_id, SUM(reach) reach, SUM(engagements) engagements, SUM(likes) likes, "
            "                  SUM(comments) comments, SUM(shares) shares "
            "           FROM post_metrics GROUP BY post_id) m ON m.post_id = p.id "
            "WHERE p.brand_id = ? ORDER BY datetime(p.created_at) DESC, p.id DESC",
            (brand["id"],)).fetchall()
        posts = rows_to_list(rows)
        published = [p for p in posts if p["status"] == "published"]
        platforms = sorted({a["platform"] for a in accts if a["status"] == "connected"})
        return {
            "profile": {
                "name": "Zeeshan Zaheer", "handle": "zeeshan", "initials": "ZZ", "color": "#6E62D6",
                "brand": brand["name"], "role": "Admin",
                "following": following,
                "posts_count": len(published),
                "reach": sum(p["reach"] for p in posts),
                "platforms": platforms,
            },
            "posts": posts,
        }
    finally:
        conn.close()


# --- integrations ------------------------------------------------------------

@router.get("/integrations/meta/check")
async def meta_check():
    """Verify Meta/Instagram credentials without publishing (drives the setup screen)."""
    return await adapters.meta_check()


# --- dev convenience ---------------------------------------------------------

@router.post("/admin/reset")
def reset():
    seed.reset_and_seed()
    return {"ok": True}
