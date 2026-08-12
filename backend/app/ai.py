"""Content generation — provider-agnostic.

The app runs with zero credentials on ``MockProvider``, which produces brand-aware,
real-estate-flavoured content good enough to exercise the whole flow. Set
``AI_PROVIDER=anthropic`` and an ``ANTHROPIC_API_KEY`` to switch to real Claude
generation; any other provider is a matter of writing one more class with a
``generate()`` method and registering it in ``get_provider()``.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


class ContentProvider:
    def generate(self, brand: dict, fmt: str, topic: str, objective: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def answer(self, brand: dict, question: str, context: dict) -> dict:  # pragma: no cover
        raise NotImplementedError


# --- mock (default, no credentials) ------------------------------------------

class MockProvider(ContentProvider):
    name = "mock"

    HOOKS = [
        "Most investors get this wrong about {topic}.",
        "{topic}: 3 things buyers keep overlooking.",
        "Everyone's watching Dubai. Here's what {topic} actually shows.",
        "The numbers on {topic} might surprise you.",
    ]

    def generate(self, brand: dict, fmt: str, topic: str, objective: str) -> dict:
        topic = (topic or "the UAE market").strip()
        voice = brand.get("voice") or "Premium, confident, educational"
        cta = brand.get("cta") or "DM us to learn more."
        audience = brand.get("audience") or "investors"
        always = (brand.get("always_say") or "").strip()
        idx = (len(topic) + len(fmt)) % len(self.HOOKS)
        hook = self.HOOKS[idx].format(topic=topic)
        caption = (
            f"{hook}\n\n"
            f"For {audience.lower()} weighing {topic.lower()} right now — "
            f"written {voice.split(',')[0].lower()}, no fluff.\n\n"
            f"1. Look at the fundamentals, not the headline.\n"
            f"2. Compare against your own goals, not the hype.\n"
            f"3. Move when the data — and your timing — line up.\n\n"
            + (f"({always}.)\n\n" if always else "")
            + f"{cta}"
        )
        hashtags = ["#Dubai", "#RealEstate", "#UAEProperty", "#Investment", "#" + re.sub(r"\W+", "", topic.title())]
        result: dict[str, Any] = {
            "provider": self.name,
            "title": hook,
            "caption": caption,
            "hashtags": hashtags,
        }
        if fmt == "carousel":
            result["slides"] = [
                {"heading": hook, "body": "Swipe for the 3 things that matter →"},
                {"heading": "1. Fundamentals first", "body": "Yield, location, and handover — before anything else."},
                {"heading": "2. Fit your goals", "body": "Rental income vs. capital growth vs. residency."},
                {"heading": "3. Timing", "body": "Enter when the data and your plan agree."},
                {"heading": "Ready to check your options?", "body": cta},
            ]
        return result

    def answer(self, brand: dict, question: str, context: dict) -> dict:
        """A grounded analyst answer built from the real analytics context — no
        credentials needed. Routes on the question, always cites actual numbers."""
        q = (question or "").lower()
        t = context.get("totals") or {}
        formats = context.get("formats") or []
        topics = context.get("topics") or []
        best = context.get("best")
        recs = context.get("recommendations") or []
        synced = context.get("synced") or []
        er = round((t.get("engagement_rate") or 0) * 100, 1)

        def num(n: Any) -> str:
            n = int(n or 0)
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)

        top_fmt = formats[0] if formats else None
        top_topic = topics[0] if topics else None
        lines: list[str] = []

        if not t.get("posts"):
            lines.append("You don't have any published posts yet, so there's nothing to analyse.")
            lines.append("Once a few go out, ask me **what's working**, **what to post next**, or **which format wins** — I'll answer from your real numbers.")
        elif any(k in q for k in ("format", "reel", "carousel", "static", "video")):
            lines.append(f"Your strongest format is **{top_fmt['format']}** — {top_fmt['score']}/10 against your own baseline, averaging **{num(top_fmt['avg_reach'])} reach** across {top_fmt['count']} posts.")
            if len(formats) > 1:
                weak = formats[-1]
                lines.append(f"Your weakest is **{weak['format']}** ({weak['score']}/10) — either rethink the angle or pair it with a stronger topic.")
            if top_topic:
                lines.append(f"Move: make more **{top_fmt['format']}s**, especially on **{top_topic['pillar']}**, your best topic.")
        elif any(k in q for k in ("topic", "pillar", "theme", "subject", "about")):
            lines.append(f"Your best-performing topic is **{top_topic['pillar']}** ({top_topic['score']}/10) — it drives the most saves + shares relative to reach.")
            if len(topics) > 1:
                lines.append(f"Right behind it: **{topics[1]['pillar']}** ({topics[1]['score']}/10).")
            weakish = [x for x in topics if x["score"] < 4]
            if weakish:
                lines.append(f"**{weakish[0]['pillar']}** is underperforming — improve the hook or post it less.")
        elif any(k in q for k in ("next", "post next", "idea", "recommend", "should i")):
            if recs:
                r = recs[0]
                lines.append(f"Post this next: a **{r['format']}** on **{r['pillar']}** — “{r['title']}”.")
                lines.append(f"Why: {r.get('why', '')}")
                if len(recs) > 1:
                    lines.append(f"Runner-up: a **{recs[1]['format']}** on **{recs[1]['pillar']}**.")
            else:
                lines.append("Publish a couple more posts and I'll start ranking exactly what to post next.")
        elif any(k in q for k in ("platform", "instagram", "linkedin", "facebook", "tiktok", "twitter", "channel", " x ")):
            if synced:
                top = synced[0]
                lines.append(f"Most of your unified-feed engagement is reflecting on **{top['platform']}** ({top['net']} reflected across {top['events']} actions).")
            lines.append("Your published mix leans on Instagram for reach; **LinkedIn** is your best channel for education and lead-gen content.")
        else:
            lines.append(f"Here's your shape: **{t.get('posts')} posts**, **{num(t.get('reach'))} total reach**, **{er}% engagement rate** vs your own baseline.")
            if top_fmt:
                lines.append(f"Best format: **{top_fmt['format']}** ({top_fmt['score']}/10). Best topic: **{top_topic['pillar']}** ({top_topic['score']}/10).")
            if best:
                lines.append(f"Standout post: **{best['pct']:+d}%** above your normal {best['format']} — “{best['title']}”.")
            if recs:
                lines.append(f"My #1 move for you: a **{recs[0]['format']}** on **{recs[0]['pillar']}**.")

        return {"provider": self.name, "answer": "\n\n".join(lines)}


# --- anthropic (optional) ----------------------------------------------------

class AnthropicProvider(ContentProvider):
    """Real Claude generation via the official SDK. Activated only when
    AI_PROVIDER=anthropic and a key is available. Model is configurable via
    AI_MODEL (defaults to claude-opus-5)."""

    name = "anthropic"

    def generate(self, brand: dict, fmt: str, topic: str, objective: str) -> dict:
        try:
            import anthropic  # imported lazily so the app runs without the package
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("AI_PROVIDER=anthropic but the 'anthropic' package isn't installed. "
                               "Run: pip install anthropic") from exc

        model = os.getenv("AI_MODEL", "claude-opus-5")
        never = brand.get("never_say") or ""
        always = brand.get("always_say") or ""
        audience = brand.get("audience") or ""
        system = (
            "You are Wolfie, a social media copywriter for a UAE real-estate brand. "
            + f"Brand voice: {brand.get('voice','Premium, confident, educational')}. "
            + (f"Audience: {audience}. " if audience else "")
            + f"Preferred CTA: {brand.get('cta','DM us to learn more.')}. "
            + (f"Always mention: {always}. " if always else "")
            + (f"Never say: {never}. " if never else "")
            + "Return ONLY valid minified JSON, no markdown fence."
        )
        shape = ('{"title","caption","hashtags":[...]' +
                 (',"slides":[{"heading","body"}]' if fmt == "carousel" else "") + "}")
        prompt = (
            f"Write a {fmt} for objective '{objective or 'engagement'}' about '{topic or 'the UAE market'}'. "
            f"Respond as JSON with this shape: {shape}"
        )
        try:
            client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY / auth profile
            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # bad key, bad model, network — surface as a clean 400
            raise RuntimeError(f"Claude request failed ({model}): {exc}") from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Model wrapped JSON in prose/fence — recover the object.
            m = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(m.group(0)) if m else {"title": topic, "caption": text, "hashtags": []}
        data["provider"] = self.name
        return data

    def answer(self, brand: dict, question: str, context: dict) -> dict:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("AI_PROVIDER=anthropic but the 'anthropic' package isn't installed. "
                               "Run: pip install anthropic") from exc
        model = os.getenv("AI_MODEL", "claude-opus-5")
        system = (
            "You are the AI Analyst inside a UAE real-estate brand's social media tool. "
            "Answer the user's question using ONLY the performance data provided as JSON — never invent numbers. "
            "Be concise and specific, cite the actual figures, and end with one clear recommendation. "
            "Plain text, short paragraphs; you may use **bold** for key terms."
        )
        prompt = (
            f"Brand: {brand.get('name', '')} — voice: {brand.get('voice', '')}.\n"
            f"Performance data (JSON):\n{json.dumps(context)}\n\n"
            f"Question: {question}"
        )
        try:
            client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY
            resp = client.messages.create(
                model=model, max_tokens=800, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise RuntimeError(f"Claude request failed ({model}): {exc}") from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return {"provider": self.name, "answer": text or "I couldn't produce an answer from the data."}


def get_provider() -> ContentProvider:
    choice = os.getenv("AI_PROVIDER", "mock").lower()
    if choice == "anthropic":
        return AnthropicProvider()
    return MockProvider()
