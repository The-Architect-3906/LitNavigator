# CLAUDE.md — LitNavigator

Adaptive research tutor: reads papers, induces a concept graph (prereqs + misconceptions), and
teaches a learner adaptively. LangGraph state machine + SQLite. ICCSE 2026 Agentic AI competition.

## Commands (always use the venv)
```bash
.venv/bin/python -m pytest -q                      # full test suite
.venv/bin/python -m litnav.evaluation.verify_m0    # acceptance gates G0..G3 (offline, $0)
#   verify_m1 = prereq replan + checkpoint resume; m2 = teach/reteach/concede; m3 = induction
.venv/bin/python -m litnav.app demo-m2 --answer cot       # misconception → reteach → pass (legacy path)
.venv/bin/python -m litnav.app demo-m3                    # off-graph induction
.venv/bin/python -m litnav.app demo-intent --intent researcher   # | journalist (route re-scopes)
.venv/bin/python -m litnav.ui.server               # web tutor → http://127.0.0.1:8000/tutor
LITNAV_LIVE_GATES=1 .venv/bin/python -m litnav.evaluation.verify_live   # opt-in LIVE gates ($, needs key)
```
**Live gates** (`litnav/evaluation/verify_live*`, harness in `live_harness.py`) run the REAL LLM path
and assert invariants the offline suite can't (it replays the deterministic candidate, so it's blind to
live-only bugs — e.g. it missed that the live learner bars stayed flat). `verify_live` runs all three:
`verify_live_digest` (keypoints + objectives), `verify_live_tutor` (mastery/grading/misconception/Bloom),
`verify_live_prereq` (prereqs survive on a real chain). They SKIP unless `LITNAV_LIVE_GATES=1` + a key is
set, so default CI stays offline/$0; each runs N times and asserts k-of-N over ranges/structure (never
exact values) for non-determinism. Run pre-merge for digest/tutor changes — NOT in the default suite.
Offline by default (`provider=none`, deterministic, $0). For live LLM, create `.env` (gitignored):
`LITNAV_LLM_PROVIDER=openai`, `LITNAV_LLM_API_KEY=…`, `LITNAV_LLM_MODEL=gpt-4o-mini`. Entry points
(`app`, `ui.server`) call `load_dotenv`; the evaluation gates do NOT (they stay offline).

## Architecture
- **Graph:** `litnav/graph/builder.py` (LangGraph `StateGraph`, `SqliteSaver` checkpoint); nodes in
  `litnav/nodes/`. State contract = `NavState` (`litnav/state.py`).
- **Two teaching paths, forked at `retrieve` by whether the concept has keypoints:**
  - **Keypoint (newest):** ORIENT→TEACH→ASSESS — `orient_tour → init_kp → teach_kp → assess_next →
    grade_kp → {reteach_kp | advance_kp}`, quizzes at rising Bloom levels. Gated by
    `tests/test_keypoint_flow.py` (the milestone gates only cover the legacy path).
  - **Legacy:** `teach → check → grade → tutor_router → {advance | reteach | diagnose→replan | concede}`.
- **Induction:** `induce_scaffold` derives a prereq + misconception for an off-graph concept;
  confidence is ALWAYS rule-computed (`docs/data-contract.md`), never returned by the LLM.
- **LLM seam:** `litnav/llm/client.py` — `complete_json` / `complete_text` / `embed_texts`, each with a
  deterministic fallback so everything runs offline. On `feat/open-world-digest`: tiered `router.py` +
  `registry.py` (cheap `gpt-4o-mini` / frontier `gpt-4o`), cost metering, and strict/live mode.
- **Open-world DIGEST** (`feat/open-world-digest` only): `litnav/digest/` (extract → edges → verify →
  pipeline) turns source docs into a graph. A DISCOVER stage (source acquisition) is NOT implemented.
- **Storage:** `litnav/storage/` (`repo.py` helpers, `schema.py` idempotent migrations). Domain DB +
  separate LangGraph checkpoint DB; per-session tutor DBs under `data/runtime/`. UI reads via
  `litnav/ui/trace.py:build_trace`.

## Conventions
- Nodes call `repo.*` helpers — no raw SQL in nodes. Storage helpers don't decide routes.
- The LLM client returns content + structured fields only; **mastery, confidence, and routing are
  rule-computed**, never emitted by the model. Every LLM caller passes a deterministic fallback.
- Grade for the **key idea**, not verbatim (`grade_kp.py`) — an over-strict prompt rejects correct
  paraphrases on every model (incl. gpt-5.x); the model is rarely the lever, the prompt is.
- UI renders state/traces; it must not invent rationale. The learner model shown comes from
  `learner_state`, so nodes must persist mastery there (not only in graph state).

## Branches
`main` = tutor + legacy/induction (gated, green). `feat/open-world-digest` = main + DIGEST pipeline +
tiered router + cost metering (un-merged). `deck/iccse-pptx` = pitch-deck build.
