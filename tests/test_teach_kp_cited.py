"""BUG A2/B4: teach_kp_node and reteach_kp_node must surface keypoint evidence as
current_cited_chunks so the UI's glass-box 'Cited evidence' panel is populated.

Run offline (provider=none, deterministic, $0).
"""
import sqlite3

from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.nodes.teach_kp import teach_kp_node
from litnav.nodes.reteach_kp import reteach_kp_node
from litnav.nodes.teach_kp import init_concept_progress

CHUNK_ID = "chunk-evidence-1"
KP_ID = "kp-react-1"
CONCEPT_ID = 1


def _seed():
    """Seed an in-memory DB with a paper, chunk, concept, and keypoint."""
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "topic")
    paper_id = repo.create_paper(c, title="Test Paper", source_type="pdf")
    repo.create_paper_chunk(c, CHUNK_ID, paper_id, CONCEPT_ID,
                            "ReAct interleaves reasoning traces with actions.")
    repo.create_concept(c, CONCEPT_ID, "react", "ReAct")
    repo.upsert_learner_state(c, "s", CONCEPT_ID, mastery=0.3, confidence=0.0, n_observations=0)
    repo.create_keypoint(c, KP_ID, CONCEPT_ID,
                         name="ReAct loop",
                         objective="Understand the think-act-observe cycle",
                         evidence_chunk_id=CHUNK_ID,
                         sort_order=0, bloom_level="recall")
    return c


def _teach_state(cp):
    return {
        "session_id": "s",
        "route_version": 1,
        "concept_progress": cp,
        "goal_type": None,
        "intent": None,
        "target_language": "English",
        "current_cited_chunks": [],
    }


def _reteach_state(cp):
    return {
        "session_id": "s",
        "route_version": 1,
        "concept_progress": cp,
        "goal_type": None,
        "intent": None,
        "target_language": "English",
        "current_cited_chunks": [],
    }


def test_teach_kp_sets_current_cited_chunks():
    """teach_kp_node must include the keypoint's evidence_chunk_id in current_cited_chunks."""
    c = _seed()
    cp = init_concept_progress(CONCEPT_ID, c)
    state = _teach_state(cp)

    out = teach_kp_node(state, c)

    assert "current_cited_chunks" in out, "teach_kp_node did not return current_cited_chunks at all"
    assert out["current_cited_chunks"] == [CHUNK_ID], (
        f"expected [{CHUNK_ID!r}], got {out['current_cited_chunks']!r}"
    )


def test_reteach_kp_sets_current_cited_chunks():
    """reteach_kp_node must include the keypoint's evidence_chunk_id in current_cited_chunks."""
    c = _seed()
    cp = init_concept_progress(CONCEPT_ID, c)
    cp = {
        **cp,
        "current_keypoint_id": KP_ID,
        "current_bloom": "recall",
        "keypoint_state": {
            KP_ID: {
                "mastery": 0.3,
                "correct_obs": 0,
                "last_result": "wrong",
                "reteach_count": 0,
                "strategies_used": [],
            }
        },
    }
    state = _reteach_state(cp)

    out = reteach_kp_node(state, c)

    assert "current_cited_chunks" in out, "reteach_kp_node did not return current_cited_chunks at all"
    assert out["current_cited_chunks"] == [CHUNK_ID], (
        f"expected [{CHUNK_ID!r}], got {out['current_cited_chunks']!r}"
    )


def test_teach_kp_cited_chunks_empty_when_no_evidence():
    """If a keypoint has no evidence_chunk_id, current_cited_chunks must be [] not None."""
    c = _seed()
    # Add a second keypoint with no evidence
    repo.create_keypoint(c, "kp-no-evidence", CONCEPT_ID,
                         name="No evidence keypoint",
                         objective="A keypoint without an evidence chunk",
                         evidence_chunk_id=None,
                         sort_order=1, bloom_level="recall")
    cp = init_concept_progress(CONCEPT_ID, c)
    # Fast-forward to the second keypoint (no-evidence one)
    cp = {**cp, "taught_idx": 1}
    state = _teach_state(cp)

    out = teach_kp_node(state, c)

    assert "current_cited_chunks" in out, "teach_kp_node did not return current_cited_chunks"
    assert out["current_cited_chunks"] == [], (
        f"expected [] for no-evidence keypoint, got {out['current_cited_chunks']!r}"
    )
