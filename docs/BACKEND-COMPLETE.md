# Backend — What Ships Today

*Everything the LitNavigator backend does, in plain language, with the research method, the code that
implements it, and how it's verified.* Design rationale: [RESEARCH-AND-SPEC](RESEARCH-AND-SPEC.md).
Remaining work: [BACKEND-ROADMAP](BACKEND-ROADMAP.md). Measured quality: [E2E-REPORT](E2E-REPORT.md).

**Status:** 353 automated tests pass offline ($0); all live gates pass against a real provider.
A full multi-concept tutoring session (find → digest → teach → artifact → recommend) costs about **$0.02**.

---

## A real session, end to end

This is an actual live run (goal: *"Explain the basics of quantum error correction for a beginner"*,
survey depth, a learner who gets confused once then recovers). It mastered 4 concepts in 13 turns for
~$0.019.

```mermaid
flowchart TD
    U(["👤 Learner · goal in English<br/>'Explain the basics of quantum error correction for a beginner'"])

    U --> S1["① DISCOVER · skill find-sources<br/>normalize → 'quantum error correction basics' · intent = crash-course<br/>picked source: 'Quantum Error Correction Via Noise Guessing Decoding' · 4 chunks<br/><b>BM25 · embedding rerank · LLM relevance gate</b>"]
    S1 --> S2["② DIGEST · skill digest-corpus<br/>8 concepts: stabilizer_codes · QECCs · finite_blocklength · GRAND …<br/>prereq-ordered, cited graph persisted to SQLite<br/><b>RefD prereq signal · Liang 2015 · + gpt-4o edge judge</b>"]
    S2 --> S3["③ ORIENT · nodes goal_elicit + planner + orient_tour<br/>goal = survey → Bloom ceiling = comprehension<br/>route: Stabilizer Codes → QECCs → Finite Blocklength → GRAND<br/><b>Bloom's taxonomy · goal modes</b>"]

    S3 --> T["④ TEACH · node teach_kp<br/>'Stabilizer codes are a class of quantum error-correcting codes that use the<br/>stabilizer-group framework to protect quantum information from noise…'<br/><b>Mayer multimedia · worked-example · strategy policy</b>"]
    T --> Q["⑤ ASSESS · node assess_next<br/>recall quiz: 'What is the purpose of stabilizer codes in quantum error correction?'<br/><b>Bloom-leveled QG · SAQUET distractor gate · IRT difficulty</b>"]
    Q -. "👤 'I'm lost'" .-> L["node handle_lost · no grade<br/>analogy: 'Think of stabilizer codes like a group of friends<br/>solving a puzzle together…' then re-pose the question<br/><b>metacognitive re-explain · strategy switch</b>"]
    L -.-> Q
    Q -- "👤 you answer: 'to correct errors in quantum information'" --> G["⑥ GRADE · node grade_kp<br/>correct · feedback 'correctly identifies the purpose' · mastery 0.30 → 0.48<br/><b>BKT / Rasch-IRT · never LLM self-judgement</b>"]
    G -- "correct · raise Bloom → comprehension · re-quiz (0.69 → 0.81)" --> Q
    G -- "mastered at the Bloom ceiling" --> ADV["⑦ ADVANCE · node advance_kp<br/>mastery 0.81 ≥ 0.75 · confidence 0.9 → concept marked 'done'<br/><b>dual-threshold · respects Bloom ceiling</b>"]
    ADV --> NX{more concepts<br/>on the route?}
    NX -- "yes · next: QECCs → Finite Blocklength → GRAND" --> T
    NX -- "all 4 mastered" --> ART

    ART["⑧ MAKE-ARTIFACT · skill make-artifact<br/>Cornell notes in English, cited c1,c2:<br/>'## QECCs — Cues: role in quantum communication? — Summary: essential for reliable…'<br/><b>Mayer · retrieval practice · Roediger 2006</b>"]
    ART --> DONE(["✅ 4 / 4 concepts mastered · 13 turns · ~$0.019 · all live"])

    subgraph X ["Cross-cutting — every step"]
      direction LR
      OL["Outer agent loop · ReAct + Plan-and-Solve<br/>picks which skill to run, per state"]
      CS["Cost spine · one metered router<br/>model cascade · BKT/Rasch routing ≈ free · budget cap"]
    end

    classDef disc fill:#dde6f2,stroke:#3f4b5e,color:#0f1b2b;
    classDef dig fill:#c7ecd4,stroke:#258a51,color:#0c3019;
    classDef teach fill:#d7ccff,stroke:#5b49c4,color:#1c1444;
    classDef art fill:#ffd9ec,stroke:#b03a7a,color:#3d0f27;
    classDef store fill:#eaf3ff,stroke:#2d5d8f,color:#0f1b2b;
    classDef spine fill:#ffdf9e,stroke:#b3700d,color:#43280a;
    classDef user fill:#fff3bf,stroke:#b08900,color:#3d2e00;
    class U user; class S1 disc; class S2 dig; class S3 teach;
    class T,Q,L,G,ADV,NX teach; class ART art; class DONE store; class OL,CS spine;
```

| Step | What the learner experiences | How it works (method) | Code |
|--|--|--|--|
| ① Find sources | Their goal becomes an English search query; the system pulls real papers and **drops off-topic ones** before using any | BM25 + embedding re-rank; a cheap LLM relevance check | `litnav/discover/` |
| ② Build the map | The chosen source becomes 8 concepts with prerequisite links and cited evidence | RefD prereq signal (Liang 2015) + a `gpt-4o` judge | `litnav/digest/` |
| ③ Set the depth | "Survey" goal → teach to the *comprehension* Bloom level; plan a prerequisite-ordered route | Bloom's taxonomy | `litnav/nodes/goal_elicit.py`, `planner.py` |
| ④ Teach | Each idea is explained concisely, **grounded in the cited paper text** | Mayer + worked-example effect | `litnav/nodes/teach_kp.py` |
| ⑤ Quiz | A question at the current Bloom level; wrong-answer options are flaw-checked | Bloom-leveled QG + SAQUET gate + IRT difficulty | `litnav/nodes/assess_next.py`, `assess/quizgen.py` |
| ⑤′ "I'm lost" | The tutor re-explains with an analogy and **doesn't penalise** the learner | metacognitive re-explain | `litnav/nodes/handle_lost.py` |
| ⑥ Grade | The answer updates a real mastery estimate — the model never grades itself | BKT / Rasch-IRT (Corbett & Anderson 1995) | `litnav/nodes/grade_kp.py` |
| ⑦ Advance | At mastery ≥ threshold the concept is marked done; otherwise reteach or honestly concede | dual-threshold advance | `litnav/nodes/route_decider.py` |
| ⑧ Take-away | Cornell notes **in the learner's language**, with citations | Mayer + retrieval-practice (Roediger 2006) | `litnav/artifact/` |
| ⑨ What next | Prerequisite-aware ranked next concepts | hard-prereq filter + mastery-gain ranker | `litnav/recommend/` |

---

## The five stage skills

Each is a contracted, separately-testable skill the outer agent (ReAct + Plan-and-Solve,
`litnav/graph/builder.py`) invokes. Skills with a `SKILL.md` contract: **find-sources**,
**digest-corpus**, **make-artifact**, **recommend-next**. Teach/assess is the LangGraph spine itself.

### find-sources — discover real sources for any goal
`litnav/discover/` · `SKILL.md`
- Normalises any-language goal → English search query (`query.py`) so non-English goals find sources.
- Classifies intent (`intent.py`), queries OpenAlex + Wikipedia (`adapters/`), ranks by BM25 then
  embedding similarity + citation authority, de-dups (`rank.py`).
- **Relevance gate** (`relevance.py`): a cheap LLM scores each source's fit to the *specific* goal and
  drops adjacent-but-wrong ones (e.g. a PBFT paper for a Raft goal), never starving the pipeline.
- Fetches full text for the top few and sub-chunks it into citable units (`fulltext.py`).
- *Measured:* on-topic source selection rose from 44% → ~100% on the in-domain scenarios, and
  non-English discovery from 0/4 → 4/4. **Live gate:** `verify_discover_live` (~$0.0002).

### digest-corpus — turn sources into a teachable concept graph
`litnav/digest/` · `SKILL.md`
- Extracts distinct concepts + keypoints from the source text, grounded in chunks (`extract.py`).
- Proposes prerequisite + similarity edges; prerequisites use the **RefD** reference-distance signal
  blended with an LLM judge (`refd.py`, `edges.py`); a frontier `gpt-4o` judge verifies high-impact
  prerequisite edges and downgrades unsupported ones (`verify.py`). The similarity judge runs on the
  cheap tier (the prerequisite judge stays frontier) to keep cost low.
- Persists concepts, edges, keypoints, quiz seeds, and cited chunks (`pipeline.py`); confidence is
  always rule-computed, never returned by the model.
- *Measured:* prerequisite edges now survive on real evidence (RefD recovers links a lone LLM judge
  rejects). **Live gate:** `verify_digest_live` (~$0.003/digest).

### teach / assess — the adaptive inner loop
`litnav/nodes/` + `litnav/assess/` (the checkpointed LangGraph state machine)
- **Goal elicitation** (`goal_elicit.py`): one turn sets the Bloom ceiling (survey→comprehension,
  functional/mastery→application). A `repivot_goal()` helper re-elicits if the learner changes goal
  mid-session.
- **Teaching** (`teach_kp.py`): keypoint-by-keypoint, evidence-grounded; the explanation strategy
  (worked-example / analogy / concise…) is chosen from goal × expertise × current mastery
  (`assess/strategy.py`).
- **Assessment** (`assess_next.py`, `assess/quizgen.py`): questions at rising Bloom levels (varied so
  they don't repeat), multiple-choice distractors generated then flaw-gated (SAQUET), difficulty
  estimated by a weaker LLM "student" (IRT).
- **Grading** (`grade_kp.py`): mastery is updated by BKT/Rasch from the real answer; feedback explains
  *why* an answer is right or wrong and hints at the gap. When the cheap grader is unsure near the
  mastery threshold it escalates once to the frontier model.
- **Routing** (`route_decider.py`): advance at mastery + confidence; reteach with a new strategy on a
  wrong answer; re-explain on "I'm lost" without grading; if a failed concept has an un-mastered
  prerequisite, detour to teach it first (`diagnose.py` → `replan.py`); concede honestly if stuck —
  never claiming mastery it didn't reach.
- **Spacing** (`assess/spacing.py`): an FSRS-style review schedule after mastery.
- *Measured:* across 10 live scenarios all four branches (advance / reteach→recover / concede /
  lost→recover) fire correctly; teaching is in the learner's language. **Live gate:**
  `verify_teach_assess_live` (~$0.0002/turn-set).

### make-artifact — a take-away in the learner's language
`litnav/artifact/` · `SKILL.md`
- Picks the format for the scenario (`selector.py`): mind-map, Cornell notes, slides, worked-example,
  or a combination.
- Renderers (`renderers/`): mind-map is deterministic Mermaid ($0); notes/slides/worked-example use a
  cheap LLM grounded in the concept's evidence and **write in the learner's language**.
- Every artifact carries a retrieval-practice prompt and a citations section that resolves to real
  source chunks. **Live gate:** `verify_artifact_live` (~$0.0004).

### recommend-next — what to learn next
`litnav/recommend/` · `SKILL.md`
- Hard filter: a concept is eligible only if its prerequisites are mastered. Soft rank: by how many
  further concepts it unlocks. Deterministic (no LLM); returns "ready now" vs "blocked — needs X
  first". **Gate:** `verify_recommend` (offline).

### cost spine — every call metered, cheap by default
`litnav/llm/` (`router.py`, `registry.py`, `result_cache.py`, `client.py`) + `storage/cost_repo.py`
- One router is the only place models are called: a registry of approved models, tier routing
  (cheap `gpt-4o-mini` default, frontier `gpt-4o` only when needed), a per-session budget cap with an
  80% alert, a semantic result cache, and a strict-liveness mode (a dead provider raises rather than
  silently returning a fixture). Every call is written to `cost_ledger`. **Live gate:** `verify_cost_live`.

---

## Verification

**Offline (deterministic, $0):** `verify_cost`, `verify_digest`, `verify_discover`,
`verify_teach_assess`, `verify_artifact`, `verify_recommend`, plus the legacy `verify_m0…m3`. Full
suite: **`pytest -q` → 353 passed.**

**Live (real provider, metered — run with `LITNAV_LLM_PROVIDER=openai`):**

| Gate | Asserts | Cost |
|--|--|--|
| `verify_liveness` | a real call is provably distinct from a fallback | $0.000007 |
| `verify_cost_live` | budget cap fires on real accumulating spend | ~$0.00001 |
| `verify_digest_live` | concepts **persist** + the `gpt-4o` judge runs + evidence resolves | ~$0.003 |
| `verify_discover_live` | real OpenAlex/Wikipedia/arXiv; relevance gate; multilingual query | ~$0.002 |
| `verify_teach_assess_live` | goal classified, distractors flaw-gated, grade metered | ~$0.0002 |
| `verify_artifact_live` | notes/slides/worked render live; citations resolve | ~$0.0004 |
| `verify_openworld_e2e_live` | a fresh topic runs discover→digest→teach→artifact on the **persisted** graph | ~$0.003 |

The full 10-scenario quality evaluation (frontier-judge scores) is in [E2E-REPORT](E2E-REPORT.md).
