from __future__ import annotations

import os

# Token usage of the most recent complete_json call (0 when provider=none / no call made).
# Callers read this to record token_cost; offline runs honestly report 0.
LAST_TOKEN_COST = 0


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict) -> dict:
    """Call the configured LLM and return a JSON dict, or return fallback when provider=none."""
    global LAST_TOKEN_COST
    LAST_TOKEN_COST = 0
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
                LAST_TOKEN_COST = int(response.usage.total_tokens or 0)
            except Exception:
                LAST_TOKEN_COST = 0
            return json.loads(response.choices[0].message.content)
        except Exception:
            return fallback

    return fallback
