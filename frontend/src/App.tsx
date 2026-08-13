import { useEffect, useRef, useState } from "react";
import { api, Account, Brand, Job, Post, FeedPost, FeedComment, Person, Notification } from "./api";

/* ---------- date helpers ---------- */
const asDate = (iso: string) => new Date(iso.endsWith("Z") ? iso : iso + "Z");
const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fmtTime = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
function localInputDefault(hoursAhead = 1) {
  const d = new Date(Date.now() + hoursAhead * 3600_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

type Toast = { msg: string; bad?: boolean } | null;

export default function App() {
  const [tab, setTab] = useState<"home" | "ideas" | "calendar" | "approvals" | "create" | "publish" | "analytics" | "analyst" | "brand" | "connectors" | "profile">("home");
  const [role, setRole] = useState<"Manager" | "Creator">("Manager");
  const [tick, setTick] = useState(0);
  const [toastMsg, setToastRaw] = useState<Toast>(null);
  const [st, setSt] = useState<any>(null);
  const [menu, setMenu] = useState<string | null>(null);

  const bump = () => setTick((t) => t + 1);
  const toast = (msg: string, bad = false) => {
    setToastRaw({ msg, bad });
    setTimeout(() => setToastRaw(null), 2600);
  };
  // wrap an async action: run, toast errors, then refresh
  const run = async (fn: () => Promise<any>, ok?: string) => {
    try {
      await fn();
      if (ok) toast(ok);
      bump();
    } catch (e: any) {
      toast(e.message || "Something went wrong", true);
    }
  };

  useEffect(() => {
    api.state().then(setSt).catch(() => {});
  }, [tick]);

  // poll so the background publish engine's changes show up live
  useEffect(() => {
    const id = setInterval(bump, 4000);
    return () => clearInterval(id);
  }, []);

  // close any open top-right menu when clicking elsewhere
  useEffect(() => {
    const h = () => setMenu(null);
    document.addEventListener("click", h);
    return () => document.removeEventListener("click", h);
  }, []);

  const nav = (t: any) => { setTab(t); setMenu(null); };

  if (!st) return <div className="app"><div className="empty">Connecting to Wolfie…</div></div>;

  const brand: Brand = st.brand;
  const accounts: Account[] = st.accounts;
  const inReview = st.counts.in_review as number;

  const ctx = { tick, role, toast, run, accounts, brand };

  // the former Tools dropdown, now a left sidebar on desktop
  const sideItems: { key: any; ico: string; label: string; badge?: number }[] = [
    { key: "calendar", ico: "📅", label: "Calendar" },
    { key: "approvals", ico: "✅", label: "Approvals", badge: inReview },
    { key: "publish", ico: "🚀", label: "Publish log" },
    { key: "analytics", ico: "📊", label: "Analytics" },
    { key: "analyst", ico: "🤖", label: "AI Analyst" },
    { key: "connectors", ico: "🔌", label: "Connectors" },
    { key: "brand", ico: "🧠", label: "Brand Brain" },
  ];

  return (
    <div className="app">
      <div className="top">
        <div className="brand-logo solo" onClick={() => nav("home")} title="Home">
          <svg className="wmark" viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" aria-label="Wolfie">
            <path d="M18 24 L37 78 L50 47 L63 78 L82 24" />
          </svg>
        </div>
        <div className="spacer" />
        <div className="menus">
          <div className="create-menu-m">
            <NavMenu id="create" label="Create" tab={tab} nav={nav} menu={menu} setMenu={setMenu}
              items={[
                { key: "ideas", ico: "💡", label: "Ideas & Trends", sub: "Turn signals into drafts" },
                { key: "create", ico: "✨", label: "Compose", sub: "Draft & generate a post" },
              ]} />
          </div>
          <div className="tools-menu-m">
            <NavMenu id="tools" label="Tools" tab={tab} nav={nav} menu={menu} setMenu={setMenu}
              items={[
                { key: "calendar", ico: "📅", label: "Calendar" },
                { key: "approvals", ico: "✅", label: "Approvals", badge: inReview },
                { key: "publish", ico: "🚀", label: "Publish log" },
                { key: "analytics", ico: "📊", label: "Analytics" },
                { key: "analyst", ico: "🤖", label: "AI Analyst", sub: "Ask about your performance" },
                { key: "connectors", ico: "🔌", label: "Connectors", sub: "Channels & integrations" },
                { key: "brand", ico: "🧠", label: "Brand Brain" },
              ]} />
          </div>
        </div>
        <div className="bellwrap" onClick={(e) => e.stopPropagation()}>
          <button className="bell" title="Notifications" onClick={() => setMenu(menu === "notifs" ? null : "notifs")}>
            🔔{st.unread > 0 && <span className="bell-badge">{st.unread > 9 ? "9+" : st.unread}</span>}
          </button>
          {menu === "notifs" && <NotificationsDropdown bump={bump} unread={st.unread} />}
        </div>
        <button className={"profbtn" + (tab === "profile" ? " on" : "")} title="My Profile — Zeeshan Zaheer" onClick={() => setTab("profile")}>
          <span className="profava">ZZ</span>
        </button>
      </div>

      <div className="layout">
        <aside className="sidenav">
          {sideItems.map((it) => (
            <button key={it.key} className={"sideitem" + (tab === it.key ? " active" : "")} onClick={() => nav(it.key)}>
              <span className="side-ico">{it.ico}</span>
              <span className="side-txt">{it.label}</span>
              {it.badge ? <span className="side-badge">{it.badge}</span> : null}
            </button>
          ))}
        </aside>
        <main className="main">
          {tab === "home" && <HomeView {...ctx} goTab={setTab} following={st.following || []} />}
          {tab === "ideas" && <IdeasView {...ctx} goTab={setTab} />}
          {tab === "calendar" && <CalendarView {...ctx} />}
          {tab === "approvals" && <ApprovalsView {...ctx} goCreate={() => setTab("create")} />}
          {tab === "create" && <CreateView {...ctx} />}
          {tab === "publish" && <PublishView {...ctx} />}
          {tab === "analytics" && <AnalyticsView {...ctx} />}
          {tab === "analyst" && <AnalystView {...ctx} />}
          {tab === "brand" && <BrandBrainView {...ctx} />}
          {tab === "connectors" && <ConnectorsView {...ctx} />}
          {tab === "profile" && <ProfileView {...ctx} goTab={setTab} />}
        </main>
        <RightRail tick={tick} tab={tab} goTab={setTab} />
      </div>

      {tab !== "analyst" && <AskBubble />}
      {tab !== "analyst" && <ComposeFab bump={bump} toast={toast} />}
      {toastMsg &&<div className={"toast" + (toastMsg.bad ? " bad" : "")}>{toastMsg.msg}</div>}
    </div>
  );
}

/* ================= Right rail (desktop) — suggestions, trends, popular feed ================= */
function RightRail({ tick, goTab }: { tick: number; tab: string; goTab: (t: any) => void }) {
  const [feed, setFeed] = useState<FeedPost[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [an, setAn] = useState<any>(null);
  useEffect(() => {
    api.feed().then(setFeed).catch(() => {});
    api.recommendations().then(setRecs).catch(() => {});
    api.analytics().then(setAn).catch(() => {});
  }, [tick]);
  const popular = [...feed].sort((a, b) => (b.likes + b.reposts) - (a.likes + a.reposts)).slice(0, 5);
  const topics = (an?.topics || []) as any[];
  const maxTopic = Math.max(1, ...topics.map((t) => t.score));

  return (
    <aside className="rightnav">
      <div className="railsec card">
        <div className="railhead">✨ Content suggestions</div>
        {recs.slice(0, 3).map((r, i) => (
          <button className="recitem" key={i} onClick={() => goTab("ideas")}>
            <div className="recchips"><span className="pill draft">{r.pillar}</span><span className="scorepill">{r.score}</span></div>
            <b className="rectitle">{r.title}</b>
            <div className="tiny recwhy">{r.why}</div>
          </button>
        ))}
        {recs.length === 0 && <div className="tiny" style={{ padding: "6px 10px" }}>Publish a few posts to unlock suggestions.</div>}
      </div>

      <div className="railsec card">
        <div className="railhead">📈 Trending topics</div>
        {topics.slice(0, 5).map((t) => (
          <div className="barrow" key={t.pillar}>
            <div className="n">{t.pillar}</div>
            <div className="bar"><div className="barfill coral" style={{ width: `${(t.score / maxTopic) * 100}%` }} /></div>
            <div className="v">{t.score}</div>
          </div>
        ))}
        {topics.length === 0 && <div className="tiny" style={{ padding: "6px 10px" }}>No signal yet — publish to learn.</div>}
      </div>

      <div className="railsec card">
        <div className="railhead">Popular in your workspace</div>
        {popular.map((p) => (
          <button className="popitem" key={p.id} onClick={() => goTab("home")}>
            <div className="avatar-xs" style={{ background: p.author_color }}>{p.author_initials}</div>
            <div className="popbody">
              <b>{p.author_name}</b>
              <div className="poptext">{p.text}</div>
              <div className="tiny">❤️ {p.likes} · 🔁 {p.reposts}</div>
            </div>
          </button>
        ))}
        {popular.length === 0 && <div className="tiny" style={{ padding: "6px 10px" }}>No posts yet.</div>}
      </div>
    </aside>
  );
}

/* ================= Inline composer (desktop) — X-style create-post box ================= */
function InlineComposer({ toast, onPosted }: { toast: (m: string, bad?: boolean) => void; onPosted: () => void }) {
  const [text, setText] = useState("");
  const [media, setMedia] = useState<string[]>([]);
  const [plats, setPlats] = useState<string[]>(["linkedin"]);
  const [busy, setBusy] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const imgRef = useRef<HTMLInputElement>(null);
  const vidRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!plusOpen) return;                          // close the +menu on any outside click
    const h = () => setPlusOpen(false);
    document.addEventListener("click", h);
    return () => document.removeEventListener("click", h);
  }, [plusOpen]);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    Array.from(list).slice(0, 6).forEach((f) => {
      if (f.size > 12 * 1024 * 1024) { toast(`${f.name} is over 12MB — skipped`, true); return; }
      const r = new FileReader();
      r.onload = () => setMedia((m) => (m.length >= 6 ? m : [...m, String(r.result)]));
      r.readAsDataURL(f);
    });
  };
  const togglePlat = (p: string) => setPlats((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));
  const canPost = (text.trim() !== "" || media.length > 0) && plats.length > 0 && !busy;
  const post = async () => {
    if (!canPost) return;
    setBusy(true);
    try {
      await api.feedCreate(text.trim(), media.length ? JSON.stringify(media) : "", plats);
      setText(""); setMedia([]);
      toast(`Posted to ${plats.length} platform${plats.length > 1 ? "s" : ""}`);
      onPosted();
    } catch (e: any) { toast(e.message || "Couldn't post", true); }
    finally { setBusy(false); }
  };

  return (
    <div className="composer card composer-inline">
      <div className="avatar-sm" style={{ background: "#6E62D6" }}>ZZ</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <textarea
          className="citext" placeholder="What's happening?" rows={1} value={text}
          onChange={(e) => { setText(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 200) + "px"; }}
        />
        {media.length > 0 && (
          <div className={"composemedia n" + Math.min(media.length, 4)}>
            {media.map((u, i) => (
              <div className="cmthumb" key={i}>
                {isVideoUrl(u) ? <video src={u} /> : <img src={u} alt="" />}
                <button className="cmx" title="Remove" onClick={() => setMedia((m) => m.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
          </div>
        )}
        <div className="cbar">
          <div className="menu-wrap" onClick={(e) => e.stopPropagation()}>
            <button className={"cplusbtn" + (plusOpen ? " on" : "")} title="Add media & platforms" onClick={() => setPlusOpen((v) => !v)}>+</button>
            {plusOpen && (
              <div className="dropdown cplus-dd">
                <div className="dd-label">Add media</div>
                <button className="dd-item" onClick={() => imgRef.current?.click()}><span className="dd-ico">🖼</span><span className="dd-txt">Photos<small>One or more images</small></span></button>
                <button className="dd-item" onClick={() => vidRef.current?.click()}><span className="dd-ico">🎬</span><span className="dd-txt">Video</span></button>
                <div className="dd-sep" />
                <div className="dd-label">Post to</div>
                <div className="cplatrow" style={{ padding: "2px 8px 8px" }}>
                  {ALL_PLATFORMS.map((p) => (
                    <button key={p} className={"cplat" + (plats.includes(p) ? " on" : "")} onClick={() => togglePlat(p)}>
                      <span className={`acc ${p}`} style={{ width: 18, height: 18, borderRadius: 5 }}><PlatSvg p={p} size={12} /></span>
                      {PLAT_LABEL[p] || p}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="cbar-right">
            <span className="tiny">{plats.length ? `${plats.length} platform${plats.length > 1 ? "s" : ""}` : "Pick a platform"}</span>
            <button className="btn btn-primary" disabled={!canPost} onClick={post}>{busy ? "Posting…" : "Post"}</button>
          </div>
        </div>
        <input ref={imgRef} type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files); e.currentTarget.value = ""; }} />
        <input ref={vidRef} type="file" accept="video/*" hidden onChange={(e) => { addFiles(e.target.files); e.currentTarget.value = ""; }} />
      </div>
    </div>
  );
}

/* ================= Compose FAB — create a post (media + platforms), mobile ================= */
function ComposeFab({ bump, toast }: { bump: () => void; toast: (m: string, bad?: boolean) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [media, setMedia] = useState<string[]>([]);      // data URLs (images and/or a video)
  const [plats, setPlats] = useState<string[]>(["linkedin"]);
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLInputElement>(null);
  const vidRef = useRef<HTMLInputElement>(null);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    Array.from(list).slice(0, 6).forEach((f) => {
      if (f.size > 12 * 1024 * 1024) { toast(`${f.name} is over 12MB — skipped`, true); return; }
      const r = new FileReader();
      r.onload = () => setMedia((m) => (m.length >= 6 ? m : [...m, String(r.result)]));
      r.readAsDataURL(f);
    });
  };
  const togglePlat = (p: string) => setPlats((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));
  const canPost = (text.trim() !== "" || media.length > 0) && plats.length > 0 && !busy;
  const post = async () => {
    if (!canPost) return;
    setBusy(true);
    try {
      await api.feedCreate(text.trim(), media.length ? JSON.stringify(media) : "", plats);
      setText(""); setMedia([]); setPlats(["linkedin"]); setOpen(false);
      toast(`Posted to ${plats.length} platform${plats.length > 1 ? "s" : ""}`);
      bump();
    } catch (e: any) { toast(e.message || "Couldn't post", true); }
    finally { setBusy(false); }
  };

  return (
    <>
      {open && (
        <div className="composeoverlay" onClick={() => !busy && setOpen(false)}>
          <div className="composecard" onClick={(e) => e.stopPropagation()}>
            <div className="composehead"><b>Create a post</b><button className="askclose" onClick={() => setOpen(false)} title="Close">✕</button></div>
            <div className="composebody">
              <div className="composerow">
                <div className="avatar-sm" style={{ background: "#6E62D6" }}>ZZ</div>
                <textarea autoFocus placeholder="What's happening across your network?" value={text} onChange={(e) => setText(e.target.value)} rows={3} />
              </div>

              {media.length > 0 && (
                <div className={"composemedia n" + Math.min(media.length, 4)}>
                  {media.map((u, i) => (
                    <div className="cmthumb" key={i}>
                      {isVideoUrl(u) ? <video src={u} /> : <img src={u} alt="" />}
                      <button className="cmx" title="Remove" onClick={() => setMedia((m) => m.filter((_, j) => j !== i))}>✕</button>
                    </div>
                  ))}
                </div>
              )}

              <div className="composetools">
                <button className="ctoolbtn" onClick={() => imgRef.current?.click()}>🖼 Photo(s)</button>
                <button className="ctoolbtn" onClick={() => vidRef.current?.click()}>🎬 Video</button>
                <input ref={imgRef} type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files); e.currentTarget.value = ""; }} />
                <input ref={vidRef} type="file" accept="video/*" hidden onChange={(e) => { addFiles(e.target.files); e.currentTarget.value = ""; }} />
              </div>

              <div className="composeplats">
                <div className="tiny" style={{ fontWeight: 800, marginBottom: 8 }}>Post to</div>
                <div className="cplatrow">
                  {ALL_PLATFORMS.map((p) => (
                    <button key={p} className={"cplat" + (plats.includes(p) ? " on" : "")} onClick={() => togglePlat(p)}>
                      <span className={`acc ${p}`} style={{ width: 18, height: 18, borderRadius: 5 }}><PlatSvg p={p} size={12} /></span>
                      {PLAT_LABEL[p] || p}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="composefoot">
              <span className="tiny">{plats.length ? `Cross-posting to ${plats.length}` : "Pick at least one platform"}</span>
              <button className="btn btn-primary" disabled={!canPost} onClick={post}>{busy ? "Posting…" : "Post"}</button>
            </div>
          </div>
        </div>
      )}
      <button className="composefab" title="Create a post" onClick={() => setOpen(true)} aria-label="Create a post">
        <svg viewBox="0 0 24 24" width="27" height="27" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
      </button>
    </>
  );
}

/* ================= floating AI chat bubble (opens the Analyst anywhere) ================= */
function AskBubble() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<{ role: "user" | "ai"; text: string; provider?: string }[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ(""); setBusy(true);
    try {
      const r = await api.analyst(text);
      setMsgs((m) => [...m, { role: "ai", text: r.answer, provider: r.provider }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "ai", text: e.message || "Something went wrong.", provider: "error" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {open && (
        <div className="askpanel">
          <div className="askhead">
            <div><b>🤖 AI Analyst</b><div className="tiny">Ask about your performance</div></div>
            <button className="askclose" onClick={() => setOpen(false)} title="Close">✕</button>
          </div>
          <div className="askbody">
            {msgs.length === 0 && (
              <div className="askhi">Hi — I'm your analyst. Ask me what's working, what to post next, or which format wins.</div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={"amsg " + m.role}>
                {m.role === "ai" && <div className="analyst-ava sm">🤖</div>}
                <div className="abubble">
                  {renderMd(m.text)}
                  {m.role === "ai" && m.provider && m.provider !== "error" && (
                    <div className="tiny" style={{ marginTop: 6, opacity: 0.6 }}>via {m.provider === "anthropic" ? "Claude" : "built-in analyst"}</div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="amsg ai"><div className="analyst-ava sm">🤖</div><div className="abubble analyst-typing">Analysing…</div></div>}
            {msgs.length === 0 && (
              <div className="achips" style={{ marginTop: 10 }}>
                {ANALYST_SUGGESTIONS.map((s) => <button key={s} className="achip" disabled={busy} onClick={() => ask(s)}>{s}</button>)}
              </div>
            )}
          </div>
          <div className="abar">
            <input placeholder="Ask about your performance…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask(q)} />
            <button className="btn btn-primary btn-sm" disabled={busy || !q.trim()} onClick={() => ask(q)}>Ask</button>
          </div>
        </div>
      )}
      <button className={"askfab" + (open ? " on" : "")} onClick={() => setOpen((o) => !o)} title="Ask the AI Analyst">
        {open ? "✕" : "🤖"}
      </button>
    </>
  );
}

function icon(p: string) {
  return ({ instagram: "◎", facebook: "f", linkedin: "in", tiktok: "♪", twitter: "𝕏", youtube: "▸" } as Record<string, string>)[p] ?? "?";
}
function platName(p: string) {
  return ({ instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", tiktok: "TikTok", twitter: "X (Twitter)", youtube: "YouTube", wolfie: "your Wolfie network" } as Record<string, string>)[p] ?? p;
}
// The full set of channels the filter rows always offer, so every platform is
// selectable even when it currently has no posts (Facebook on Home, X on Profile).
const ALL_PLATFORMS = ["instagram", "facebook", "linkedin", "tiktok", "twitter"];
// Short filter-pill labels (the user's wording).
const PLAT_LABEL: Record<string, string> = { instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", tiktok: "TikTok", twitter: "Twitter", youtube: "YouTube" };
// Real brand marks (single-path logos) so the pills/badges show the correct icon.
const BRAND_PATHS: Record<string, string> = {
  facebook: "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.628-5.373-12-12-12s-12 5.372-12 12c0 5.628 3.874 10.35 9.101 11.647Z",
  instagram: "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163C8.741 0 8.332.014 7.052.072 2.695.272.273 2.69.073 7.052.014 8.332 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.332 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z",
  linkedin: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z",
  tiktok: "M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z",
  twitter: "M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.931ZM17.61 20.644h2.039L6.486 3.24H4.298Z",
};
function PlatSvg({ p, size = 12 }: { p: string; size?: number }) {
  const d = BRAND_PATHS[p];
  if (!d) return <>{icon(p)}</>;
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true" style={{ display: "block" }}><path d={d} /></svg>;
}

// Platform filter as a single dropdown (All Platforms + every social network).
function PlatformFilter({ plat, setPlat }: { plat: string; setPlat: (p: string) => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const h = () => setOpen(false);
    document.addEventListener("click", h);
    return () => document.removeEventListener("click", h);
  }, [open]);
  const opts = ["all", ...ALL_PLATFORMS];
  const tile = (p: string, size: number) =>
    p === "all"
      ? <span className="platf-all" style={{ width: size + 6, height: size + 6 }}>🌐</span>
      : <span className={`acc ${p}`} style={{ width: size + 6, height: size + 6, borderRadius: 5 }}><PlatSvg p={p} size={size} /></span>;
  return (
    <div className="platfilter">
      <div className="menu-wrap" onClick={(e) => e.stopPropagation()}>
        <button className={"platfbtn" + (open ? " on" : "")} onClick={() => setOpen((v) => !v)}>
          {tile(plat, 13)}
          <span>{plat === "all" ? "All Platforms" : (PLAT_LABEL[plat] || plat)}</span>
          <span className="chev">▾</span>
        </button>
        {open && (
          <div className="dropdown platfdd">
            <div className="dd-label">Filter by platform</div>
            {opts.map((p) => (
              <button key={p} className={"dd-item" + (plat === p ? " active" : "")} onClick={() => { setPlat(p); setOpen(false); }}>
                {tile(p, 13)}
                <span className="dd-txt">{p === "all" ? "All Platforms" : (PLAT_LABEL[p] || p)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

type Ctx = {
  tick: number; role: "Manager" | "Creator"; toast: (m: string, bad?: boolean) => void;
  run: (fn: () => Promise<any>, ok?: string) => Promise<void>; accounts: Account[]; brand: Brand;
};

/* ================= HOME — the network feed ================= */
function relTime(iso: string) {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  const s = Math.max(1, (Date.now() - d.getTime()) / 1000);
  if (s < 60) return Math.floor(s) + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  if (s < 86400) return Math.floor(s / 3600) + "h";
  return Math.floor(s / 86400) + "d";
}
function mediaLabel(m: string) {
  return ({
    sunset: "🌅  Palm Jumeirah · golden hour", skyline: "🏙️  Downtown Dubai", video: "▶  Reel · 0:24",
    project: "▤  Yas Island · floor plans", chart: "📊  July DXB transactions", pool: "☀️  Saadiyat · amenities",
  } as Record<string, string>)[m] || "🖼  Media";
}
// an uploaded file is stored as a data:/http URL; a seeded post uses a themed keyword
const isUploadedMedia = (m: string) => m.startsWith("data:") || m.startsWith("http");
const isVideoUrl = (u: string) => u.startsWith("data:video") || /\.(mp4|webm|mov)(\?|$)/i.test(u);

// Renders a post's media: a themed keyword (seeded), a single upload, or a JSON
// array of uploads (one image / multiple images / a video) as a gallery.
function FeedMedia({ m }: { m: string }) {
  if (m.startsWith("[")) {
    let arr: string[] = [];
    try { arr = JSON.parse(m); } catch { arr = []; }
    arr = arr.filter(Boolean);
    if (!arr.length) return null;
    return (
      <div className={"fgallery n" + Math.min(arr.length, 4)}>
        {arr.slice(0, 4).map((u, i) => (isVideoUrl(u) ? <video key={i} src={u} controls /> : <img key={i} src={u} alt="" />))}
      </div>
    );
  }
  if (isUploadedMedia(m)) {
    return isVideoUrl(m) ? <video className="fimg" src={m} controls /> : <img className="fimg" src={m} alt="" />;
  }
  return <div className={"fmedia media-" + m}>{mediaLabel(m)}</div>;
}

function HomeView({ tick, toast }: Ctx & { goTab: (t: any) => void; following: string[] }) {
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, FeedComment[]>>({});
  const [reply, setReply] = useState("");
  const [plat, setPlat] = useState("all");
  // posts with a like/repost mid-flight: the poll must not clobber their optimistic state
  const dirty = useRef<Set<number>>(new Set());

  const load = () => api.feed().then((fresh: FeedPost[]) =>
    setPosts((prev) => fresh.map((fp) => {
      if (!dirty.current.has(fp.id)) return fp;
      const local = prev.find((p) => p.id === fp.id);
      return local || fp; // keep the in-flight optimistic row until its request settles
    })),
  ).catch(() => {});
  useEffect(() => { load(); }, [tick]);

  const patch = (id: number, fn: (p: FeedPost) => FeedPost) => setPosts((ps) => ps.map((x) => (x.id === id ? fn(x) : x)));
  const toggleFeed = async (p: FeedPost, call: (id: number) => Promise<any>, optimistic: (x: FeedPost) => FeedPost) => {
    dirty.current.add(p.id);
    patch(p.id, optimistic);
    try {
      const server = await call(p.id);              // { ...row, mirror }
      const { mirror, ...row } = server;
      patch(p.id, () => row as FeedPost);           // reconcile with the committed row
      if (mirror?.detail) toast("↪ " + mirror.detail);
    } catch { load(); }
    finally { dirty.current.delete(p.id); }
  };
  const like = (p: FeedPost) => toggleFeed(p, api.feedLike, (x) => ({ ...x, liked: x.liked ? 0 : 1, likes: x.likes + (x.liked ? -1 : 1) }));
  const repost = (p: FeedPost) => toggleFeed(p, api.feedRepost, (x) => ({ ...x, reposted: x.reposted ? 0 : 1, reposts: x.reposts + (x.reposted ? -1 : 1) }));
  const toggle = async (p: FeedPost) => {
    if (open === p.id) { setOpen(null); return; }
    setOpen(p.id);
    if (!comments[p.id]) { const c = await api.feedComments(p.id); setComments((m) => ({ ...m, [p.id]: c })); }
  };
  const send = async (p: FeedPost) => {
    if (!reply.trim()) return;
    const res = await api.feedComment(p.id, reply.trim());  // { comments, mirror }
    setComments((m) => ({ ...m, [p.id]: res.comments })); setReply("");
    patch(p.id, (x) => ({ ...x, comments_count: x.comments_count + 1 }));
    if (res.mirror?.detail) toast("↪ " + res.mirror.detail);
  };

  const platforms = ["all", ...ALL_PLATFORMS];
  const shown = posts.filter((p) => plat === "all" || p.platform === plat);

  return (
    <div className="feedsolo">
      <div className="feedmain">
        <h2 className="feedhead">Home <span className="tiny" style={{ fontWeight: 700 }}>· your network, every platform</span></h2>

        <InlineComposer toast={toast} onPosted={load} />

        <PlatformFilter plat={plat} setPlat={setPlat} />

        {shown.length === 0 && <div className="empty">Nothing on this platform yet — try another, or post something.</div>}
        {shown.map((p) => (
          <div className="fpost" key={p.id}>
            <div className="avatar-sm" style={{ background: p.author_color }}>{p.author_initials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="fmeta">
                <b>{p.author_name}</b><span className="fhandle">@{p.author_handle}</span><span className="fdot">·</span><span className="ftime">{relTime(p.created_at)}</span>
                <span className={`fplat ${p.platform}`} title={`posted on ${p.platform}`}>{p.platform === "wolfie" ? "🐺" : <PlatSvg p={p.platform} size={13} />}</span>
              </div>
              {p.text && <div className="ftext">{p.text}</div>}
              {p.media && <FeedMedia m={p.media} />}
              <div className="factions">
                <button className="fact" onClick={() => toggle(p)}>💬 <span>{p.comments_count}</span></button>
                <button className={"fact" + (p.reposted ? " on-rt" : "")} onClick={() => repost(p)}>🔁 <span>{p.reposts}</span></button>
                <button className={"fact" + (p.liked ? " on-like" : "")} onClick={() => like(p)}>{p.liked ? "❤️" : "🤍"} <span>{p.likes}</span></button>
                <button className="fact" onClick={() => toast("Link copied — share it anywhere")}>↗</button>
              </div>
              {!!(p.liked || p.reposted) && p.platform !== "wolfie" && (
                <div className="fsync" title={`Your engagement is written back to ${platName(p.platform)}`}>
                  ↪ Reflected on <b>{platName(p.platform)}</b>
                </div>
              )}
              {open === p.id && (
                <div className="fcomments">
                  {(comments[p.id] || []).map((c) => (
                    <div className="fcomment" key={c.id}>
                      <div className="avatar-xs" style={{ background: "#8A8A93" }}>{c.initials}</div>
                      <div style={{ flex: 1 }}><b>{c.author}</b> <span className="tiny">{relTime(c.created_at)}</span><div>{c.text}</div></div>
                    </div>
                  ))}
                  {(comments[p.id] || []).length === 0 && <div className="tiny" style={{ padding: "2px 0 8px" }}>Be the first to reply.</div>}
                  <div className="fcbox">
                    <input placeholder="Post your reply" value={reply} onChange={(e) => setReply(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(p)} />
                    <button className="btn btn-sm" onClick={() => send(p)}>Reply</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================= MY PROFILE — your posts across every platform ================= */
function ProfileView({ tick, goTab }: Ctx & { goTab: (t: any) => void }) {
  const [data, setData] = useState<any>(null);
  const [plat, setPlat] = useState("all");
  useEffect(() => { api.profile().then(setData).catch(() => {}); }, [tick]);
  if (!data) return <div className="empty">Loading your profile…</div>;

  const p = data.profile;
  const posts: any[] = data.posts || [];
  const platforms = ["all", ...ALL_PLATFORMS];
  const shown = posts.filter((x) => plat === "all" || x.platform === plat);

  return (
    <div>
      <div className="profhero card">
        <div className="profava-lg" style={{ background: p.color }}>{p.initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ margin: 0 }}>{p.name}</h2>
          <div className="tiny" style={{ fontWeight: 700, marginTop: 2 }}>@{p.handle} · {p.role} · {p.brand}</div>
          <div className="profstats">
            <div><b>{p.posts_count}</b><span>Posts</span></div>
            <div><b>{p.following}</b><span>Following</span></div>
            <div><b>{p.platforms.length}</b><span>Platforms</span></div>
            <div><b>{fmtNum(p.reach)}</b><span>Total reach</span></div>
          </div>
          <div className="profplats">
            {p.platforms.map((pf: string) => (
              <span key={pf} className={`acc ${pf}`} title={pf} style={{ width: 26, height: 26, borderRadius: 8 }}><PlatSvg p={pf} size={15} /></span>
            ))}
          </div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => goTab("create")}>✨ New post</button>
      </div>

      <div style={{ margin: "16px 0 4px" }}><PlatformFilter plat={plat} setPlat={setPlat} /></div>

      {shown.length === 0 && <div className="empty">No posts on this platform yet.</div>}
      <div className="profgrid">
        {shown.map((x) => (
          <div className="card p profpost" key={x.id}>
            <div className="fmeta" style={{ marginBottom: 8 }}>
              <div className={"thumb " + x.format} style={{ width: 34, height: 42, fontSize: 15, borderRadius: 9 }}>{fmtGlyph(x.format)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ display: "block", fontSize: 14, lineHeight: 1.25 }}>{x.title || "(untitled)"}</b>
                <span className="tiny">{platName(x.platform || "—")} · {x.format} · {relTime(x.created_at)}</span>
              </div>
              {x.platform && <span className={`fplat ${x.platform}`}><PlatSvg p={x.platform} size={13} /></span>}
            </div>
            {x.caption && <div className="profcap">{x.caption}</div>}
            <div className="proffoot">
              <span className={"pill " + x.status}>{x.status.replace(/_/g, " ")}</span>
              {x.status === "published" && <span className="tiny">👁 {fmtNum(x.reach)} · ⚡ {fmtNum(x.engagements)}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================= AI ANALYST — ask about your performance ================= */
// render **bold** + paragraph breaks from the analyst's plain-text answer
function renderMd(text: string) {
  return text.split("\n\n").map((para, i) => (
    <p key={i} style={{ margin: i === 0 ? 0 : "8px 0 0" }}>
      {para.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
        seg.startsWith("**") && seg.endsWith("**")
          ? <strong key={j}>{seg.slice(2, -2)}</strong>
          : <span key={j}>{seg}</span>,
      )}
    </p>
  ));
}

const ANALYST_SUGGESTIONS = [
  "What's my best-performing format?",
  "What should I post next?",
  "Which topic is working best?",
  "How's my engagement overall?",
];

function AnalystView({ }: Ctx) {
  const [msgs, setMsgs] = useState<{ role: "user" | "ai"; text: string; provider?: string }[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ(""); setBusy(true);
    try {
      const r = await api.analyst(text);
      setMsgs((m) => [...m, { role: "ai", text: r.answer, provider: r.provider }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "ai", text: e.message || "Something went wrong.", provider: "error" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="feedsolo">
      <div className="head"><div><h2>AI Analyst</h2><p>Ask about your performance — answered from your real numbers.</p></div></div>

      <div className="analyst">
        {msgs.length === 0 && (
          <div className="analyst-empty">
            <div className="analyst-ava">🤖</div>
            <p style={{ maxWidth: 380, margin: "0 auto" }}>Hi — I'm your analyst. Ask me what's working, what to post next, or which format wins.</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={"amsg " + m.role}>
            {m.role === "ai" && <div className="analyst-ava sm">🤖</div>}
            <div className="abubble">
              {renderMd(m.text)}
              {m.role === "ai" && m.provider && m.provider !== "error" && (
                <div className="tiny" style={{ marginTop: 6, opacity: 0.6 }}>via {m.provider === "anthropic" ? "Claude" : "built-in analyst"}</div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="amsg ai"><div className="analyst-ava sm">🤖</div><div className="abubble analyst-typing">Analysing your numbers…</div></div>}
      </div>

      {msgs.length === 0 && (
        <div className="achips">
          {ANALYST_SUGGESTIONS.map((s) => <button key={s} className="achip" disabled={busy} onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}
      <div className="abar">
        <input placeholder="Ask about your performance…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask(q)} />
        <button className="btn btn-primary btn-sm" disabled={busy || !q.trim()} onClick={() => ask(q)}>Ask</button>
      </div>
    </div>
  );
}

/* ================= ANALYTICS ================= */
function AnalyticsView({ tick }: Ctx) {
  const [a, setA] = useState<any>(null);
  useEffect(() => { api.analytics().then(setA).catch(() => {}); }, [tick]);
  if (!a) return <div className="empty">Loading analytics…</div>;
  const t = a.totals;
  const maxFmt = Math.max(1, ...a.formats.map((f: any) => f.score));
  return (
    <div>
      <div className="head"><div><h2>What's working</h2><p>Everything scored against <b>your</b> baseline — not raw views.</p></div></div>
      <div className="kpis">
        <div className="kpi"><div className="lab">Total reach</div><div className="val tnum">{fmtNum(t.reach)}</div></div>
        <div className="kpi"><div className="lab">Engagement rate</div><div className="val tnum">{(t.engagement_rate * 100).toFixed(1)}%</div></div>
        <div className="kpi"><div className="lab">Posts analysed</div><div className="val tnum">{t.posts}</div></div>
      </div>
      <div className="grid2">
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 12 }}>🏆 Winning formats</h3>
          {a.formats.map((f: any) => (
            <div className="barrow" key={f.format}>
              <div className="n" style={{ textTransform: "capitalize" }}>{f.format} <span className="tiny">×{f.count}</span></div>
              <div className="bar"><div className="barfill" style={{ width: `${(f.score / maxFmt) * 100}%` }} /></div>
              <div className="v">{f.score}</div>
            </div>
          ))}
        </div>
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 12 }}>🎯 Winning topics</h3>
          {a.topics.map((tp: any) => (
            <div className="barrow" key={tp.pillar}>
              <div className="n">{tp.pillar}</div>
              <div className="bar"><div className="barfill coral" style={{ width: `${tp.score * 10}%` }} /></div>
              <div className="v">{tp.score}</div>
            </div>
          ))}
        </div>
      </div>
      {a.best && (
        <div className="card p" style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 16, marginBottom: 8 }}>📈 Best post</h3>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <b>{a.best.title}</b>
            <span className="pill approved">+{a.best.pct}% above your normal {a.best.format}</span>
          </div>
          <p className="tiny" style={{ marginTop: 8 }}>{fmtNum(a.best.reach)} reach — but the number that matters is how far above your baseline it landed.</p>
        </div>
      )}
      <div className="card p" style={{ marginTop: 16 }}>
        <h3 style={{ fontSize: 16, marginBottom: 4 }}>↪ Engagement synced to platforms</h3>
        <p className="tiny" style={{ marginBottom: 12 }}>Every like, repost and reply you make in your unified feed is written back to the post's original platform.</p>
        {(a.synced || []).length === 0 ? (
          <div className="tiny">Engage with posts in your feed and they'll be reflected here, per platform.</div>
        ) : (
          <div className="synced">
            {a.synced.map((s: any) => (
              <div className="syncrow" key={s.platform}>
                <span className={`acc ${s.platform}`} style={{ width: 24, height: 24, borderRadius: 7 }}><PlatSvg p={s.platform} size={14} /></span>
                <b style={{ flex: 1 }}>{platName(s.platform)}</b>
                <span className="tiny">{s.events} action{s.events === 1 ? "" : "s"}</span>
                <span className="pill approved tnum">{s.net} reflected</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ================= BRAND BRAIN ================= */
function BrandBrainView({ brand, run }: Ctx) {
  const [name, setName] = useState(brand.name);
  const [voice, setVoice] = useState(brand.voice);
  const [audience, setAudience] = useState(brand.audience);
  const [cta, setCta] = useState(brand.cta);
  const [always, setAlways] = useState(brand.always_say);
  const [never, setNever] = useState(brand.never_say);
  const [pillars, setPillars] = useState<string[]>(
    (brand.pillars || "").split(",").map((s) => s.trim()).filter(Boolean),
  );
  const [newPillar, setNewPillar] = useState("");

  const addPillar = () => {
    const p = newPillar.trim();
    if (p && !pillars.includes(p)) setPillars([...pillars, p]);
    setNewPillar("");
  };
  const save = () =>
    run(
      () => api.updateBrand(brand.id, { name, voice, audience, cta, always_say: always, never_say: never, pillars }),
      "Brand Brain saved — it now steers generation & recommendations",
    );

  return (
    <div>
      <div className="head"><div><h2>Brand Brain</h2><p>Teach Wolfie once. These rules steer every caption it writes and every recommendation it ranks.</p></div></div>
      <div className="grid2">
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 12 }}>Who you are</h3>
          <div className="field"><label>Brand name</label><input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="field"><label>Audience</label><input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Who you're speaking to" /></div>
          <div className="field"><label>Voice</label><input value={voice} onChange={(e) => setVoice(e.target.value)} placeholder="e.g. Premium, confident, educational" /></div>
          <div className="field" style={{ margin: 0 }}><label>Preferred CTA</label><input value={cta} onChange={(e) => setCta(e.target.value)} /></div>
        </div>
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 12 }}>Content rules</h3>
          <div className="field"><label style={{ color: "var(--teal-ink)" }}>Always mention</label><input value={always} onChange={(e) => setAlways(e.target.value)} placeholder="e.g. RERA permit number" /></div>
          <div className="field" style={{ margin: 0 }}><label style={{ color: "var(--rose-ink)" }}>Never say (comma-separated)</label><input value={never} onChange={(e) => setNever(e.target.value)} placeholder="e.g. guaranteed returns, risk-free" /></div>
          <div className="tiny" style={{ marginTop: 10 }}>🛡 Never-say phrases are flagged on any post in Approvals — a guardrail at the publish gate.</div>
        </div>
      </div>
      <div className="card p" style={{ marginTop: 16 }}>
        <h3 style={{ fontSize: 16, marginBottom: 10 }}>Content pillars</h3>
        <div className="tiny" style={{ marginBottom: 10 }}>Wolfie tracks performance by pillar and flags gaps in Recommendations.</div>
        <div className="row" style={{ marginBottom: 12 }}>
          {pillars.map((p, i) => (
            <span className="pill draft" key={i} style={{ cursor: "pointer" }} title="Remove" onClick={() => setPillars(pillars.filter((_, j) => j !== i))}>{p} ✕</span>
          ))}
          {pillars.length === 0 && <span className="tiny">No pillars yet.</span>}
        </div>
        <div className="row">
          <input value={newPillar} onChange={(e) => setNewPillar(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addPillar()} placeholder="Add a pillar…" style={{ width: 220, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 10, padding: "9px 12px", fontFamily: "inherit", fontSize: 14 }} />
          <button className="btn btn-sm" onClick={addPillar}>Add</button>
        </div>
      </div>
      <div className="row" style={{ marginTop: 16, alignItems: "center" }}>
        <button className="btn btn-primary" onClick={save}>Save Brand Brain</button>
        <span className="tiny">Then regenerate a post in Create — you'll see the CTA, voice, and audience steer the copy.</span>
      </div>
    </div>
  );
}

/* ================= CALENDAR ================= */
function CalendarView({ tick, run }: Ctx) {
  const [jobs, setJobs] = useState<Job[]>([]);
  useEffect(() => { api.calendar().then(setJobs).catch(() => {}); }, [tick]);

  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() + i); return d;
  });
  const byDay: Record<string, Job[]> = {};
  for (const j of jobs) {
    const k = dayKey(asDate(j.scheduled_at));
    (byDay[k] ||= []).push(j);
  }

  return (
    <div>
      <div className="head">
        <div><h2>Content calendar</h2><p>Scheduled posts across every channel. The publish engine fires jobs automatically as they come due.</p></div>
        <button className="btn" onClick={() => run(() => api.runDue(), "Ran due jobs")}>Run due now</button>
      </div>
      <div className="cal">
        {days.map((d) => {
          const items = (byDay[dayKey(d)] || []).sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
          return (
            <div className="col" key={dayKey(d)}>
              <h4>{d.toLocaleDateString([], { weekday: "short" })}<small>{d.getDate()}</small></h4>
              {items.map((j) => (
                <div className="ev" key={j.id}>
                  <div className="time mono">{fmtTime(asDate(j.scheduled_at))} · {j.platform}</div>
                  <div className="t">{j.title}</div>
                  <span className={"pill " + j.status} style={{ marginTop: 6 }}>{j.status}</span>
                </div>
              ))}
              {items.length === 0 && <div className="tiny">—</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ================= APPROVALS ================= */
function ApprovalsView({ tick, role, run, goCreate }: Ctx & { goCreate: () => void }) {
  const [posts, setPosts] = useState<Post[]>([]);
  useEffect(() => { api.posts("in_review").then(setPosts).catch(() => {}); }, [tick]);

  return (
    <div>
      <div className="head">
        <div><h2>Approvals</h2><p>Creator → Manager → Scheduled. {role === "Creator" && "Switch to Manager (top-right) to approve."}</p></div>
      </div>
      <div className="card">
        {posts.length === 0 && <div className="empty">Nothing waiting for review. 🎉</div>}
        {posts.map((p) => (
          <div className="appr" key={p.id}>
            <div className={"thumb " + p.format}>{fmtGlyph(p.format)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <b style={{ fontSize: 15.5 }}>{p.title || "(untitled)"}</b>
                <span className="pill in_review">Awaiting review</span>
              </div>
              <div className="tiny" style={{ margin: "3px 0 2px" }}>
                {p.platform ?? "no channel"} · {p.format} · v{p.current_version} · by {p.created_by}
              </div>
              <div className="muted" style={{ fontSize: 13.5 }}>{p.caption}</div>
              {p.violations && p.violations.length > 0 && (
                <div className="err" style={{ marginTop: 8 }}>⚠ Brand rule — never say “{p.violations.join("”, “")}”</div>
              )}
              <div className="steps">
                <span className="s done">✓ {p.created_by} · Creator</span> ›
                <span className="s now">2 You · Manager</span> ›
                <span className="s">3 Scheduled</span>
              </div>
              {role === "Manager" ? (
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => run(() => api.approve(p.id, "You"), "Approved — now schedule it")}>Approve</button>
                  <button className="btn btn-sm" onClick={() => {
                    const c = prompt("What needs changing?"); if (c !== null) run(() => api.requestChanges(p.id, "You", c), "Sent back for changes");
                  }}>Request changes</button>
                </div>
              ) : (
                <div className="tiny" style={{ marginTop: 10 }}>Waiting on a Manager to approve.</div>
              )}
            </div>
          </div>
        ))}
      </div>
      <p className="tiny" style={{ marginTop: 12 }}>Approved posts get scheduled from the <a onClick={goCreate} style={{ cursor: "pointer", color: "var(--teal-ink)" }}>Create</a> tab.</p>
    </div>
  );
}

/* ================= CREATE ================= */
/* ================= IDEAS & TRENDS — the top of the learning loop ================= */
function IdeasView({ tick, toast, goTab }: Ctx & { goTab: (t: any) => void }) {
  const [recs, setRecs] = useState<any[]>([]);
  const [an, setAn] = useState<any>(null);
  const [promoted, setPromoted] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [needsManual, setNeedsManual] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.recommendations().then(setRecs).catch(() => {});
    api.analytics().then(setAn).catch(() => {});
  }, [tick]);

  // (format,pillar) is the engine's own de-dupe key — stable across the 4s poll, unlike the positional rec id
  const sig = (r: any) => `${r.format}|${r.pillar}`;

  const promote = async (r: any, generate = true) => {
    const s = sig(r);
    setBusy(s);
    try {
      await api.createFromRec({ account_id: r.account_id, format: r.format, objective: r.objective, title: r.title, topic: r.pillar, generate });
      setPromoted((p) => new Set(p).add(s));
      setNeedsManual((m) => { const n = new Set(m); n.delete(s); return n; });
      toast("Draft created — it's waiting in Compose");
      goTab("create");
    } catch (e: any) {
      // AI generation unconfigured (400) → offer a no-AI promote using the idea's title verbatim
      setNeedsManual((m) => new Set(m).add(s));
      toast(e.message || "Couldn't generate copy — try without AI", true);
    } finally {
      setBusy(null);
    }
  };
  const dismiss = (r: any) => { setDismissed((d) => new Set(d).add(sig(r))); toast("Idea dismissed"); };

  const active = recs.filter((r) => !dismissed.has(sig(r)));
  const topics = an?.topics || [];
  const maxTopic = Math.max(1, ...topics.map((t: any) => t.score));
  const bestFmt = (an?.formats || [])[0];

  return (
    <div className="feedwrap">
      <div className="feedmain">
        <div className="head"><div><h2>Ideas &amp; Trends</h2><p>Your next best posts, drawn from what's working in your network. Promote one and it lands as a draft in the approval loop.</p></div></div>

        {recs.length === 0 && <div className="empty">Publish a few posts and Wolfie will start suggesting ideas here.</div>}

        {active.map((r) => {
          const s = sig(r);
          const done = promoted.has(s);
          return (
            <div className="card p ideacard" key={s}>
              <div className={"thumb " + r.format}>{fmtGlyph(r.format)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ideachips">
                  <span className="pill draft">{r.pillar}</span>
                  <span className="pill draft">🎯 {r.objective}</span>
                  <span className="scorepill" style={{ marginLeft: "auto" }}>{r.score}/10</span>
                </div>
                <h3 style={{ fontSize: 16.5, margin: "9px 0 8px", lineHeight: 1.25 }}>{r.title}</h3>
                <div className="why"><span>💡</span><div>{r.why}</div></div>
                {done ? (
                  <div className="ideaactions">
                    <span className="pill approved">✓ Promoted to draft</span>
                    <button className="btn btn-sm" onClick={() => goTab("create")}>Open in Compose →</button>
                  </div>
                ) : (
                  <div className="ideaactions">
                    <button className="btn btn-primary btn-sm" disabled={busy === s} onClick={() => promote(r, true)}>{busy === s ? "Creating…" : "✨ Promote to draft"}</button>
                    {needsManual.has(s) && <button className="btn btn-sm" disabled={busy === s} onClick={() => promote(r, false)}>Promote without AI</button>}
                    <button className="btn btn-ghost btn-sm" disabled={busy === s} onClick={() => dismiss(r)}>Dismiss</button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <aside className="feedside">
        <div className="card p sidecard">
          <h3>📈 Trending topics</h3>
          {topics.slice(0, 5).map((t: any) => (
            <div className="barrow" key={t.pillar}>
              <div className="n">{t.pillar}</div>
              <div className="bar"><div className="barfill coral" style={{ width: `${(t.score / maxTopic) * 100}%` }} /></div>
              <div className="v">{t.score}</div>
            </div>
          ))}
          {topics.length === 0 && <div className="tiny">No signal yet — publish to learn what travels.</div>}
        </div>
        {bestFmt && (
          <div className="card p sidecard">
            <h3>🏆 Best format to ride</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 11, marginTop: 8 }}>
              <div className={"thumb " + bestFmt.format} style={{ width: 40, height: 48, fontSize: 17 }}>{fmtGlyph(bestFmt.format)}</div>
              <div><b style={{ textTransform: "capitalize", fontSize: 15 }}>{bestFmt.format}</b><div className="tiny">Scoring {bestFmt.score}/10 for you right now</div></div>
            </div>
          </div>
        )}
        {an?.best && (
          <div className="card p sidecard">
            <h3>🔥 What's working now</h3>
            <b style={{ fontSize: 14 }}>{an.best.title}</b>
            <div style={{ marginTop: 8 }}><span className="pill approved">+{an.best.pct}% vs your normal {an.best.format}</span></div>
          </div>
        )}
      </aside>
    </div>
  );
}

function CreateView({ tick, run, toast, accounts, brand }: Ctx) {
  const [accountId, setAccountId] = useState<number>(accounts[0]?.id ?? 0);
  const [format, setFormat] = useState("static");
  const [title, setTitle] = useState("");
  const [caption, setCaption] = useState("");
  const [mediaUrl, setMediaUrl] = useState("");
  const [slides, setSlides] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [posts, setPosts] = useState<Post[]>([]);

  useEffect(() => {
    // this brand's posts that are still in the pipeline
    api.posts().then((all: Post[]) =>
      setPosts(all.filter((p) => ["draft", "changes_requested", "in_review", "approved"].includes(p.status)))
    ).catch(() => {});
  }, [tick]);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await api.generate({ brand_id: brand.id, format, topic: title, objective: "engagement" });
      setTitle(r.title || title);
      setCaption(r.caption || caption);
      setSlides(r.slides || []);
      toast(`Drafted with the ${r.provider} generator`);
    } catch (e: any) {
      toast(e.message, true);
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    run(async () => {
      await api.createPost({ brand_id: brand.id, account_id: accountId || null, format, title, caption, media_url: mediaUrl, created_by: "You" });
      setTitle(""); setCaption(""); setMediaUrl(""); setSlides([]);
    }, "Draft saved");

  return (
    <div>
      <div className="head"><div><h2>Create a post</h2><p>Draft it, generate on-brand copy, then send it into the approval loop.</p></div></div>
      <div className="grid2">
        <div className="card p">
          <div className="row" style={{ marginBottom: 12 }}>
            <div className="field" style={{ flex: 1, margin: 0 }}>
              <label>Channel</label>
              <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))}>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.platform} · {a.handle} {a.status !== "connected" ? "(offline)" : ""}</option>)}
              </select>
            </div>
            <div className="field" style={{ width: 150, margin: 0 }}>
              <label>Format</label>
              <select value={format} onChange={(e) => setFormat(e.target.value)}>
                {["reel", "carousel", "static", "text"].map((f) => <option key={f}>{f}</option>)}
              </select>
            </div>
          </div>
          <div className="field"><label>Title / hook</label><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Golden Visa myths" /></div>
          <div className="field"><label>Caption</label><textarea rows={6} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Write it, or generate on-brand copy →" /></div>
          <div className="field"><label>Media URL <span className="tiny" style={{ fontWeight: 600 }}>— public image/video, required for real Instagram publishing</span></label><input value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} placeholder="https://… (optional in mock mode)" /></div>
          {slides.length > 0 && (
            <div className="slides">
              {slides.map((s, i) => <div className="slide" key={i}><b>{s.heading}</b><span>{s.body}</span></div>)}
            </div>
          )}
          <div className="row" style={{ marginTop: 6 }}>
            <button className="btn" onClick={generate} disabled={busy}>{busy ? "Generating…" : "✨ Generate with AI"}</button>
            <button className="btn btn-primary" onClick={save} disabled={!title && !caption}>Save draft</button>
          </div>
        </div>

        <div className="card p">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span className="ava" style={{ background: brand.color, width: 24, height: 24, borderRadius: 7, color: "#fff", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 11 }}>{brand.initials}</span>
            <b style={{ fontSize: 14 }}>On brand</b>
          </div>
          <div className="tiny" style={{ marginBottom: 4 }}>Voice: {brand.voice}</div>
          <div className="tiny">CTA: {brand.cta}</div>
          {brand.never_say && <div className="err" style={{ marginTop: 8 }}>Never say: {brand.never_say}</div>}
          <div className="tiny" style={{ marginTop: 10 }}>The AI generator runs on a mock provider by default — set <span className="mono">AI_PROVIDER=anthropic</span> to use real Claude.</div>
        </div>
      </div>

      <h3 style={{ margin: "24px 0 12px", fontSize: 17 }}>In the pipeline</h3>
      <div className="card">
        {posts.length === 0 && <div className="empty">No drafts yet — create one above.</div>}
        {posts.map((p) => <PipelineRow key={p.id} post={p} run={run} />)}
      </div>
    </div>
  );
}

function PipelineRow({ post, run }: { post: Post; run: Ctx["run"] }) {
  const [when, setWhen] = useState(localInputDefault(1));
  return (
    <div className="appr">
      <div className={"thumb " + post.format}>{fmtGlyph(post.format)}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <b style={{ fontSize: 15 }}>{post.title || "(untitled)"}</b>
          <span className={"pill " + post.status}>{post.status.replace("_", " ")}</span>
        </div>
        <div className="tiny" style={{ margin: "3px 0" }}>{post.platform ?? "no channel"} · {post.format}</div>
        <div className="muted" style={{ fontSize: 13 }}>{post.caption}</div>
        <div className="row" style={{ marginTop: 10 }}>
          {(post.status === "draft" || post.status === "changes_requested") && (
            <button className="btn btn-primary btn-sm" onClick={() => run(() => api.submit(post.id, "You"), "Submitted for approval")}>Submit for approval</button>
          )}
          {post.status === "in_review" && <span className="tiny">Waiting in Approvals.</span>}
          {post.status === "approved" && (
            <>
              <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} style={{ width: 200, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 9px", fontFamily: "inherit" }} />
              <button className="btn btn-primary btn-sm" onClick={() => run(() => api.schedule(post.id, new Date(when).toISOString()), "Scheduled")}>Schedule</button>
              <button className="btn btn-sm" onClick={() => run(() => api.publishNow(post.id), "Publishing now…")}>Publish now</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ================= PUBLISH LOG ================= */
function PublishView({ tick, run }: Ctx) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => { api.jobs().then(setJobs).catch(() => {}); }, [tick]);
  useEffect(() => { api.metaCheck().then(setMeta).catch(() => {}); }, [tick]);

  const metaBadge = meta && (
    <span className={"pill " + (meta.configured ? (meta.ok ? "published" : "failed") : "draft")}>
      Instagram: {meta.configured ? (meta.ok ? `live @${meta.username}` : "credentials error") : "mock mode"}
    </span>
  );

  return (
    <div>
      <div className="head">
        <div><h2>Publish log</h2><p>The engine claims due jobs, calls each platform adapter, retries failures with backoff, and records the result. Updates live.</p></div>
        <div className="row" style={{ alignItems: "center" }}>{metaBadge}<button className="btn" onClick={() => run(() => api.runDue(), "Ran due jobs")}>Run due now</button></div>
      </div>
      {meta && !meta.configured && <div className="tiny" style={{ marginBottom: 12 }}>{meta.detail}</div>}
      {meta && meta.configured && !meta.ok && <div className="err" style={{ marginBottom: 12 }}>{meta.detail}</div>}
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>Post</th><th>Channel</th><th>Status</th><th>Scheduled</th><th>Attempts</th><th>Result</th><th></th></tr></thead>
          <tbody>
            {jobs.length === 0 && <tr><td colSpan={7}><div className="empty">No jobs yet.</div></td></tr>}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><b>{j.title}</b><div className="tiny">{j.format}</div></td>
                <td>{j.platform}</td>
                <td><span className={"pill " + j.status}>{j.status}</span></td>
                <td className="mono tiny">{asDate(j.scheduled_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                <td className="tnum">{j.attempts}</td>
                <td>
                  {j.status === "published" && j.platform_url && <a href={j.platform_url} target="_blank" rel="noreferrer">View post ↗</a>}
                  {j.status === "failed" && <span className="err">{j.last_error}</span>}
                  {j.status === "scheduled" && <span className="tiny">waiting…</span>}
                  {j.status === "publishing" && <span className="tiny">publishing…</span>}
                </td>
                <td>
                  {(j.status === "scheduled" || j.status === "failed") &&
                    <button className="btn btn-ghost btn-sm" onClick={() => run(() => api.cancelJob(j.id), "Canceled")}>Cancel</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fmtGlyph(f: string) {
  return ({ reel: "▶", carousel: "▤", static: "▦", text: "T" } as Record<string, string>)[f] ?? "•";
}

function fmtNum(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

/* ================= top-right dropdown menu ================= */
function NavMenu({ id, label, items, tab, nav, menu, setMenu }: {
  id: string; label: string; tab: string; nav: (t: any) => void;
  menu: string | null; setMenu: (m: string | null) => void;
  items: { key: string; ico: string; label: string; sub?: string; badge?: number }[];
}) {
  const open = menu === id;
  return (
    <div className="menu-wrap">
      <button className={"menu-btn" + (open ? " on" : "")} onClick={(e) => { e.stopPropagation(); setMenu(open ? null : id); }}>
        {label} <span className="chev">▾</span>
      </button>
      {open && (
        <div className="dropdown" onClick={(e) => e.stopPropagation()}>
          <div className="dd-label">{label}</div>
          {items.map((it) => (
            <button key={it.key} className={"dd-item" + (tab === it.key ? " active" : "")} onClick={() => nav(it.key)}>
              <span className="dd-ico">{it.ico}</span>
              <span className="dd-txt">{it.label}{it.sub && <small>{it.sub}</small>}</span>
              {it.badge ? <span className="dd-badge">{it.badge}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ================= notifications dropdown ================= */
const NOTIF_ICO: Record<string, string> = { like: "❤️", comment: "💬", follow: "➕", mention: "🏷️", system: "📣" };
function NotificationsDropdown({ bump, unread }: { bump: () => void; unread: number }) {
  const [items, setItems] = useState<Notification[]>([]);
  useEffect(() => { api.notifications().then(setItems).catch(() => {}); }, []);
  const markAll = async () => {
    if (unread > 0) { try { await api.readNotifications(); } catch { /* keep UI responsive */ } }
    setItems((is) => is.map((n) => ({ ...n, read: 1 })));
    bump();
  };
  return (
    <div className="dropdown notif-dd">
      <div className="notif-head">
        <b>Notifications</b>
        <button className="linkbtn" onClick={markAll} disabled={unread === 0}>Mark all read</button>
      </div>
      <div className="notif-list">
        {items.map((n) => (
          <div className={"notif" + (n.read ? "" : " unread")} key={n.id}>
            <div className="avatar-xs" style={{ background: n.actor_color }}>{n.actor_initials}</div>
            <div className="notif-body">
              <div><b>{n.actor_name}</b> <span>{n.text}</span></div>
              <div className="tiny">{relTime(n.created_at)} ago</div>
            </div>
            <span className="notif-ico">{NOTIF_ICO[n.type] || "•"}</span>
          </div>
        ))}
        {items.length === 0 && <div className="tiny" style={{ padding: "14px 4px" }}>You're all caught up.</div>}
      </div>
    </div>
  );
}

/* ================= CONNECTORS ================= */
function ConnectorsView({ tick, accounts }: Ctx) {
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => { api.metaCheck().then(setMeta).catch(() => {}); }, [tick]);
  const metaPill = meta && (
    <span className={"pill " + (meta.configured ? (meta.ok ? "published" : "failed") : "draft")}>
      {meta.configured ? (meta.ok ? `live @${meta.username}` : "credentials error") : "mock mode"}
    </span>
  );
  return (
    <div>
      <div className="head"><div><h2>Connectors</h2><p>Channels Wolfie publishes to and reads insights from — official, compliant APIs only.</p></div></div>
      <div className="grid2">
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 10 }}>🔌 Channels</h3>
          {accounts.map((a) => (
            <div className="conn-row" key={a.id}>
              <span className={`acc ${a.platform}`} style={{ width: 30, height: 30, borderRadius: 9 }}>{icon(a.platform)}</span>
              <div style={{ flex: 1 }}><b style={{ textTransform: "capitalize" }}>{a.platform}</b><div className="tiny">{a.handle}</div></div>
              <span className={"pill " + (a.status === "connected" ? "published" : "draft")}>{a.status}</span>
            </div>
          ))}
        </div>
        <div className="card p">
          <h3 style={{ fontSize: 16, marginBottom: 10 }}>🧩 Integrations</h3>
          <div className="conn-row">
            <span className="conn-ico">◆</span>
            <div style={{ flex: 1 }}><b>Meta Graph API</b><div className="tiny">Instagram / Facebook publishing &amp; insights</div></div>
            {metaPill}
          </div>
          <div className="conn-row">
            <span className="conn-ico" style={{ background: "var(--coral-soft)", color: "var(--coral-ink)" }}>✨</span>
            <div style={{ flex: 1 }}><b>AI generation</b><div className="tiny">On-brand captions, carousels &amp; reel scripts</div></div>
            <span className="pill scheduled">mock</span>
          </div>
          {meta && !meta.configured && <div className="tiny" style={{ marginTop: 10 }}>{meta.detail}</div>}
          {meta && meta.configured && !meta.ok && <div className="err" style={{ marginTop: 10 }}>{meta.detail}</div>}
          <p className="tiny" style={{ marginTop: 12 }}>Credentials live in your backend <span className="mono">.env</span> — never pasted into the app.</p>
        </div>
      </div>
    </div>
  );
}
