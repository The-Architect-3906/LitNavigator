from __future__ import annotations

import os


def complete_json(prompt: str, *, schema_hint: str = "", fallback: dict) -> dict:
    """Call the configured LLM and return a JSON dict, or return fallback when provider=none."""
    provider = os.getenv("LITNAV_LLM_PROVIDER", "none")

    if provider == "none":
        return fallback

    if provider == "qwen":
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=os.getenv("LITNAV_LLM_API_KEY", ""),
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            import json
            response = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return fallback

    return fallback
