from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/runtime/litnav.sqlite"
    llm_provider: str = "none"
    llm_api_key: str = ""
    use_network: bool = False


def load_settings() -> Settings:
    return Settings(
        db_path=os.getenv("LITNAV_DB_PATH", "data/runtime/litnav.sqlite"),
        llm_provider=os.getenv("LITNAV_LLM_PROVIDER", "none"),
        llm_api_key=os.getenv("LITNAV_LLM_API_KEY", ""),
        use_network=os.getenv("LITNAV_USE_NETWORK", "false").lower() == "true",
    )
