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


def get_provider() -> ContentProvider:
    choice = os.getenv("AI_PROVIDER", "mock").lower()
    if choice == "anthropic":
        return AnthropicProvider()
    return MockProvider()
