# B1 evidence quote-match — live verification

Goal "how do agents remember things across steps", live digest (gpt-5.4-mini), top-3 sources.

**Result: 8 keypoints → 5 DISTINCT evidence chunks** (c0, c1, c5, c6, c12), 0 paper-level, NOT all-c0.
Before the fix: every keypoint collapsed to c0 (the abstract). Now keypoints spread across chunks
from multiple sources (c12 = a later source), so the "cited evidence" panel shows concept-specific
evidence. Resolver: quote-substring authority + id corroboration + embedding fallback (now wired
live) + honest paper-level degrade; never c0-by-default. 530 tests green, gates G0–G3 pass,
gold-set 5/6 exact-match / 0% false-positive.
