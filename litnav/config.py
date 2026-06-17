from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no dependency). Real environment variables win (setdefault).
    Called only from CLI/server entry points, so tests and gates stay offline by default."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key:
            os.environ.setdefault(key, value)

# Dedicated, gitignored demo databases. The CLI demo runner writes here and only
# ever deletes these files, so it can never erase whatever LITNAV_DB_PATH points at.
DEMO_DB_PATH = "data/runtime/litnav-demo.sqlite"
DEMO_CKPT_PATH = "data/runtime/litnav-demo-ckpt.sqlite"


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
