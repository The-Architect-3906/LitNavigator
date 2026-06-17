from pathlib import Path

from litnav import app
from litnav.config import DEMO_DB_PATH

_LOCK = Path(DEMO_DB_PATH).with_suffix(".lock")


def test_demo_lock_acquires_and_releases():
    if _LOCK.exists():
        _LOCK.unlink()
    with app._demo_db_lock():
        assert _LOCK.exists(), "lockfile held inside the context"
    assert not _LOCK.exists(), "lockfile released on exit"


def test_demo_lock_steals_stale_lock():
    """A leftover lock from a crashed run must not wedge future demos."""
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    _LOCK.write_text("stale")  # simulate a holder that died without releasing
    with app._demo_db_lock(timeout=0.0):  # immediately treat as stale and steal
        assert _LOCK.exists()
    assert not _LOCK.exists()
