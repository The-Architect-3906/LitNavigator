import os

import pytest

from litnav import app
from litnav.config import DEMO_DB_PATH
from pathlib import Path

_LOCK = Path(DEMO_DB_PATH).with_suffix(".lock")


def _clear():
    if _LOCK.exists():
        _LOCK.unlink()


def test_demo_lock_acquires_and_releases():
    _clear()
    with app._demo_db_lock():
        assert _LOCK.exists(), "lockfile held inside the context"
        assert app._lock_holder_pid(_LOCK) == os.getpid(), "holder PID recorded"
    assert not _LOCK.exists(), "lockfile released on exit"


def test_pid_alive_true_for_self_false_for_invalid():
    assert app._pid_alive(os.getpid()) is True
    assert app._pid_alive(0) is False
    assert app._pid_alive(-1) is False


def test_reclaims_lock_from_dead_holder(monkeypatch):
    """A lock left by a crashed run (PID no longer alive) is reclaimed, not waited on."""
    _clear()
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    _LOCK.write_text("424242")  # some PID that we will declare dead
    monkeypatch.setattr(app, "_pid_alive", lambda pid: False)
    with app._demo_db_lock(timeout=0.0):
        assert _LOCK.exists()
        assert app._lock_holder_pid(_LOCK) == os.getpid(), "we now own it"
    assert not _LOCK.exists()


def test_does_not_steal_from_live_holder(monkeypatch):
    """A live holder is never stolen; a busy live holder past timeout raises, not steals."""
    _clear()
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    _LOCK.write_text("424242")
    monkeypatch.setattr(app, "_pid_alive", lambda pid: True)
    with pytest.raises(RuntimeError, match="locked by a running demo"):
        with app._demo_db_lock(timeout=0.1):
            pass
    assert _LOCK.read_text().strip() == "424242", "live holder's lock left intact"
    _clear()
