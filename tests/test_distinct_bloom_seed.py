"""RC#2: the backfilled higher-Bloom seed must NOT be a verbatim copy of the recall seed.

Digest used to fill a missing comprehension seed by copying the recall question's exact text +
relabeling bloom_level, so the bloom-climb re-posed identical words ("rising to comprehension" changed
a hidden tag, not the question) — the most-cited live-test complaint (B3, 8/10 scenarios). The derived
rung must carry distinct question text (live: LLM-generated; offline: a deterministic reframe).
"""
from litnav.digest import pipeline


def test_backfilled_comprehension_seed_is_not_verbatim_recall():
    concepts = [{"slug": "react", "name": "ReAct"}]
    kps = [{"kp_id": "kp1", "concept_slug": "react"}]
    candidate = {"quiz_seeds": [
        {"concept_slug": "react", "keypoint_id": "kp1",
         "question": "What is the ReAct loop?", "answer_key": "reason + act + observe",
         "bloom_level": "recall"},
    ]}
    seeds = pipeline._propose_quiz_seeds(concepts, {}, candidate, keypoints=kps,
                                         session_id=None, conn=None, budget=None)  # offline
    by_rung = {s["bloom_level"]: s for s in seeds if s["keypoint_id"] == "kp1"}
    assert "recall" in by_rung and "comprehension" in by_rung, "both rungs should be seeded"
    assert by_rung["comprehension"]["question"] != by_rung["recall"]["question"], \
        "comprehension seed is a verbatim copy of recall (RC#2/B3)"
    assert by_rung["comprehension"]["question"].strip(), "comprehension question must be non-empty"
