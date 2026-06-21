# OW-5 — make-artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Implement spec §6.4 `make-artifact`: given concept_ids + a scenario, **select** the right format and render it — mind-map, concise notes, slides, worked-example, or a combination — every artifact carrying source citations and a retrieval prompt.

**Architecture:** `litnav/artifact/` — a deterministic format **selector** (the §6.4 matrix), four renderers (mind-map is deterministic from `concept_graph()`; notes/slides/worked-example are cheap-LLM with offline fallbacks), and an orchestrator that selects → renders → writes a file → returns `{artifact_path, format, citations}`. Cross-cutting: Mayer (concise, graphics+text), a retrieval prompt per segment, citations from each concept's evidence.

**Tech Stack:** Python, `litnav.ui.trace.concept_graph`, `litnav.llm.router` (cheap tier, metered), `litnav.storage.repo`, `pytest`. Slides = Marp Markdown (pptx via marp-cli is an external post-step; we emit the Marp `.md`). Build order per spec: mind-map → notes → slides → worked-example. Baseline: **252 passed**.

## Spec §6.4 → task trace
| §6.4 element | Task |
|---|---|
| In/Out contract `{concept_ids, scenario, format?}` → `{artifact_path, format, citations}` | T1 |
| Format-selection matrix (survey→map, reference→notes, applied→worked, present→slides, mastery→combo) | T1 |
| mind-map (Mermaid from `concept_graph()`) — build first, ~free | T2 |
| concise notes (Cornell: cues + summary, not verbatim) | T3 |
| slides (Marp; multi-stage decompose → schema → thin DSL) | T4 |
| worked example (+ one practice item) | T5 |
| combination (map + notes + worked) for deep mastery | T6 |
| cross-cutting: retrieval prompt per segment; citations on every artifact | every renderer; gated in T7 |

---

## Task 1: contract + format selector

**Files:** Create `litnav/artifact/__init__.py`, `litnav/artifact/contract.py`, `litnav/artifact/selector.py`; Test `tests/test_artifact_selector.py`.

- [ ] **Step 1: failing test** `tests/test_artifact_selector.py`:
```python
from litnav.artifact.contract import ArtifactInput, ArtifactResult, FORMATS
from litnav.artifact import selector

def test_formats_set():
    assert FORMATS == {"mindmap", "notes", "slides", "worked_example", "combination"}

def test_selector_matrix():
    s = selector.select_format
    assert s({"goal_type": "survey", "content_kind": "structure", "user_request": ""}) == "mindmap"
    assert s({"goal_type": "functional", "content_kind": "procedure", "user_request": "how to build X"}) == "worked_example"
    assert s({"goal_type": "mastery", "content_kind": "reference", "user_request": "quick recall"}) == "combination"
    assert s({"goal_type": None, "content_kind": "reference", "user_request": "crash course"}) == "notes"
    assert s({"goal_type": None, "content_kind": "present", "user_request": "make a deck"}) == "slides"

def test_format_override_wins():
    assert selector.select_format({"goal_type": "survey"}, override="notes") == "notes"
```
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** `contract.py`: `FORMATS = {"mindmap","notes","slides","worked_example","combination"}`; `@dataclass ArtifactInput(concept_ids: list[int], scenario: dict, format: str|None=None)`; `@dataclass ArtifactResult(artifact_path: str, format: str, citations: list[str])`. `selector.py::select_format(scenario, override=None) -> str` implementing the §6.4 matrix with this precedence: explicit `override` → "slides" (present/deck/slides cues) → "worked_example" (functional / procedure / applied / "how to") → "mindmap" (survey / systematic / structure / "map"/"relate") → "combination" (mastery) → "notes" (default: reference/crash-course/quick-recall).
- [ ] **Step 4:** run + `pytest -q` (expect 254). Report.
- [ ] **Step 5: commit** `feat(ow5): make-artifact contract + format-selection matrix (spec §6.4)`.

---

## Task 2: mind-map renderer (deterministic, from concept_graph)

**Files:** Create `litnav/artifact/renderers/__init__.py`, `litnav/artifact/renderers/mindmap.py`; Test `tests/test_artifact_mindmap.py`.

- [ ] **Step 1:** Read `litnav/ui/trace.py::concept_graph(conn, session_id)` for the exact return shape (concepts + edges). The mind-map is deterministic Mermaid — no LLM.
- [ ] **Step 2: failing test** — `mindmap.render(graph, citations)` returns a Mermaid block (` ```mermaid ` … `graph TD`), one node per concept (slug→name), `-->` for prerequisite edges and `-.->` for similarity edges, ends with a **retrieval prompt** line and a **Citations:** section listing the citation ids.
- [ ] **Step 3:** implement `mindmap.render(graph: dict, citations: list[str]) -> str` (graph = `{"concepts":[{slug,name}], "edges":[{prereq_slug,target_slug,edge_type}]}`). Deterministic; sanitize names for Mermaid; append `\n> Recall prompt: …` and `\nCitations: <ids>`.
- [ ] **Step 4:** run + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow5): deterministic mind-map renderer (Mermaid from concept_graph) + citations`.

---

## Task 3: concise notes renderer (Cornell-style)

**Files:** Create `litnav/artifact/renderers/notes.py`; Test `tests/test_artifact_notes.py`.

- [ ] **Step 1: failing test** — `notes.render(concepts, evidence_by_concept, *, conn, session_id)` produces Cornell-style markdown (a **Cues** column + a **Summary**), NOT verbatim evidence; ends each concept segment with a **retrieval prompt**; carries citations. Offline (provider=none) → a deterministic templated note from concept names/keypoints (no LLM). Live → cheap LLM, grounded in evidence, with the anti-verbatim instruction.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement via `router.complete_json(tier="cheap", stage="artifact", ...)` (cues+summary per concept) with an offline fallback that templates from keypoints. Mayer rule: concise, no extraneous; append a retrieval prompt per concept + a Citations section.
- [ ] **Step 4:** run + `pytest -q` + `verify_*` unaffected. Report.
- [ ] **Step 5: commit** `feat(ow5): Cornell-style concise notes renderer (cheap LLM + offline template) + retrieval prompts`.

---

## Task 4: slides renderer (Marp, multi-stage)

**Files:** Create `litnav/artifact/renderers/slides.py`; Test `tests/test_artifact_slides.py`.

- [ ] **Step 1: failing test** — `slides.render(concepts, evidence_by_concept, *, conn, session_id)` returns valid **Marp Markdown** (front-matter `marp: true`, `---` slide separators), one section per concept, a title slide, each content slide ending with a retrieval prompt, a final Citations slide. Multi-stage: a cheap-LLM decompose into a strict JSON outline (`{"slides":[{title,bullets}]}`), then a deterministic Marp emitter over that outline (the "thin DSL over the renderer"). Offline → templated outline from concepts.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement: `_outline(...)` via `router.complete_json(tier="cheap", stage="artifact", fallback=templated_outline)` → strict `{"slides":[...]}`; `_to_marp(outline, citations)` deterministic markdown emitter (front-matter + `---` + bullets + retrieval prompt + citations slide). Note pptx conversion (marp-cli) as an external post-step in a comment.
- [ ] **Step 4:** run + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow5): Marp slides renderer (LLM outline → deterministic Marp emitter) + citations`.

---

## Task 5: worked-example renderer (+ practice item)

**Files:** Create `litnav/artifact/renderers/worked_example.py`; Test `tests/test_artifact_worked.py`.

- [ ] **Step 1: failing test** — `worked_example.render(concepts, evidence_by_concept, *, conn, session_id)` returns markdown with a step-by-step **worked example** grounded in evidence PLUS **one practice item** (question + a hidden/【answer】) per concept, ending with a retrieval prompt + citations. Offline → templated worked example from keypoints.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement via `router.complete_json(tier="cheap", stage="artifact", fallback=templated)` (worked steps + 1 practice item); deterministic offline fallback; retrieval prompt + citations.
- [ ] **Step 4:** run + `pytest -q`. Report.
- [ ] **Step 5: commit** `feat(ow5): worked-example renderer (+ one practice item) + citations`.

---

## Task 6: make_artifact orchestrator + SKILL.md

**Files:** Create `litnav/artifact/make_artifact.py`, `litnav/artifact/SKILL.md`; Modify `.gitignore` (add `artifacts/`); Test `tests/test_make_artifact.py`.

- [ ] **Step 1: failing test** — `make_artifact(ai: ArtifactInput, *, conn, session_id, out_dir) -> ArtifactResult`: selects the format (or uses override), loads the concept graph + evidence for `concept_ids`, renders, writes a file under `out_dir` with the right extension (`.md`), returns `{artifact_path (exists), format, citations (non-empty when evidence exists)}`. `format="combination"` writes a single file concatenating map + notes + worked. Offline-deterministic for mindmap/combination.
- [ ] **Step 2: confirm FAIL.**
- [ ] **Step 3:** implement orchestrator: `select_format` → gather `{concepts, edges}` (via `concept_graph` filtered to `concept_ids`) + `evidence_by_concept` + `citations` (evidence chunk ids / paper sources for the concepts) → dispatch to the renderer(s) → write file (`out_dir/<format>.md`) → `ArtifactResult`. "combination" calls mindmap+notes+worked and concatenates. Add `SKILL.md` (contract, matrix, cross-cutting rules, build order, offline behavior). `.gitignore += artifacts/`.
- [ ] **Step 4:** run + `pytest -q` + all prior gates green. Report.
- [ ] **Step 5: commit** `feat(ow5): make_artifact orchestrator (select→render→write→citations) + SKILL.md`.

---

## Task 7: verify_artifact (offline unit) + verify_artifact_live (capability) + report

**Files:** Create `litnav/evaluation/verify_artifact.py`, `litnav/evaluation/verify_artifact_live.py`; Test `tests/test_verify_artifact.py`.

- [ ] **Offline unit gate** (`verify_artifact`): deterministic — selector matrix; mind-map renders from a fixture graph with the right edges + a retrieval prompt + citations; combination concatenates; every rendered artifact contains a citation section + a retrieval prompt. `pytest` entry.
- [ ] **LIVE gate** (`verify_artifact_live`, skips at provider=none): from a LIVE-digested concept graph, render notes + slides + worked-example; assert each is non-empty, carries citations that resolve to real chunks, contains a retrieval prompt, and was metered (cost_ledger stage=artifact). Print cost.
- [ ] **commit** `feat(ow5): verify_artifact offline unit gate + verify_artifact_live capability gate`.

## Controller live verification → three-part report (NOT a subagent task)
Run `verify_artifact_live` LIVE; produce the three-part report (live usage + cost table + evaluation: do the selected formats match the scenario? citations resolve? optimize? actions). Update `docs/OPEN-WORLD-STATUS.md` + README OW-5 rows. Final §6.4 re-check.

## Self-Review
- Every §6.4 element traced (table); build order honored (mindmap T2 → notes T3 → slides T4 → worked T5 → combination T6). ✓
- Cross-cutting (retrieval prompt + citations) in every renderer, gated in T7. ✓
- Live-first: T7 live gate + report; mindmap/selector/combination deterministic offline (gateable); notes/slides/worked have offline fallbacks so prior gates stay green. ✓
- No new ENABLED model (renderers use `cheap`); Marp→pptx is an external post-step, not a model. ✓
- Type consistency: `select_format`, `render(...)` signatures, `ArtifactInput/Result`, `make_artifact` consistent across tasks. ✓
