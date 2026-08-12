# Wolfie — runnable MVP

An operational slice of the Wolfie *AI Social Media Growth OS*: the **Calendar → Approvals → Publish** loop, working end to end.

- **Backend** — FastAPI + SQLite (stdlib, zero DB setup) + a background **publish engine** that fires scheduled jobs, retries failures, and records results.
- **Frontend** — React (Vite + TypeScript).
- **Integrations are mock-by-default.** Social publishing runs on realistic mock adapters and AI content on a mock generator — the whole app runs with **no credentials**. Real Claude / Meta / LinkedIn plug in behind clean seams (see `.env`).

## What actually works

- Create a draft (write it, or **Generate with AI** — mock by default).
- **Submit → Approve / Request changes** (role-gated: Creator vs Manager), with an audit trail and version history.
- **Schedule** an approved post (or *Publish now*). The background engine (ticks every 3s) claims due jobs, calls the platform **adapter** via one `publish_post()` interface, retries with backoff (up to 3×), and writes back a platform post-ID + URL — or an error.
- Watch it happen live on the **Calendar** and **Publish log** (the UI polls every 4s).
- Seeded so it's alive immediately: one job publishes within seconds, one aimed at a disconnected TikTok account **fails on purpose** so you can see the error/retry path.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**

Neither ships with Windows by default — install from [python.org](https://www.python.org/downloads/) and [nodejs.org](https://nodejs.org/), or via winget:

```powershell
winget install Python.Python.3.12 OpenJS.NodeJS.LTS
```

(Open a **new** terminal after installing so PATH updates.)

## Run it (two terminals)

**Terminal 1 — backend:**

```powershell
cd wolfie\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API is now at http://localhost:8000 (docs at http://localhost:8000/docs).

**Terminal 2 — frontend:**

```powershell
cd wolfie\frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

> On macOS/Linux, activate the venv with `source .venv/bin/activate` instead.

## Turning on real integrations

Copy `backend/.env.example` to `backend/.env` and set what you need:

- **Real AI copy:** `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=…` (and `pip install anthropic`). Model via `AI_MODEL` (default `claude-opus-5`).
- **See retries/failures:** `WOLFIE_MOCK_FAILURE_RATE=0.15`.
- **Real Instagram publishing (implemented):** the `InstagramAdapter` in `app/adapters.py` does the real Meta Graph API flow (create media container → publish; reels are polled until processed). It activates automatically once **both** `META_ACCESS_TOKEN` and `META_IG_USER_ID` are set in `.env` — otherwise Instagram stays on the mock adapter. Instagram requires a **public media URL**, so set each post's `media_url` (a field on the Create form) or a `META_DEFAULT_IMAGE_URL` / `META_DEFAULT_VIDEO_URL` fallback. What's on *your* side: an Instagram Business account + a Meta app with `instagram_content_publish` + Advanced Access via App Review + a long-lived token and the IG Business account id. **Check your setup without publishing** at `GET /api/integrations/meta/check` (also shown as a badge on the Publish log screen). Entering the token is something you do in `.env` — Wolfie never asks you to paste it into the UI.

## Project layout

```
backend/
  app/
    main.py        FastAPI app + startup (seed, start scheduler)
    db.py          SQLite schema + helpers
    api.py         all endpoints + approval state machine
    scheduler.py   the background publish engine
    adapters.py    platform adapters behind one publish_post()
    ai.py          content generation (mock | anthropic)
    seed.py        demo data
frontend/
  src/App.tsx      the UI (Calendar / Approvals / Create / Publish log)
  src/api.ts       typed API client
```

## One-process production mode (optional)

```powershell
cd wolfie\frontend; npm run build      # emits frontend/dist
cd ..\backend; uvicorn app.main:app --port 8000
```

FastAPI then serves the built UI at http://localhost:8000 alongside the API.

## Deploy — backend on Railway, frontend on Vercel

The backend is a long-running service (background publish scheduler + a SQLite DB it writes to), so it needs a real host — **Railway** — while the static frontend goes on **Vercel**. Config files for both are already in the repo.

**1. Backend → Railway**

- New project → *Deploy from GitHub repo* → this repo.
- Open the service → **Settings → Root Directory → `backend`** (this is the key step — without it the builder sees both `frontend/` and `backend/` at the repo root and fails with *"could not determine how to build the app"*).
- Redeploy. `backend/railway.json` supplies the start command (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`); `requirements.txt` is auto-installed.
- Under **Settings → Networking**, *Generate Domain*. Copy that URL (e.g. `https://my-society-backend.up.railway.app`).
- *(Optional)* add a **Volume** mounted at `/data` and set `WOLFIE_DB_PATH=/data/wolfie.db` so data survives redeploys. Without it, the demo data simply re-seeds on each deploy.

**2. Frontend → Vercel**

- Import the repo → **Root Directory → `frontend`** (Vercel auto-detects Vite).
- Edit `frontend/vercel.json` → replace the destination host with your Railway URL from step 1, keeping the `/api/:path*` suffix. Commit + push; Vercel redeploys.
- The rewrite proxies the app's `/api` calls to Railway, so the browser stays same-origin (no CORS).

> Runs on mock adapters with dummy data out of the box — no credentials required. On Vercel-serverless the backend also works (SQLite on `/tmp`, scheduler auto-disabled) but data is ephemeral; Railway is preferred so the publish scheduler actually runs.

## Reset

The **Reset demo** button (top-right) re-seeds the database. Or delete `backend/wolfie.db*` and restart.
