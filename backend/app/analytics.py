"""Analytics + the recommendation engine — the learning half of the loop.

When a post publishes, we record performance metrics (mock, but shaped so real
patterns emerge: reels out-reach static, market-data drives saves, area-guides
drive shares). Everything is scored against the brand's OWN baseline, and the
recommender turns those patterns — plus content gaps — into a ranked "what should
I post next", each with a plain-language reason.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from .db import get_conn, utcnow_iso

CANONICAL_PILLARS = ["Market Data", "Investment Education", "Area Guides", "New Projects", "News"]

# base performance by format
_FMT = {
    "reel":     {"reach": 14000, "eng": 0.062},
    "carousel": {"reach": 9000,  "eng": 0.055},
    "static":   {"reach": 5200,  "eng": 0.032},
    "text":     {"reach": 6000,  "eng": 0.045},
}
# multipliers by content pillar: (reach, saves, shares)
_PILLAR = {
    "Market Data":          {"reach": 1.20, "saves": 2.3, "shares": 1.3},
    "Investment Education": {"reach": 1.10, "saves": 1.7, "shares": 1.2},
    "Area Guides":          {"reach": 1.05, "saves": 1.2, "shares": 2.3},
    "New Projects":         {"reach": 1.00, "saves": 1.0, "shares": 1.0},
    "News":                 {"reach": 0.85, "saves": 0.7, "shares": 0.9},
    "General":              {"reach": 0.90, "saves": 1.0, "shares": 1.0},
}

_PILLAR_KEYWORDS = [
    (["market", "transaction", "yield", "data", "numbers", "price", "report", "dxb"], "Market Data"),
    (["golden visa", "mortgage", "invest", "myth", "finance", "roi", "eligib"], "Investment Education"),
    (["area", "guide", "island", "waterfront", "community", "saadiyat", "palm",
      "rak", "abu dhabi", "downtown", "marina", "yas"], "Area Guides"),
    (["launch", "project", "off-plan", "offplan", "new tower", "handover"], "New Projects"),
    (["news", "roundup", "announce"], "News"),
]

_TITLES = {
    "Market Data": "Dubai just posted its latest transaction numbers — here's what they mean",
    "Investment Education": "The Golden Visa, explained in plain numbers",
    "Area Guides": "Why this UAE community belongs on your investment shortlist",
    "New Projects": "A new off-plan launch just dropped — is it actually worth it?",
    "News": "This week in UAE property, in 60 seconds",
}
_OBJECTIVE = {
    "Market Data": "Saves", "Investment Education": "Leads",
    "Area Guides": "Shares", "New Projects": "Reach", "News": "Reach",
}


def pillar_for(title: str) -> str:
    t = (title or "").lower()
    for kws, name in _PILLAR_KEYWORDS:
        if any(k in t for k in kws):
            return name
    return "General"


# --- metrics ingestion -------------------------------------------------------

def _mock_metrics(fmt: str, pillar: str) -> dict:
    base = _FMT.get(fmt, _FMT["static"])
    pm = _PILLAR.get(pillar, _PILLAR["General"])
    v = random.uniform(0.82, 1.28)
    reach = int(base["reach"] * pm["reach"] * v)
    impressions = int(reach * random.uniform(1.3, 1.6))
    eng = int(reach * base["eng"] * random.uniform(0.85, 1.2))
    likes = int(eng * 0.70)
    comments = max(1, int(eng * 0.07))
    shares = int(eng * 0.13 * pm["shares"])
    saves = int(eng * 0.11 * pm["saves"])
    engagements = likes + comments + shares + saves
    return {
        "reach": reach, "impressions": impressions, "engagements": engagements,
        "likes": likes, "comments": comments, "shares": shares, "saves": saves,
        "video_views": reach if fmt == "reel" else 0,
    }


def record_metrics(post_id: int, account_id: int | None, collected_at: str | None = None) -> None:
    """Called by the publish engine right after a successful publish."""
    conn = get_conn()
    try:
        post = conn.execute("SELECT format, title FROM posts WHERE id = ?", (post_id,)).fetchone()
        if post is None:
            return
        platform = "instagram"
        if account_id is not None:
            acc = conn.execute("SELECT platform FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if acc:
                platform = acc["platform"]
        pillar = pillar_for(post["title"])
        m = _mock_metrics(post["format"], pillar)
        conn.execute(
            "INSERT INTO post_metrics (post_id, account_id, platform, format, pillar, reach, impressions, "
            "engagements, likes, comments, shares, saves, video_views, collected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (post_id, account_id, platform, post["format"], pillar, m["reach"], m["impressions"],
             m["engagements"], m["likes"], m["comments"], m["shares"], m["saves"], m["video_views"],
             collected_at or utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# --- analytics summary -------------------------------------------------------

def _synced_engagements() -> list[dict]:
    """Feed engagements mirrored to each origin platform (net of un-likes)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT platform, SUM(delta) AS net, COUNT(*) AS events "
            "FROM platform_engagements WHERE mirrored = 1 GROUP BY platform").fetchall()
    finally:
        conn.close()
    out = [{"platform": r["platform"], "net": r["net"] or 0, "events": r["events"]}
           for r in rows if (r["net"] or 0) > 0]
    out.sort(key=lambda x: x["net"], reverse=True)
    return out


def summary() -> dict:
    synced = _synced_engagements()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT m.*, p.title FROM post_metrics m JOIN posts p ON p.id = m.post_id").fetchall()
    finally:
        conn.close()
    if not rows:
        return {"totals": {"posts": 0, "reach": 0, "engagement_rate": 0},
                "formats": [], "topics": [], "best": None, "synced": synced}

    total_reach = sum(r["reach"] for r in rows)
    total_eng = sum(r["engagements"] for r in rows)
    totals = {
        "posts": len(rows),
        "reach": total_reach,
        "engagement_rate": round(total_eng / total_reach, 4) if total_reach else 0,
    }

    # per-format averages + a 0-10 score
    by_fmt: dict[str, list] = {}
    for r in rows:
        by_fmt.setdefault(r["format"], []).append(r)
    fmt_avg = {f: sum(x["reach"] for x in xs) / len(xs) for f, xs in by_fmt.items()}
    fmt_eng = {f: (sum(x["engagements"] for x in xs) / max(1, sum(x["reach"] for x in xs))) for f, xs in by_fmt.items()}
    max_reach = max(fmt_avg.values()) if fmt_avg else 1
    max_eng = max(fmt_eng.values()) if fmt_eng else 1
    formats = sorted(
        [{"format": f, "count": len(by_fmt[f]), "avg_reach": int(fmt_avg[f]),
          "score": round((fmt_avg[f] / max_reach) * 5 + (fmt_eng[f] / max_eng) * 5, 1)}
         for f in by_fmt],
        key=lambda x: x["score"], reverse=True,
    )

    # per-pillar save+share rate → topic score
    by_pillar: dict[str, list] = {}
    for r in rows:
        by_pillar.setdefault(r["pillar"], []).append(r)
    pill_rate = {p: (sum(x["saves"] + x["shares"] for x in xs) / max(1, sum(x["reach"] for x in xs)))
                 for p, xs in by_pillar.items()}
    max_rate = max(pill_rate.values()) if pill_rate else 1
    topics = sorted(
        [{"pillar": p, "count": len(by_pillar[p]), "score": round((pill_rate[p] / max_rate) * 10, 1)}
         for p in by_pillar],
        key=lambda x: x["score"], reverse=True,
    )

    # best post vs its format baseline
    best = None
    for r in rows:
        baseline = fmt_avg.get(r["format"], r["reach"]) or 1
        pct = round((r["reach"] / baseline - 1) * 100)
        if best is None or pct > best["pct"]:
            best = {"title": r["title"], "format": r["format"], "reach": r["reach"], "pct": pct}

    return {"totals": totals, "formats": formats, "topics": topics, "best": best, "synced": synced}


# --- recommendations ---------------------------------------------------------

def _days_since_pillar(pillars: list[str]) -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT title, created_at FROM posts").fetchall()
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    last: dict[str, datetime] = {}
    for r in rows:
        p = pillar_for(r["title"])
        try:
            dt = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if p not in last or dt > last[p]:
            last[p] = dt
    return {p: ((now - last[p]).days if p in last else 999) for p in pillars}


def recommendations(limit: int = 4) -> list[dict]:
    summ = summary()
    formats = summ["formats"]
    topics = summ["topics"]

    top_fmt = formats[0]["format"] if formats else "reel"
    top_fmt_score = formats[0]["score"] if formats else 8.5
    top_topic = topics[0]["pillar"] if topics and topics[0]["pillar"] in _TITLES else "Market Data"
    top_topic_score = topics[0]["score"] if topics else 9.0
    save_mult = _PILLAR.get(top_topic, _PILLAR["General"])["saves"]

    # pick the brand's connected accounts (prefer instagram for reels, linkedin for text)
    conn = get_conn()
    try:
        brand = conn.execute("SELECT pillars FROM brands ORDER BY id LIMIT 1").fetchone()
        accounts = conn.execute(
            "SELECT * FROM accounts WHERE status = 'connected' ORDER BY id").fetchall()
    finally:
        conn.close()

    # the brand's own content pillars drive gap detection (edited in Brand Brain)
    pillars = [p.strip() for p in ((brand["pillars"] if brand else "") or "").split(",") if p.strip()]
    if not pillars:
        pillars = CANONICAL_PILLARS
    gaps = _days_since_pillar(pillars)

    def account_for(fmt: str):
        pref = "linkedin" if fmt == "text" else "instagram"
        for a in accounts:
            if a["platform"] == pref:
                return a
        return accounts[0] if accounts else None

    seen: set[tuple] = set()
    recs: list[dict] = []

    def add(fmt: str, pillar: str, score: float, why: str):
        key = (fmt, pillar)
        if key in seen:
            return
        seen.add(key)
        acc = account_for(fmt)
        recs.append({
            "id": len(recs) + 1,
            "format": fmt,
            "pillar": pillar,
            "objective": _OBJECTIVE.get(pillar, "Engagement"),
            "title": _TITLES.get(pillar) or f"A fresh {pillar} idea for your audience",
            "topic": pillar,
            "platform": acc["platform"] if acc else "instagram",
            "account_id": acc["id"] if acc else None,
            "why": why,
            "score": round(score, 1),
        })

    # 1) double down on the strongest format + topic
    add(top_fmt, top_topic, 9.6,
        f"{top_fmt.title()}s are your strongest format ({top_fmt_score}/10) and {top_topic} "
        f"drives about {save_mult:.1f}× more saves than your average — combine the two.")

    # 2) fill the biggest content gap (among the brand's own pillars)
    gap_pillar = max(pillars, key=lambda p: gaps.get(p, 999))
    gap_days = gaps.get(gap_pillar, 999)
    gap_txt = f"in {gap_days} days" if gap_days < 900 else "yet"
    add(top_fmt, gap_pillar, 8.4,
        f"You haven't posted {gap_pillar} {gap_txt}. It's a gap in your mix — and {top_fmt}s "
        f"are the format most likely to land it.")

    # 3) an education carousel for leads
    add("carousel", "Investment Education", 7.7,
        "Educational carousels are your #2 save-driver and a strong lead magnet — a "
        "Golden-Visa explainer converts well.")

    # 4) an area-guide reel for shares
    add("reel", "Area Guides", 7.1,
        "Area guides generate the most shares for you. A short reel walking one community "
        "tends to travel furthest.")

    recs.sort(key=lambda r: r["score"], reverse=True)
    return recs[:limit]
