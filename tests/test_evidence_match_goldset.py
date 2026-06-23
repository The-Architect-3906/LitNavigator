"""Gold-set accuracy test for resolve_evidence_chunk.

Two synthetic "papers" (6 chunks total), 6 hand-labeled keypoints covering:
  - exact quote match (3 cases)
  - paraphrase/no-quote → embedding fallback or honest degrade (2 cases)
  - quote matching multiple chunks → id-disambiguated (1 case)

Accuracy assertions:
  - quote-exact cases must resolve to the correct chunk (precision = 1.0 in this set)
  - NO case wrongly resolves to chunk 0 unless chunk 0 is actually the correct answer
  - false-positive rate (confident-wrong) must be 0 at the threshold

A "false positive" is defined as: chunk_id is not None AND chunk_id != correct_chunk.
"""
from __future__ import annotations

import math
import pytest

from litnav.digest.evidence import resolve_evidence_chunk


# ---------------------------------------------------------------------------
# Fake embed_fn: keyword-overlap cosine (deterministic, no network)
# ---------------------------------------------------------------------------

KEYWORDS = [
    "attention", "transformer", "softmax", "recurrent", "gradient",
    "backpropagation", "layer", "normalisation", "dropout", "convolution",
]


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Return a vector per text: dim i = count of KEYWORDS[i] in text (lowercased)."""
    result = []
    for t in texts:
        t_low = t.lower()
        result.append([float(t_low.count(kw)) for kw in KEYWORDS])
    return result


# ---------------------------------------------------------------------------
# Two synthetic papers (6 chunks total, 3 per paper)
# ---------------------------------------------------------------------------

# Paper 1 — about Transformer architecture
PAPER1_CHUNKS = {
    "p1c0": (
        "The attention mechanism computes a weighted softmax over the key-query dot products, "
        "then multiplies by the value matrix to produce context-aware representations."
    ),
    "p1c1": (
        "Multi-head attention applies several attention heads in parallel. Each head operates "
        "on a different linear projection of the input, allowing the transformer to jointly "
        "attend to information from different representation subspaces."
    ),
    "p1c2": (
        "Layer normalisation is applied after each sub-layer in the transformer. "
        "Dropout regularisation is also used to prevent overfitting during training."
    ),
}

# Paper 2 — about training deep networks
PAPER2_CHUNKS = {
    "p2c0": (
        "Backpropagation computes the gradient of the loss with respect to each parameter "
        "by applying the chain rule layer by layer through the network."
    ),
    "p2c1": (
        "Recurrent neural networks maintain a hidden state that is updated at each timestep, "
        "allowing them to model sequential dependencies in data."
    ),
    "p2c2": (
        "Convolutional layers apply learned filters to local patches of the input, "
        "producing feature maps that capture spatial hierarchies."
    ),
}

# Combined chunk set for all tests
ALL_CHUNKS = {**PAPER1_CHUNKS, **PAPER2_CHUNKS}


# ---------------------------------------------------------------------------
# Gold-set: 6 keypoints with hand-labeled correct chunks
# ---------------------------------------------------------------------------
# Each entry: (quote, emitted_id, correct_chunk, expected_label_prefix, description)
# expected_label_prefix matches the start of the label string (for loose assertion).

GOLDSET = [
    # --- Exact-quote cases (should always resolve correctly) ---
    (
        # KP 1: exact verbatim quote from p1c0
        "computes a weighted softmax over the key-query dot products",
        "p1c0",               # emitted_id agrees → "verified"
        "p1c0",
        "verified",
        "attention softmax — exact quote + id agree",
    ),
    (
        # KP 2: exact verbatim quote from p1c1, but emitted_id wrong → "quote-exact"
        "applies several attention heads in parallel",
        "p1c0",               # emitted_id is WRONG (pointing to c0)
        "p1c1",
        "quote-exact",
        "multi-head attention — exact quote overrides wrong id",
    ),
    (
        # KP 3: exact quote from p2c0
        "computes the gradient of the loss with respect to each parameter",
        "p2c0",
        "p2c0",
        "verified",
        "backprop gradient — exact quote + id agree",
    ),
    (
        # KP 4: quote appears in BOTH p1c0 and p1c1 (the word "attention" is in both)
        # emitted_id = p1c1 → disambiguates to p1c1 → "quote-multi"
        "attention",
        "p1c1",
        "p1c1",
        "quote-multi",
        "attention multi-match — id disambiguates",
    ),
    (
        # KP 5: paraphrase / no useful quote, but emitted_id is real → "id-only"
        "sequential data modelling via hidden state",   # paraphrase — NOT verbatim in any chunk
        "p2c1",
        "p2c1",
        "id-only",
        "recurrent hidden state — paraphrase falls through to id-only",
    ),
    (
        # KP 6: no quote, no valid id → embedding must find p2c2 (convolution/spatial keywords)
        # OR degrade to paper-level. Either is acceptable; we only assert no false-positive.
        "",                   # no quote
        "JUNK_ID",            # bad emitted id
        "p2c2",               # correct answer (but resolver may not get here — that's OK)
        None,                 # label may be "embedding" or "paper-level"
        "convolutional layers — no quote, no id (embedding or degrade)",
    ),
]


# ---------------------------------------------------------------------------
# Accuracy test
# ---------------------------------------------------------------------------

def test_goldset_accuracy_and_zero_false_positives():
    """Run resolve_evidence_chunk on every gold entry, report accuracy, assert no FP."""
    n_total = len(GOLDSET)
    n_correct = 0
    n_confident_wrong = 0   # False positives: resolved != None AND resolved != correct

    results = []
    for quote, emitted_id, correct_chunk, expected_label, description in GOLDSET:
        resolved, label = resolve_evidence_chunk(
            quote=quote,
            emitted_id=emitted_id,
            chunks=ALL_CHUNKS,
            embed_fn=_fake_embed,
            sim_min=0.55,
        )
        is_correct = (resolved == correct_chunk)
        is_fp = (resolved is not None) and (resolved != correct_chunk)

        if is_correct:
            n_correct += 1
        if is_fp:
            n_confident_wrong += 1

        results.append({
            "desc": description,
            "correct_chunk": correct_chunk,
            "resolved": resolved,
            "label": label,
            "expected_label": expected_label,
            "is_correct": is_correct,
            "is_fp": is_fp,
        })

    # Print detailed report (visible with pytest -s or on failure)
    print("\n--- Gold-set Evidence Match Report ---")
    for r in results:
        status = "CORRECT" if r["is_correct"] else ("FP!" if r["is_fp"] else "degrade")
        print(
            f"  [{status:8s}] {r['desc']}\n"
            f"             resolved={r['resolved']!r} label={r['label']!r}"
            f" expected_label={r['expected_label']!r}"
        )
    match_accuracy = n_correct / n_total
    print(f"\n  Match accuracy: {n_correct}/{n_total} = {match_accuracy:.1%}")
    print(f"  False-positive rate: {n_confident_wrong}/{n_total} = {n_confident_wrong/n_total:.1%}")

    # --- Assertions ---

    # 1. No false positives (confident-but-wrong) at the threshold.
    assert n_confident_wrong == 0, (
        f"False-positive rate must be 0, got {n_confident_wrong}/{n_total}. "
        "Details above."
    )

    # 2. Quote-exact cases (KP 1-4 in the gold set, which all have verbatim quotes) must resolve
    #    correctly. These are the cases where the resolver has enough signal.
    quote_exact_cases = [r for r in results if r["expected_label"] in ("verified", "quote-exact", "quote-multi")]
    for r in quote_exact_cases:
        assert r["is_correct"], (
            f"Quote case '{r['desc']}' resolved to {r['resolved']!r} "
            f"instead of {r['correct_chunk']!r}. label={r['label']!r}"
        )

    # 3. The id-only case (KP 5) must also resolve correctly.
    id_only_cases = [r for r in results if r["expected_label"] == "id-only"]
    for r in id_only_cases:
        assert r["is_correct"], (
            f"Id-only case '{r['desc']}' resolved to {r['resolved']!r} "
            f"instead of {r['correct_chunk']!r}."
        )

    # 4. Overall accuracy must be at least 4/6 (83%) — even if KP 6 degrades to paper-level,
    #    cases 1-5 must all be correct.
    assert match_accuracy >= 4 / 6, (
        f"Match accuracy {match_accuracy:.1%} below expected minimum 66.7%."
    )


def test_chunk_zero_not_wrongly_assigned_unless_correct():
    """None of the gold-set keypoints whose correct chunk is NOT p1c0 should resolve to p1c0."""
    for quote, emitted_id, correct_chunk, expected_label, description in GOLDSET:
        if correct_chunk == "p1c0":
            continue  # c0 IS the correct answer here, so resolving to it is fine
        resolved, label = resolve_evidence_chunk(
            quote=quote,
            emitted_id=emitted_id,
            chunks=ALL_CHUNKS,
            embed_fn=_fake_embed,
            sim_min=0.55,
        )
        assert resolved != "p1c0", (
            f"'{description}': resolved to p1c0 (first chunk) but correct is {correct_chunk!r}. "
            f"label={label!r}. This is the B1 collapse bug."
        )
