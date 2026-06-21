---
name: make-artifact
description: >
  Use when the user wants a study artifact (concept map, notes, slide deck,
  worked example, or a combined all-in-one) generated from a set of mastered
  or target concepts. Entry point: make_artifact(ArtifactInput, conn, session_id, out_dir).
---

## Contract

```python
# Input
ArtifactInput(
    concept_ids: list[int],   # concepts to cover (order preserved)
    scenario: dict,           # {goal_type, content_kind, user_request}
    format: str | None,       # override; None → auto-selected
)

# Output
ArtifactResult(
    artifact_path: str,       # absolute path to written .md file
    format: str,              # effective format used
    citations: list[str],     # chunk IDs included, deduped, in evidence order
)
```

## Format-selection matrix (spec §6.4)

| Trigger (checked in order)                                      | Format          |
|-----------------------------------------------------------------|-----------------|
| `override` in FORMATS                                           | `override`      |
| content_kind / user_request contains slide/deck/present/talk    | `slides`        |
| goal_type == "functional" OR request contains procedure/build   | `worked_example`|
| goal_type == "mastery"                                          | `combination`   |
| goal_type in survey/systematic OR request contains map/overview | `mindmap`       |
| default (reference / crash-course / quick recall)              | `notes`         |

## Cross-cutting rules

- **Mayer concision** — renderers must distil, never copy verbatim evidence.
- **Retrieval prompt** — every renderer section ends with a recall/self-test prompt.
- **Citations on every artifact** — `ArtifactResult.citations` lists all chunk IDs
  used as evidence; each renderer footer repeats them.

## Build order / renderer capabilities

| Format          | LLM required? | Offline behaviour                          |
|-----------------|---------------|--------------------------------------------|
| `mindmap`       | No            | Fully deterministic Mermaid graph          |
| `notes`         | Cheap (opt.)  | Deterministic Cornell template             |
| `slides`        | Cheap (opt.)  | Deterministic Marp template                |
| `worked_example`| Cheap (opt.)  | Deterministic step template                |
| `combination`   | Cheap (opt.)  | mindmap (det.) + notes + worked — one file |

`combination` concatenates mindmap → notes → worked_example with `\n\n---\n\n`.

## Data queries (exact — do not deviate)

```sql
-- concepts
SELECT id, slug, name FROM concepts WHERE id=?

-- edges (filter in Python: both endpoints in selected id set)
SELECT prereq_concept, target_concept, edge_type FROM concept_edges

-- evidence + citations (per concept)
SELECT id, text FROM paper_chunks
WHERE concept_id=? ORDER BY chunk_index, id
```
