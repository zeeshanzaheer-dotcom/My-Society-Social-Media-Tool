"""Seed data. Enough to see the calendar, approvals, and publish log come alive
the moment the server starts — including one job scheduled in the past (so the
engine publishes it within seconds) and one aimed at a disconnected account (so
the failure/retry path is visible too)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from . import adapters, analytics
from .db import DB_PATH, get_conn, init_db, utcnow_iso


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def is_empty() -> bool:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) c FROM brands").fetchone()["c"] == 0
    finally:
        conn.close()


def seed_if_empty() -> None:
    init_db()
    if is_empty():
        _seed()


def reset_and_seed() -> None:
    conn = get_conn()
    try:
        for t in ("notifications", "people", "platform_engagements", "feed_comments", "feed_posts",
                  "post_metrics", "publish_jobs", "approvals", "post_versions", "posts", "accounts",
                  "brands", "workspaces"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()
    _seed()


def _seed() -> None:
    now = datetime.now(timezone.utc)
    conn = get_conn()
    try:
        ws = conn.execute("INSERT INTO workspaces (name, created_at) VALUES (?, ?)",
                          ("Allegiance", utcnow_iso())).lastrowid

        brand = conn.execute(
            "INSERT INTO brands (workspace_id, name, initials, color, voice, never_say, cta, "
            "audience, always_say, pillars, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ws, "Allegiance Real Estate", "AR", "#2B2230",
             "Premium, confident, educational, concise",
             "guaranteed returns, risk-free",
             "DM us to check your eligibility.",
             "International investors & UAE end-user buyers",
             "RERA permit number on listings",
             "Market Data,Investment Education,Area Guides,New Projects,News,Client Success",
             utcnow_iso()),
        ).lastrowid
        b2 = conn.execute(
            "INSERT INTO brands (workspace_id, name, initials, color, voice, never_say, cta, "
            "audience, always_say, pillars, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ws, "A-Living", "AL", "#0FB5A1", "Warm, lifestyle-led", "", "Book a viewing.",
             "Renters & young professionals", "", "Lifestyle,Community,Amenities", utcnow_iso()),
        ).lastrowid

        ig = conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) "
                          "VALUES (?,?,?,?,?)",
                          (brand, "instagram", "@allegiance.realestate", "connected", utcnow_iso())).lastrowid
        fb = conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) "
                          "VALUES (?,?,?,?,?)",
                          (brand, "facebook", "Allegiance Real Estate", "connected", utcnow_iso())).lastrowid
        li = conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) "
                          "VALUES (?,?,?,?,?)",
                          (brand, "linkedin", "Allegiance Real Estate", "connected", utcnow_iso())).lastrowid
        tt = conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) "
                          "VALUES (?,?,?,?,?)",
                          (brand, "tiktok", "@allegiance", "disconnected", None)).lastrowid
        tw = conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) "
                          "VALUES (?,?,?,?,?)",
                          (brand, "twitter", "@allegiance_ae", "connected", utcnow_iso())).lastrowid
        conn.execute("INSERT INTO accounts (brand_id, platform, handle, status, connected_at) VALUES (?,?,?,?,?)",
                     (b2, "instagram", "@a.living", "connected", utcnow_iso()))

        def post(account, fmt, title, caption, status):
            t = utcnow_iso()
            pid = conn.execute(
                "INSERT INTO posts (brand_id, account_id, format, title, caption, status, created_by, "
                "current_version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
                (brand, account, fmt, title, caption, status, "Amr", t, t),
            ).lastrowid
            conn.execute("INSERT INTO post_versions (post_id, version, title, caption, note, author, created_at) "
                         "VALUES (?,1,?,?,'Created','Amr',?)", (pid, title, caption, t))
            return pid

        def job(pid, account, platform, when, status="scheduled"):
            conn.execute(
                "INSERT INTO publish_jobs (post_id, account_id, platform, scheduled_at, status, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (pid, account, platform, _fmt(when), status, utcnow_iso()),
            )

        # a draft, an in-review item, an approved item, and scheduled items
        post(ig, "reel", "3 Dubai property myths investors still believe",
             "Everyone thinks you need AED 2M to start. Here's what the numbers say. DM us to check your eligibility.",
             "draft")

        p_review = post(li, "text", "Why Abu Dhabi waterfront may be the next growth cycle",
                        "Dubai waterfront is expensive. Abu Dhabi may be where the opportunity is moving next.",
                        "in_review")
        conn.execute("INSERT INTO approvals (post_id, action, actor, comment, created_at) VALUES (?,?,?,?,?)",
                     (p_review, "submitted", "Amr", "Ready for your review 🙏", utcnow_iso()))

        p_appr = post(ig, "carousel", "The Golden Visa, explained in 8 slides",
                      "AED 2M property. 10 years in the UAE. Here's exactly how it works. DM us to check your eligibility.",
                      "approved")
        conn.execute("INSERT INTO approvals (post_id, action, actor, comment, created_at) VALUES (?,?,?,?,?)",
                     (p_appr, "approved", "You", "", utcnow_iso()))

        # scheduled — one already due (auto-publishes on first tick), some future
        p_due = post(ig, "reel", "Market update — July DXB transactions", "July's numbers are in.", "scheduled")
        job(p_due, ig, "instagram", now - timedelta(minutes=1))

        p_soon = post(fb, "static", "Weekly news roundup", "This week in UAE property.", "scheduled")
        job(p_soon, fb, "facebook", now + timedelta(minutes=2))

        p_future = post(li, "text", "Investor insight: rental yields by area", "Where the yields are.", "scheduled")
        job(p_future, li, "linkedin", now + timedelta(hours=6))

        # a job aimed at the disconnected TikTok account — will fail, showing the error path
        p_fail = post(tt, "reel", "RAK opportunity", "90 minutes from Dubai.", "scheduled")
        job(p_fail, tt, "tiktok", now - timedelta(seconds=30))

        # --- history: past published posts WITH metrics, so analytics + recommendations
        # have real signal from the first screen ---
        plat_of = {ig: "instagram", fb: "facebook", li: "linkedin", tw: "twitter"}

        def hist(account, fmt, title, days_ago):
            dt = now - timedelta(days=days_ago, hours=random.randint(0, 12))
            ts = _fmt(dt)
            plat = plat_of[account]
            pid = conn.execute(
                "INSERT INTO posts (brand_id, account_id, format, title, caption, status, created_by, "
                "current_version, created_at, updated_at) VALUES (?,?,?,?,?, 'published','Amr',1,?,?)",
                (brand, account, fmt, title, title, ts, ts),
            ).lastrowid
            conn.execute("INSERT INTO post_versions (post_id, version, title, caption, note, author, created_at) "
                         "VALUES (?,1,?,?,'Created','Amr',?)", (pid, title, title, ts))
            conn.execute(
                "INSERT INTO publish_jobs (post_id, account_id, platform, scheduled_at, status, attempts, "
                "platform_post_id, platform_url, published_at, created_at) VALUES (?,?,?,?, 'published',1,?,?,?,?)",
                (pid, account, plat, ts, f"seed{pid}", f"https://{plat}.com/p/seed{pid}", ts, ts),
            )
            pillar = analytics.pillar_for(title)
            m = analytics._mock_metrics(fmt, pillar)
            conn.execute(
                "INSERT INTO post_metrics (post_id, account_id, platform, format, pillar, reach, impressions, "
                "engagements, likes, comments, shares, saves, video_views, collected_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, account, plat, fmt, pillar, m["reach"], m["impressions"], m["engagements"],
                 m["likes"], m["comments"], m["shares"], m["saves"], m["video_views"], ts),
            )

        history = [
            (ig, "reel", "Dubai just posted record July transaction numbers"),
            (ig, "reel", "3 market numbers every Dubai investor should know"),
            (li, "text", "Rental yields by area: the data investors miss"),
            (ig, "carousel", "The Golden Visa, explained in 8 slides"),
            (ig, "carousel", "Mortgage vs cash: the investor math"),
            (ig, "carousel", "5 Dubai investment myths, busted"),
            (ig, "reel", "Saadiyat Island: a 60-second area guide"),
            (ig, "reel", "Palm Jumeirah waterfront, in one minute"),
            (ig, "reel", "RAK: the community 90 minutes from Dubai"),
            (fb, "static", "July DXB transactions at a glance"),
            (ig, "static", "Price per sqft, by community"),
            (fb, "static", "This week in UAE property news"),
            (ig, "carousel", "New Yas Island off-plan launch — first look"),
            (ig, "reel", "The ROI myth most investors still believe"),
            (ig, "static", "Marina vs Downtown: a quick area guide"),
            (li, "text", "What the latest transaction data means for buyers"),
            (tw, "text", "Dubai rents climbed again in Q3 — the communities still offering real value 🧵"),
            (tw, "static", "Off-plan is now ~60% of Dubai transactions. The full breakdown 👇"),
        ]
        for i, (acc, fmt, title) in enumerate(history):
            hist(acc, fmt, title, days_ago=i + 1)

        # --- network feed: cross-platform posts from people in your network ---
        feed = [
            ("Zeeshan Zaheer", "zeeshan", "ZZ", "#6E62D6", "linkedin",
             "Testing Wolfie to plan our content this quarter — the “what should I post next” recs are scary good. 🐺", "", 12, 2, 3, 4),
            ("Amr Khaled", "amr.realty", "AK", "#6E9E8B", "instagram",
             "Just closed a Downtown 2BR — third this month. The market is moving. 🏙️", "skyline", 84, 9, 12, 11),
            ("Layla Hassan", "layla.homes", "LH", "#B98A34", "instagram",
             "Sunset from a Palm Jumeirah listing. This view sells itself.", "sunset", 210, 24, 18, 26),
            ("Sara Nasser", "sara.property", "SN", "#574BC0", "linkedin",
             "Reminder: the Golden Visa threshold is AED 2M in property. Getting a LOT of questions this week — happy to help.", "", 46, 7, 9, 42),
            ("Nadia Aziz", "nadia.rak", "NA", "#C25B60", "tiktok",
             "RAK is 90 minutes from Dubai and roughly half the price. Made a quick reel on why it's on my radar.", "video", 132, 15, 21, 68),
            ("Omar Farouq", "omar.invests", "OF", "#8A8A93", "linkedin",
             "Abu Dhabi waterfront yields are quietly outperforming a few Dubai communities. Thread with the numbers 👇", "", 58, 11, 14, 95),
            ("Yusuf Rahman", "yusuf.offplan", "YR", "#6E9E8B", "instagram",
             "New Yas Island launch just dropped — first look at the floor plans.", "project", 73, 6, 8, 140),
            ("Hassan Ali", "hassan.market", "HA", "#574BC0", "instagram",
             "July DXB transactions hit a new high. Chart below — save it for your next investor chat.", "chart", 99, 19, 16, 190),
            ("A-Living", "a.living", "AL", "#6E9E8B", "instagram",
             "Community pool day at our Saadiyat residences ☀️ swipe for the amenities.", "pool", 64, 3, 5, 240),
            ("Fatima Noor", "fatima.leads", "FN", "#6E62D6", "linkedin",
             "3 things first-time overseas buyers always miss. Save this before your next viewing.", "", 41, 8, 6, 320),
            ("Khalid Mansoor", "khalid.uae", "KM", "#2B2230", "twitter",
             "Dubai rents climbed again this quarter — thread on the communities still offering real value 👇", "", 55, 14, 9, 33),
            ("Property Finder", "propertyfinder", "PF", "#6E9E8B", "twitter",
             "New data: off-plan is now ~60% of Dubai transactions. Full breakdown in our latest report.", "chart", 128, 41, 22, 150),
            ("Client A", "clienta", "CA", "#B98A34", "facebook",
             "Big thanks to the Allegiance team for a smooth handover this week! 🔑", "", 22, 1, 4, 400),
        ]
        fids = []
        for (nm, hd, ini, col, plat, txt, media, lk, rp, cc, mins) in feed:
            fid = conn.execute(
                "INSERT INTO feed_posts (author_name, author_handle, author_initials, author_color, platform, "
                "text, media, likes, reposts, comments_count, liked, reposted, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,0,0,?)",
                (nm, hd, ini, col, plat, txt, media, lk, rp, cc, _fmt(now - timedelta(minutes=mins))),
            ).lastrowid
            fids.append(fid)

        def cmt(fid, author, ini, text, mins):
            conn.execute(
                "INSERT INTO feed_comments (feed_post_id, author, initials, text, created_at) VALUES (?,?,?,?,?)",
                (fid, author, ini, text, _fmt(now - timedelta(minutes=mins))),
            )
        cmt(fids[1], "Sara Nasser", "SN", "Congrats Amr! Downtown is on fire right now.", 8)
        cmt(fids[1], "Layla Hassan", "LH", "Which tower? 👀", 6)
        cmt(fids[2], "Omar Farouq", "OF", "That view is unreal.", 20)
        cmt(fids[4], "Yusuf Rahman", "YR", "RAK is underrated — been saying this for months.", 50)

        # --- people directory (who you follow + who to follow) ---
        people = [
            ("amr.realty", "Amr Khaled", "AK", "#6E9E8B", "Closing Dubai deals daily.", 1, 0),
            ("layla.homes", "Layla Hassan", "LH", "#B98A34", "Luxury listings · Palm & Emirates Hills.", 1, 0),
            ("sara.property", "Sara Nasser", "SN", "#574BC0", "Golden Visa & residency advisor.", 1, 0),
            ("nadia.rak", "Nadia Aziz", "NA", "#C25B60", "RAK & Northern Emirates specialist.", 1, 0),
            ("omar.invests", "Omar Farouq", "OF", "#8A8A93", "Yield-focused property investor.", 1, 0),
            ("a.living", "A-Living", "AL", "#6E9E8B", "Community living by Allegiance.", 1, 0),
            ("hassan.market", "Hassan Ali", "HA", "#574BC0", "Market data & transaction trends.", 0, 1),
            ("fatima.leads", "Fatima Noor", "FN", "#6E62D6", "Helping first-time overseas buyers.", 0, 1),
            ("khalid.uae", "Khalid Mansoor", "KM", "#2B2230", "UAE rental market watcher · posts on X.", 0, 1),
            ("dubailand", "Dubai Land Dept", "DL", "#574BC0", "Official UAE real-estate regulator.", 0, 1),
            ("propertyfinder", "Property Finder", "PF", "#6E9E8B", "The UAE's property portal.", 0, 1),
            ("mo.realty", "Mo Real Estate", "MR", "#B98A34", "Off-plan & investment brokerage.", 0, 1),
        ]
        for (h, n, ini, col, bio, fol, sug) in people:
            conn.execute("INSERT INTO people (handle, name, initials, color, bio, following, suggested) "
                         "VALUES (?,?,?,?,?,?,?)", (h, n, ini, col, bio, fol, sug))

        # --- notifications (network activity directed at you) ---
        notifs = [
            ("like", "Layla Hassan", "LH", "#B98A34", "liked your post “Testing Wolfie to plan our content…”", 0, 7),
            ("follow", "Omar Farouq", "OF", "#8A8A93", "started following you", 0, 22),
            ("comment", "Sara Nasser", "SN", "#574BC0", "replied: “The recs really are good — which plan are you on?”", 0, 35),
            ("mention", "Amr Khaled", "AK", "#6E9E8B", "mentioned you in a comment", 1, 90),
            ("like", "Nadia Aziz", "NA", "#C25B60", "and 11 others liked your reel", 1, 140),
            ("system", "Wolfie", "🐺", "#6E62D6", "Your “Golden Visa” carousel is trending in your network 📈", 1, 200),
        ]
        for (ty, an, ai, ac, tx, rd, mins) in notifs:
            conn.execute("INSERT INTO notifications (type, actor_name, actor_initials, actor_color, text, read, created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (ty, an, ai, ac, tx, rd, _fmt(now - timedelta(minutes=mins))))

        # --- cross-platform engagement: a few you've already made in the unified
        # feed, each mirrored back onto the post's origin platform ---
        # (fid index, origin platform, action, feed_post flag column)
        seed_eng = [
            (fids[1], "instagram", "like", "liked", 5),
            (fids[4], "tiktok", "like", "liked", 12),
            (fids[10], "twitter", "like", "liked", 18),
            (fids[5], "linkedin", "repost", "reposted", 25),
        ]
        for (fid, plat, action, flag_col, mins) in seed_eng:
            conn.execute(f"UPDATE feed_posts SET {flag_col} = 1 WHERE id = ?", (fid,))
            mirror = adapters.mirror_engagement(plat, action, 1, ref=str(fid))
            conn.execute(
                "INSERT INTO platform_engagements (feed_post_id, platform, action, delta, mirrored, detail, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (fid, plat, action, 1, 1 if mirror["mirrored"] else 0, mirror["detail"],
                 _fmt(now - timedelta(minutes=mins))),
            )

        conn.commit()
    finally:
        conn.close()
