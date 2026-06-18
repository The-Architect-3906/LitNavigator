"""Standalone desktop entry point for the LitNavigator demo (PyInstaller target).

Double-click the built executable -> it starts the local server and opens the browser.
Offline by default (LITNAV_LLM_PROVIDER=none): runs the full agentic flow deterministically,
no API key, no cost. To enable live LLM teaching, drop a `.env` next to the executable with:
    LITNAV_LLM_PROVIDER=openai
    LITNAV_LLM_API_KEY=sk-...
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

URL = "http://127.0.0.1:8000/tutor"


def _resource_base() -> str:
    # PyInstaller extracts bundled data to sys._MEIPASS; in dev it's this file's dir.
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_user_env() -> None:
    # Optional .env placed NEXT TO the executable (so a user can supply their own key).
    envp = Path(_exe_dir()) / ".env"
    if not envp.exists():
        return
    for line in envp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    _load_user_env()
    os.environ.setdefault("LITNAV_LLM_PROVIDER", "none")  # offline-safe default
    os.chdir(_resource_base())  # so relative data/seed + templates resolve when frozen

    import uvicorn

    from litnav.ui.server import app

    provider = os.environ.get("LITNAV_LLM_PROVIDER", "none")
    print(f"LitNavigator starting (provider={provider}). Open {URL}")
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(URL)), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
