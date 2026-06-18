import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.ui.cost import session_cost


def _conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "agents")
    return c


def test_zero_cost_when_no_turns():
    c = _conn()
    assert session_cost(c, "s") == {"tokens": 0, "usd": 0.0}


def test_sums_token_cost_across_turns():
    c = _conn()
    for tok in (281, 190, 64):
        repo.record_tutor_turn(c, "s", 1, "teach", "direct",
                               pre_check_score=0.0, post_check_score=1.0,
                               cited_chunks=[], token_cost=tok,
                               mastery_after=0.8, confidence_after=0.4)
    out = session_cost(c, "s")
    assert out["tokens"] == 535
    assert out["usd"] == round(535 / 1000 * 0.0004, 5)
