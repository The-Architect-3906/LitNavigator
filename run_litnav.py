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


def _env_candidates() -> list[Path]:
    # Where a user might place the .env. The exe dir is the documented spot, but the frozen
    # layout can make sys.executable's dir ambiguous, so we also try the CWD and the parent
    # of the unpacked bundle. First existing match wins.
    cands: list[Path] = [Path(_exe_dir()) / ".env"]
    try:
        cands.append(Path(os.getcwd()) / ".env")
    except Exception:
        pass
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        cands.append(Path(mp).parent / ".env")
    seen: set[str] = set()
    out: list[Path] = []
    for p in cands:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _load_user_env() -> str | None:
    # Optional .env placed NEXT TO the executable (so a user can supply their own key).
    # The user's .env WINS over any inherited/system env (override, not setdefault) — otherwise
    # a stray LITNAV_LLM_PROVIDER in the environment would silently keep the exe offline.
    for envp in _env_candidates():
        try:
            if not envp.exists():
                continue
            text = envp.read_text(encoding="utf-8-sig")  # tolerate a BOM
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                if key:
                    os.environ[key] = value.strip().strip('"').strip("'")
        return str(envp)
    return None


def main() -> None:
    used_env = _load_user_env()
    os.environ.setdefault("LITNAV_LLM_PROVIDER", "none")  # offline-safe default
    provider = os.environ.get("LITNAV_LLM_PROVIDER", "none")
    mode = "LIVE open-world (discovers real sources)" if provider != "none" else "offline ($0, no key)"
    # Write a tiny startup log next to the exe so a user can SEE whether live mode engaged.
    try:
        (Path(_exe_dir()) / "litnav_startup.log").write_text(
            f"LitNavigator\n.env used : {used_env or 'none found — running offline'}\n"
            f"provider  : {provider}\nmode      : {mode}\n", encoding="utf-8")
    except Exception:
        pass
    os.chdir(_resource_base())  # so relative data/seed + templates resolve when frozen

    import uvicorn

    from litnav.ui.server import app

    print(f"LitNavigator starting (provider={provider}, mode={mode}). Open {URL}")
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(URL)), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
