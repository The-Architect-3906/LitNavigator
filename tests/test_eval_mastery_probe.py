from litnav.eval.mastery_probe import run_probe, always_correct, lost_then_recover


def test_always_correct_masters_every_concept_fast():
    r = run_probe(learner=always_correct)
    assert r["mastered_rate"] == 1.0
    assert r["avg_mastery_delta"] > 0.4
    assert r["avg_turns"] <= 4          # recall→comprehension→application, no reteach
    assert r["reteach_recovery"] == 1.0  # no reteach needed → vacuously full recovery


def test_lost_then_recover_still_masters_via_reteach():
    r = run_probe(learner=lost_then_recover)
    assert r["mastered_rate"] == 1.0     # a wrong-then-right learner still reaches mastery
    assert r["reteach_recovery"] == 1.0  # the reteach path recovered the concept
    assert r["avg_turns"] >= 4           # the extra wrong+reteach turn costs more turns


def test_probe_shape():
    r = run_probe()
    assert set(r) == {"mastered_rate", "avg_mastery_delta", "avg_turns", "reteach_recovery", "usd"}
