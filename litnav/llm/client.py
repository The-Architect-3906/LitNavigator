from __future__ import annotations

import os
import threading

# Per-thread token cost: each calling thread sees its own counter so concurrent
# sessions do not bleed cost into each other's records.
_tls = threading.local()


def last_token_cost() -> int:
    """Return the token cost of the most recent complete_json call on this thread (0 offline)."""
    return getattr(_tls, "cost", 0)


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict) -> dict:
    """Call the configured LLM and return a JSON dict, or return fallback when provider=none."""
    _tls.cost = 0
    provider = os.getenv("LITNAV_LLM_PROVIDER", "none")

    if provider == "none":
        return fallback

    if provider == "qwen":
        try:
            import json

            from openai import OpenAI
            client = OpenAI(
                api_key=os.getenv("LITNAV_LLM_API_KEY", ""),
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            response = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            try:
                _tls.cost = int(response.usage.total_tokens or 0)
            except Exception:
                pass
            return json.loads(response.choices[0].message.content)
        except Exception:
            return fallback

    return fallback
