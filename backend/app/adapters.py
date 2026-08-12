"""Platform adapters.

The whole product publishes through ONE call — ``publish_post()`` — and each
network hides behind an adapter that implements ``publish(payload)``. When a
platform changes its API, you change one adapter, not the pipeline.

Out of the box every platform uses ``MockAdapter`` (no credentials, no network),
so the app is fully runnable today. Drop in a real adapter (see the Instagram
stub) and register it to go live.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class AdapterError(Exception):
    """Raised when a publish attempt fails. Message is stored on the job."""


@dataclass
class PublishPayload:
    platform: str
    format: str          # reel | carousel | static | text
    title: str
    caption: str
    handle: str
    account_status: str  # connected | disconnected | expired
    job_id: int
    media_url: str = ""  # public image/video URL (required by real platforms)


@dataclass
class PublishResult:
    platform_post_id: str
    platform_url: str


class PlatformAdapter:
    """Interface every network adapter implements."""

    name = "base"

    async def publish(self, payload: PublishPayload) -> PublishResult:  # pragma: no cover
        raise NotImplementedError


class MockAdapter(PlatformAdapter):
    """Simulates a real publish: latency, a deterministic failure for accounts
    that aren't connected, and a stable fake post id + URL."""

    def __init__(self, platform: str):
        self.name = platform

    async def publish(self, payload: PublishPayload) -> PublishResult:
        await asyncio.sleep(0.6)  # pretend the network took a moment

        # Deterministic failure: you can't publish through a broken connection.
        if payload.account_status != "connected":
            raise AdapterError(
                f"{self.name} account is {payload.account_status} — reconnect it to publish."
            )

        # optional random failure to exercise the retry path; 0.0 by default so
        # demos publish cleanly. Set WOLFIE_MOCK_FAILURE_RATE=0.15 to see retries.
        # Read at call time so .env / shell changes take effect without a reimport.
        failure_rate = float(os.getenv("WOLFIE_MOCK_FAILURE_RATE", "0"))
        if failure_rate:
            import random
            if random.random() < failure_rate:
                raise AdapterError(f"{self.name} API returned a transient error (simulated).")

        seed = f"{self.name}-{payload.job_id}-{payload.handle}".encode()
        pid = hashlib.sha1(seed).hexdigest()[:12]
        slug = _slug(self.name)
        url = f"https://{slug}/p/{pid}"
        return PublishResult(platform_post_id=pid, platform_url=url)


# --- real Meta Graph API plumbing (stdlib only) ------------------------------

def _graph_version() -> str:
    return os.getenv("META_GRAPH_VERSION", "v21.0")


def _graph_call(url: str, data: bytes | None = None) -> dict:
    """One Graph API call. Blocking (run it via asyncio.to_thread). Turns Meta
    error bodies into readable AdapterError messages."""
    try:
        req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            msg = body
        raise AdapterError(f"Meta API error: {msg}")
    except urllib.error.URLError as exc:
        raise AdapterError(f"Network error reaching Meta: {exc.reason}")


def _graph_post(path: str, params: dict) -> dict:
    return _graph_call(f"https://graph.facebook.com/{_graph_version()}/{path}",
                       urllib.parse.urlencode(params).encode())


def _graph_get(path: str, params: dict) -> dict:
    return _graph_call(f"https://graph.facebook.com/{_graph_version()}/{path}?{urllib.parse.urlencode(params)}")


async def meta_check() -> dict:
    """Verify Meta credentials without publishing — used by the setup screen."""
    token = os.getenv("META_ACCESS_TOKEN")
    ig = os.getenv("META_IG_USER_ID")
    if not token or not ig:
        return {"configured": False,
                "detail": "Set META_ACCESS_TOKEN and META_IG_USER_ID in backend/.env to publish for real."}
    try:
        info = await asyncio.to_thread(_graph_get, ig, {"fields": "username,name", "access_token": token})
        return {"configured": True, "ok": True, "username": info.get("username"),
                "name": info.get("name"), "ig_user_id": ig}
    except AdapterError as exc:
        return {"configured": True, "ok": False, "detail": str(exc)}


class InstagramAdapter(PlatformAdapter):
    """Real Instagram publishing via the Meta Graph API.

    Activated automatically when META_ACCESS_TOKEN and META_IG_USER_ID are set
    (see _default_registry). Requires an Instagram Business/Creator account, a
    Meta app with instagram_content_publish (+ Advanced Access via App Review),
    and a public media URL. Two-step flow: create a media container, then publish
    it. Reels are polled until Meta finishes processing.
    """

    name = "instagram"

    async def publish(self, payload: PublishPayload) -> PublishResult:
        token = os.getenv("META_ACCESS_TOKEN")
        ig = os.getenv("META_IG_USER_ID")
        if not token or not ig:
            raise AdapterError("Instagram not configured — set META_ACCESS_TOKEN and META_IG_USER_ID.")
        caption = payload.caption or payload.title

        if payload.format == "reel":
            video_url = payload.media_url or os.getenv("META_DEFAULT_VIDEO_URL")
            if not video_url:
                raise AdapterError("This reel has no video URL — set the post's media_url or META_DEFAULT_VIDEO_URL.")
            container = await asyncio.to_thread(_graph_post, f"{ig}/media", {
                "media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": token})
            cid = container.get("id")
            if not cid:
                raise AdapterError(f"Meta did not return a media container: {container}")
            # reels need server-side processing before they can be published
            for _ in range(20):
                st = await asyncio.to_thread(_graph_get, cid, {"fields": "status_code", "access_token": token})
                code = st.get("status_code")
                if code == "FINISHED":
                    break
                if code == "ERROR":
                    raise AdapterError(f"Meta failed to process the reel: {st}")
                await asyncio.sleep(3)
        else:
            # static / carousel-cover / text -> single image
            image_url = payload.media_url or os.getenv("META_DEFAULT_IMAGE_URL")
            if not image_url:
                raise AdapterError("This post has no image URL — set the post's media_url or META_DEFAULT_IMAGE_URL.")
            container = await asyncio.to_thread(_graph_post, f"{ig}/media", {
                "image_url": image_url, "caption": caption, "access_token": token})
            cid = container.get("id")
            if not cid:
                raise AdapterError(f"Meta did not return a media container: {container}")

        published = await asyncio.to_thread(_graph_post, f"{ig}/media_publish",
                                            {"creation_id": cid, "access_token": token})
        mid = published.get("id")
        if not mid:
            raise AdapterError(f"Publish step failed: {published}")
        try:
            info = await asyncio.to_thread(_graph_get, mid, {"fields": "permalink", "access_token": token})
            url = info.get("permalink") or f"https://instagram.com/p/{mid}"
        except AdapterError:
            url = f"https://instagram.com/p/{mid}"
        return PublishResult(platform_post_id=mid, platform_url=url)


# --- registry ----------------------------------------------------------------

_REGISTRY: dict[str, PlatformAdapter] = {}


def _default_registry() -> dict[str, PlatformAdapter]:
    platforms = ["instagram", "facebook", "linkedin", "tiktok", "twitter", "youtube"]
    reg: dict[str, PlatformAdapter] = {p: MockAdapter(p) for p in platforms}
    # Go live automatically once Meta credentials are present — otherwise stay on mock.
    if os.getenv("META_ACCESS_TOKEN") and os.getenv("META_IG_USER_ID"):
        reg["instagram"] = InstagramAdapter()
    return reg


def instagram_is_live() -> bool:
    return bool(os.getenv("META_ACCESS_TOKEN") and os.getenv("META_IG_USER_ID"))


def get_adapter(platform: str) -> PlatformAdapter:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = _default_registry()
    adapter = _REGISTRY.get(platform)
    if adapter is None:
        raise AdapterError(f"No adapter registered for platform '{platform}'.")
    return adapter


async def publish_post(payload: PublishPayload) -> PublishResult:
    """The single entry point the pipeline calls. Routes to the right adapter."""
    return await get_adapter(payload.platform).publish(payload)


# --- cross-platform engagement mirroring -------------------------------------

# One place that knows each platform's domain + display name.
_PLATFORMS: dict[str, tuple[str, str]] = {
    "instagram": ("instagram.com", "Instagram"),
    "facebook":  ("facebook.com", "Facebook"),
    "linkedin":  ("linkedin.com", "LinkedIn"),
    "tiktok":    ("tiktok.com", "TikTok"),
    "twitter":   ("x.com", "X (Twitter)"),
    "youtube":   ("youtube.com", "YouTube"),
}


def platform_name(platform: str) -> str:
    """Human display name for a platform key ('twitter' -> 'X (Twitter)')."""
    return _PLATFORMS.get(platform, (None, platform.capitalize() if platform else "your network"))[1]


def mirror_engagement(platform: str, action: str, delta: int, ref: str = "") -> dict:
    """Reflect a unified-feed engagement back onto the post's origin platform.

    Synchronous on purpose — the feed endpoints are sync, and there's no network
    hop in mock mode. This is the seam where a real adapter would call the
    platform's engagement API; today it simulates and always logs the attempt so
    the reflection is visible in the feed and in Analytics. Posts that originate
    inside Wolfie (platform 'wolfie') have no external platform to mirror to.
    """
    p = platform or ""
    if p in ("", "wolfie"):
        return {"mirrored": False, "platform": p, "detail": "Stayed in your Wolfie network"}
    if p not in _PLATFORMS:
        return {"mirrored": False, "platform": p, "detail": f"No connector for {p}"}
    verb = {"like": "Like", "repost": "Repost", "comment": "Comment"}.get(action, action.capitalize())
    pretty = _PLATFORMS[p][1]
    detail = f"{verb} synced to {pretty}" if delta >= 0 else f"{verb} removed on {pretty}"
    ref_id = hashlib.sha1(f"{p}-{action}-{ref}".encode()).hexdigest()[:10]
    return {"mirrored": True, "platform": p, "detail": detail, "platform_ref": ref_id}


def _slug(platform: str) -> str:
    return _PLATFORMS.get(platform, (f"{platform}.example", ""))[0]
