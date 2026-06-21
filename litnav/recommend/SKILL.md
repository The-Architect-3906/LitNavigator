---
name: recommend-next
description: >
  Graph-derived, deterministic "what to learn next" recommender. Given a
  session's concept graph and learner mastery, returns a ranked list of
  candidate concepts — eligible (all prereqs mastered) first, then blocked.
  Entry point: recommend_next(conn, session_id, *, mastery_threshold, k).
---

## Contract

```python
# Input
recommend_next(
    conn: sqlite3.Connection,   # domain DB (concepts + concept_edges + learner_state)
    session_id: str,            # identifies the learner's mastery rows
    *,
    mastery_threshold: float = 0.75,   # mastery >= threshold → concept is "mastered"
    k: int = 5,                        # cap on returned recommendations
) -> list[Recommendation]

# Output
@dataclass
Recommendation(
    concept_id: int,
    slug: str,
    name: str,
    score: float,    # unlock potential: # not-yet-mastered concepts this directly unlocks
    reason: str,     # human-readable ("Ready now — unlocks N concepts" | "Blocked — needs X first")
    eligible: bool,  # True iff all prereqs are mastered (or concept has no prereqs)
)
```

## Hard-prereq filter

A concept is **eligible** only when every `prerequisite` edge pointing at it comes
from a concept whose mastery ≥ `mastery_threshold`. Concepts with no prerequisite
edges are always eligible.

## Mastery-gain ranker

Among candidates (not yet mastered):

| Priority | Key                                      |
|----------|------------------------------------------|
| 1st      | `eligible` before non-eligible           |
| 2nd      | `score` desc — more downstream unlocks wins |
| 3rd      | fewer remaining unmastered prereqs (asc) |
| 4th      | `concept_id` asc (stable tie-break)      |

`score` = number of *not-yet-mastered* direct downstream concepts that list
this concept as a prerequisite (unlock potential, recomputed per call).

## Design notes

- **Deterministic — no LLM.** All logic derived from the concept graph and mastery
  values in the domain DB. Safe to call offline, $0 cost.
- Reads three tables: `concepts`, `concept_edges` (edge_type='prerequisite'),
  `learner_state` (for the given session_id; missing rows default to mastery 0.0).
- Returns eligible candidates first so callers can split "ready now" vs "blocked"
  by filtering on `Recommendation.eligible`.
