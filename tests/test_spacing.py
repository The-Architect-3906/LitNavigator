import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo, openworld_repo
from litnav.assess import spacing

NOW = "2026-06-20T00:00:00"

def test_schedule_review_enqueues_future_due():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    spacing.schedule_review(c, "s", 1, mastery=0.8, now=NOW)
    due = openworld_repo.due_reviews(c, "s", "2999-01-01T00:00:00")   # far future -> the row is due
    assert len(due) == 1 and due[0]["concept_id"] == 1
    assert openworld_repo.due_reviews(c, "s", NOW) == []              # not due at scheduling time

def test_higher_mastery_fast_forwards_longer():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    i_080 = spacing.interval_days(0.80)
    i_095 = spacing.interval_days(0.95)
    assert i_095 > i_080   # P>=0.95 over-practice fast-forward = longer interval

def test_log_retention_writes_row():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    spacing.log_retention(c, "s", 1, predicted=0.82, actual=0.6, probed_at=NOW)
    row = c.execute("SELECT predicted, actual FROM retention_log WHERE session_id='s' AND concept_id=1").fetchone()
    assert row == (0.82, 0.6)

def test_due_probes_wraps_due_reviews():
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, "s", topic="t")
    spacing.schedule_review(c, "s", 7, mastery=0.8, now=NOW)
    probes = spacing.due_probes(c, "s", "2999-01-01T00:00:00")
    assert any(p["concept_id"] == 7 for p in probes)
