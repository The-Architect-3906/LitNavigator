from litnav.discover.contract import Source
from litnav.discover.rank import survey_bonus, rank_sources


def test_bonus_intent_scaled():
    assert survey_bonus("survey") >= survey_bonus(None) >= survey_bonus("cutting-edge")
    assert survey_bonus("crash-course") > survey_bonus("cutting-edge")
    assert survey_bonus("cutting-edge") >= 0.0


def _src(title, auth, review):
    return Source("web", title, None, title, authority_score=auth, is_review=review)


def test_review_floats_up_for_survey_intent_offline():
    # offline (conn=None) → score = authority + survey_bonus(intent)
    prim = _src("Primary", 0.50, False)
    rev = _src("A Survey", 0.45, True)
    out = rank_sources("graphs", [prim, rev], conn=None, session_id=None, k=2, intent="survey")
    assert out[0].title == "A Survey"          # 0.45 + 0.20 > 0.50

    out2 = rank_sources("graphs", [prim, rev], conn=None, session_id=None, k=2, intent="cutting-edge")
    assert out2[0].title == "Primary"          # 0.45 + 0.05 < 0.50


def test_no_review_unaffected():
    a = _src("A", 0.6, False)
    b = _src("B", 0.4, False)
    out = rank_sources("x", [b, a], conn=None, session_id=None, k=2, intent="survey")
    assert out[0].title == "A"                 # higher authority wins; no bonus applied
