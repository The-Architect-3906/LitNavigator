# LitNavigator · Complete Implementation Spec

## Overview

LitNavigator is a **stateful tutor that grows out of the living research literature and teaches through it**, aimed at students / engineers / researchers who want to enter an unfamiliar research subfield.

It is not a literature search engine, nor an ordinary chatbot. It does four things, and all of them adapt to *you* specifically:
1. **Teach** — explain a concept to you directly (grounded in papers, with citations), instead of dumping material for you to read on your own.
2. **Test** — Socratic questioning to verify whether you truly understand, and identify your **specific misconception**.
3. **Reteach / backfill** — if you didn't get it, **re-explain a different way**; if you're missing a prerequisite, **back up and teach that**.
4. **Induce** — for a concept not in the syllabus, **derive its prerequisites and mine the field's misconceptions from the papers**, and teach you, with evidence-calibrated honesty, "where there's consensus, where there's still debate."

> **One-line positioning**: hand a fixed-curriculum tutor (Khanmigo / LearnLM) a research subfield and it has no syllabus to teach; hand a static source-grounded assistant (NotebookLM) your papers and it can generate one-shot quizzes/guides, but it doesn't model you, won't switch explanations for your misconception, and certainly won't order "what to learn first."
> **LitNavigator's moat = the adaptive tutor loop × curriculum scaffolding induced from the living literature.** Each half is mature on its own; nobody occupies the product, and it is exactly the real pain of a frontier scholar entering a new field.

It **trains no model**: the intelligence comes from retrieval + a human-curated concept skeleton + scaffolding induced from the corpus + runtime state transitions.

---

## 1. Positioning & innovation (the project's North Star)

### 1.1 Competitive structure comparison (goes straight into the deck — don't wait for judges to figure it out)

| System | Models you | Adaptive teach/test/reteach | Curriculum deps (prereqs) | Misconception diagnosis | Content from living literature | Scaffolding source |
|---|---|---|---|---|---|---|
| Elicit / SciSpace | ✗ | ✗ (search/summarize only) | ✗ | ✗ | ✓ | — |
| NotebookLM (2026) | ✗ | ✗ (one-shot static quiz/guide) | ✗ | ✗ | ✓ (your uploads) | — |
| Khanmigo / LearnLM | ✓ | ✓ | ✓ | ✓ | ✗ (fixed course) | human-authored course |
| **LitNavigator** | ✓ | ✓ | ✓ | ✓ | ✓ | **human skeleton + induced from papers** |

> None of the first three rows can check both of the last two columns at once. **That last column (scaffolding induced from living literature) is the empty square nobody occupies.**

### 1.2 Three capabilities only "teaching from living literature" makes possible (the novelty trio)

1. **Prerequisite induction**: read the papers to derive "concept B's method presupposes A, so A is a prerequisite of B," and **order the teaching sequence itself**. A fixed-curriculum tutor structurally lacks this.
2. **Misconception mining**: papers correct each other constantly ("contrary to common belief," "a common misconception is," "the naive approach fails because…"). Extract the field's **real pitfalls** from the corpus as a misconception library — it's the literature telling the tutor where the learner will go wrong.
3. **Teaching frontier disagreement**: textbooks teach settled conclusions; a literature tutor can teach, with calibrated uncertainty, "where there's consensus, where there's debate, where it's open." This is exactly what a research scholar most lacks when entering a new field.

### 1.3 Expectation calibration (for the team to stay clear-eyed)

This is **a strong applied innovation at a neglected intersection**, not "a brand-new agentic architecture breakthrough." The adaptive tutor loop itself is standard mature ITS; all the novelty rests on the "scaffolding induction + teaching the frontier" axis. So two iron rules: (a) the demo **must actually perform** at least one live literature induction; (b) the deck must explicitly benchmark against Khanmigo/NotebookLM and spell out the structural difference. The other five scoring dimensions (utility, agentic execution, presentation, responsible AI, cost) get pushed as usual.

> **Don't let the cost dimension run naked**: scoring includes "cost." Token/cost accounting should not be deferred to the end — from M1, drop a lightweight token count into `decisions` / `tutor_turns` (see §12), so the deck can report "average tokens/cost per concept learned."

---

## 2. Architecture

### 2.1 Dual nested loop + literature-induction node diagram

```
input
  ↓
init_or_load_state            ← build default learner_state for all target/prereq concepts (prevents router KeyError)
  ↓
planner                       ← topo-sort an initial route from the concept DAG (skeleton first)
  ↓
select_next_concept ──in curated DAG?──┬─ no / user brought a new concept ─► induce_scaffold ─┐
                                       │   (induce prereqs/misconceptions, write source='induced'+evidence) │
                                       └─ yes ─────────────────────────────────────────────────┤
                                                                                                ↓
┌─────────────── TUTOR INNER LOOP (teaching a single concept, the "teacher" lives here) ────────┐
│ retrieve_evidence  → teach → check → grade                                                     │
│   (teach can annotate: this is consensus / contested / open, calibrated to evidence)           │
│   ↓                                                                                            │
│ tutor_router ──┬── mastered ───────────────────────► EXIT → advance                            │
│  (four paths)  ├── misconception & prereqs OK ─► reteach ─┐ switch unused strategy, back to teach │
│                │                                  ▲────────┘                                    │
│                ├── blocked_by_prereq ─────────────────────► EXIT → diagnose_gap                 │
│                ├── reteach exhausted & prereqs OK ───────► EXIT → concede (honest exit)         │
│                └── off_path_request ──────────────────────► EXIT → refuse_jump / induce         │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ mastered / concede          │ blocked_by_prereq
        ▼                             ▼
   advance                       diagnose_gap → replan (insert prereq; if prereq not in skeleton → induce first)
        ↓                             ↓
 select_next_concept            select_next_concept → ... → finish
```

**Each loop/branch owns one thing:**
- **Inner loop (teach a single concept) = the teacher effect**: teach→check→grade→reteach on a misconception.
- **Outer loop (cross-concept orchestration) = curriculum adaptation**: advance on mastery / replan on missing prereq.
- **Induction branch = novelty**: for a concept/prereq/misconception not in the skeleton, induce from the corpus and write it in with evidence.

> `induce_scaffold` does not replace the human skeleton; it is a **second track**: the skeleton is the demo safety net (keeps the main path running), induction is the hard evidence of novelty (performed live at least once). Same philosophy as the L0/L1 retrieval tiers.

### 2.2 Node responsibilities

| Node | Responsibility | Must not do |
|---|---|---|
| `init_or_load_state` | Create/load the session's NavState; build a default ConceptState for all target concepts and their prereqs | — |
| `planner` | Topo-sort an **initial** route from the concept DAG | Don't reroute dynamically |
| `select_next_concept` | Pick the next pending concept; **judge whether it's inside the curated DAG** | — |
| `induce_scaffold` | Induce prereq edges/misconceptions from retrieved papers; write `source='induced'`+evidence+confidence | No assertion without evidence; on conflict with the skeleton, don't silently overwrite (flag as to-be-verified) |
| `retrieve_evidence` | Fetch evidence chunks for the current concept | No broad search |
| `teach` | Grounded explanation + frontier annotation + adaptation to level/misconception | Don't leave the chunk; don't rely on parametric memory; don't hallucinate citations |
| `check` | Socratic: predict/recall/transfer, bound to a chunk | Don't write questions off the evidence |
| `grade` | Judge correct/wrong + identify misconception + BKT-lite mastery update + confidence update + write evidence | **Doesn't decide routing** |
| `tutor_router` | Take **four-path** conditional edges based on state | Doesn't grade |
| `reteach` | Pick an unused strategy targeting the misconception's correct_model | No repetition; capped at 2 |
| `concede` | Honest termination when reteach is exhausted and no prereq is missing: flag the concept's confidence as low, write an S5 honest message, advance and exit | Don't pretend to have taught it; don't reteach infinitely |
| `diagnose_gap` | Use mastery + DAG to find the missing prereq | — |
| `replan` | Insert/adjust a route step + emit rationale (prereq not in skeleton → induce first) | — |

### 2.3 NavState

```python
class ConceptState(TypedDict):
    mastery: float                       # BKT posterior P(known), 0~1
    confidence: float                    # how sure the system is about that estimate (→ S5); updated by observation count, see §4.3
    n_observations: int                  # number of times this concept has been graded (input to confidence)
    evidence: list[dict]                 # which attempts back this score
    held_misconceptions: list[str]       # the specific misconception ids currently held (the soul)
    tried_strategies: list[str]          # explanation strategies used on this concept (forces reteach to switch)
    depth: Literal["recall","apply","explain"]

class NavState(TypedDict):
    session_id: str
    user_id: str | None
    # —— goal ——
    topic: str
    user_goal: str
    target_concepts: list[int]
    constraints: dict                    # P2: max_depth / prefer_recent / skip_math
    # —— graph ——
    concept_dag_version: str
    concept_dag: dict[int, list[int]]    # concept -> prereqs
    # —— learning state (the soul) ——
    learner_state: dict[int, ConceptState]
    mastery_threshold: float
    # —— route ——
    reading_path: list[dict]             # RouteStep
    current_step_id: str | None
    current_concept_id: int | None
    current_paper_id: int | None
    route_version: int                   # +1 on reroute; demo uses it to prove "it really changed"
    # —— teaching inner loop ——
    reteach_count: dict[int, int]        # concept_id -> times reteaught (for the cap)
    last_explanation_strategy: str | None
    # —— literature induction ——
    scaffold_origin: dict[int, str]      # concept_id -> 'curated' | 'induced'
    induced_edges: list[dict]            # induced prereq edges (incl. evidence_chunks, confidence)
    induced_misconceptions: list[dict]   # induced misconceptions (incl. evidence_chunks, confidence)
    frontier_flags: dict[int, str]       # concept_id -> 'consensus' | 'contested' | 'open'
    # —— RAG evidence ——
    retrieved_ctx: list[dict]            # chunk_id, paper_id, text, score, source
    cited_evidence: list[dict]
    # —— assessment ——
    quiz_items: list[dict]
    user_answers: list[dict]
    last_check_result: dict | None       # incl. concept_scores + detected_misconception
    # —— diagnosis & decision ——
    diagnosis: dict | None
    decision: Literal["advance","reteach","diagnose","replan",
                      "refuse_jump","induce","concede","finish"] | None
    decision_rationale: str
    # —— robustness (bonus) ——
    off_path_request: dict | None        # P2: used by S3 refuse_jump
    uncertainty_flags: list[str]         # P2: S5 calibrated tone
    # —— logs ——
    history: list[dict]

class RouteStep(TypedDict):
    step_id: str
    concept_id: int
    paper_id: int
    reason: str                          # "why learn this now"
    status: Literal["pending","active","done","skipped"]
    confidence: float
```

---

## 3. tutor_router: four-path conditional edges (the physical line between agent and workflow)

Decision order: mastery first, then misconception (reteachable), then missing prereq, then reteach-exhausted fallback; when the user is led off the skeleton, take `induce`.

```python
MAX_RETEACH = 2

def tutor_router(state) -> str:
    cid = state["current_concept_id"]
    cs = state["learner_state"][cid]

    # 1) mastered → advance (outer loop)
    if cs["mastery"] >= state["mastery_threshold"]:
        return "advance"

    # prereq-OK check (init already built default state for all concepts, so no KeyError here)
    prereqs = state["concept_dag"].get(cid, [])
    prereq_ok = all(state["learner_state"][p]["mastery"] >= state["mastery_threshold"]
                    for p in prereqs)

    # 2) misconception on this concept, prereqs OK, reteach not exhausted → switch strategy and reteach (inner loop)
    if cs["held_misconceptions"] and prereq_ok \
       and state["reteach_count"].get(cid, 0) < MAX_RETEACH:
        return "reteach"

    # 3) stuck on a missing prereq → back up and teach it (outer loop)
    if not prereq_ok:
        return "diagnose"

    # 4) prereqs all OK, but reteach exhausted and still not mastered → concede honestly.
    #    Returning "diagnose" here would spin forever: diagnose_gap finds no missing prereq →
    #    replan inserts nothing → back to the same concept → reteach already capped → diagnose again …
    return "concede"

# off-curriculum: judged earlier at select_next_concept
#   concept ∉ curated_dag  →  induce_scaffold  →  then enter the inner loop
```

**`concede` behavior** (node already listed in §2.2):
- Flag `cs["confidence"]` as low, append the concept to `uncertainty_flags`, write `decision_rationale`:
  "I switched explanations N times and this still hasn't landed; noting it as not-yet-mastered, you can overrule me, let's move on and come back later."
- Then advance, to avoid spinning the inner loop.
> Don't spin the inner loop to death once reteach is exhausted: honest admission > pretending to have taught it. This is also a responsible-AI (S5) bonus.

---

## 4. teach / check / grade / reteach

### 4.1 teach — explain the concept, not point at directions
- Input: concept + `learner_state[cid]` (level + held_misconceptions) + retrieved chunks.
- **Every assertion is hung on a real chunk, with a citation**; no parametric-memory teaching, no hallucinated citations (a literature tool hallucinating citations is a fatal irony).
- Directly dismantle the wrong mental model per `held_misconceptions`.
- **Frontier annotation**: based on evidence, state "this is a settled conclusion / still contested / an open problem."
- Pick the explanation strategy from a set; first pass defaults to `direct_explanation`.

### 4.2 check — a means of learning, not just an exam

| Question type | MVP | Purpose |
|---|---|---|
| MCQ | **required** | deterministic scoring, stable |
| Prediction | recommended | generation effect |
| Recall/explain | recommended | most effective at exposing misconceptions |
| Transfer/apply | bonus | tests depth=apply |

Every item is hard-bound to `evidence_chunk_id + source_paper_id`; the question prompt must be based on a retrieved chunk.

> **Parallel quiz forms (so the T5 learning gain holds up)**: for each demo-core concept, prepare **2–3 equal-difficulty parallel items** (same `evidence_chunk`, same `qtype`, same `difficulty`, only the wording/option order differs). Before and after teaching (pre/post), draw a different parallel item each time — this avoids the contamination of re-asking the same item (testing effect) while keeping difficulty comparable, so `post>pre` is a real gain and not just an easier question. Schema reuses `quiz_items.difficulty`; only the data-prep step pairs the items.

### 4.3 grade — identify "which misconception," BKT mastery update, and confidence update

The LLM only does what it's best at: judge correct/wrong + identify which misconception was hit. **Mastery is not an LLM-blurted float**; it uses a transparent BKT-lite:

```python
P_SLIP, P_GUESS, P_TRANSIT = 0.10, 0.20, 0.30
def bkt_update(p, correct, taught):
    # observation update: correct/wrong take two different Bayesian posteriors
    post = (p*(1-P_SLIP)/(p*(1-P_SLIP)+(1-p)*P_GUESS)) if correct \
           else (p*P_SLIP/(p*P_SLIP+(1-p)*(1-P_GUESS)))
    # inter-opportunity learning: if just taught, inject one learning increment.
    # Note: with taught=True, (1-post)*P_TRANSIT is added even on a wrong answer — this is the
    #   standard BKT term, not a bug. Under these params a wrong answer still falls back
    #   (e.g. 0.40 → ~0.35 floor), so mastery does not climb monotonically.
    return post + (1-post)*P_TRANSIT if taught else post

def confidence_update(n_observations):
    # confidence = a monotonic function of observation count, carrying S5 calibration.
    #   1 obs → 0.40 (low, "just one question"); 3 obs → 0.78; 5 obs → 0.92.
    return 1 - 0.6 ** n_observations
```

> **Why this matters**: under the current params, a single correct answer pushes mastery 0.40 → ≈0.825 (the number happens to reproduce the money shot, which is good), but a judge's "you call one question mastery?" is hard to answer. By decoupling `confidence` from observation count, the system can honestly say "mastery 0.82, but only 1 observation, confidence 0.40" — teach/rationale/UI use S5 tone accordingly. grade does `n_observations += 1` each time and writes back `confidence`.

grade output:
```json
{ "score": 0.5,
  "concept_scores": { "contrastive_learning": 0.4, "negative_sampling": 0.2 },
  "detected_misconception": { "concept": "dense_retrieval", "id": "dr_is_keyword_match" },
  "depth": "recall",
  "evidence": [{ "quiz_id": 12, "answer": "B", "correct": false,
                 "mapped_concept": "negative_sampling" }],
  "grader_confidence": 0.9 }
```

### 4.4 reteach — switch the explanation, don't repeat
From `direct → analogy → worked_example → contrast_case → simpler_decomposition`, pick one not in `tried_strategies`, anchor to the misconception's `correct_model`, re-explain, and go back to `check`. Each time `tried_strategies.append(s)`, `reteach_count[cid]+=1`.
> When `MAX_RETEACH` is exhausted and still failing → no more reteach; the router takes `concede` (§3).

---

## 5. Literature-induced scaffolding (the novelty core)

### 5.1 The dual-track principle

| Track | Use | Trust | Demo role |
|---|---|---|---|
| Human skeleton `source='curated'` | concepts/prereqs/misconceptions on the demo main path | high | safety net |
| Literature-induced `source='induced'` | off-skeleton concepts, or live demonstration | medium (verifiable via evidence) | hard evidence of novelty |

> Isomorphic to retrieval L0/L1. **Never** let "fully automatic construction of the whole graph" become a demo dependency; induction happens only at one or two points and always with evidence.

### 5.2 `induce_prereq` (prerequisite induction)
Let the LLM find "assumes / builds on / extends / requires prior understanding of" statements in the chunks, and extract "C depends on A" candidate edges. **Acceptance gate**: every edge has ≥1 cited chunk; without evidence, don't write it.

> **Confidence is computed, not LLM-blurted**: the LLM only (a) extracts the supporting chunks, and (b) judges the **language strength** of each piece of evidence (explicit assertion / general statement / weak hint). `confidence` is computed by a transparent rule (see §5.3 formula), and the rationale shows "how many papers × what strength → what score." When a judge asks "where does 0.78 come from," there's a clear answer.

Write to `concept_edges(source='induced', evidence=JSON[chunks], weight=confidence)`:
```json
{ "prereq": "negative_sampling", "target": "hard_negative_mining",
  "source": "induced", "confidence": 0.78,
  "confidence_basis": { "n_chunks": 2, "max_strength": "explicit", "multi_paper": false },
  "evidence": [{ "chunk_id": "c_2207_x", "paper_id": 41,
    "quote_span": "...builds on standard negative sampling by mining harder negatives..." }] }
```

### 5.3 `mine_misconception` (misconception induction) + transparent confidence formula
Scan correction/contrast-type language patterns ("contrary to (common belief)", "a common misconception", "naively", "it is often (wrongly) assumed", "unlike prior work", rebuttal/erratum), extract `wrong_model`/`correct_model` + citation. **Acceptance gate**: must point back to a specific chunk, else discard.

**Transparent confidence tiers for induced items (shared by prereq edges and misconceptions)**:
```python
def induced_confidence(n_chunks, max_strength, multi_paper):
    # max_strength ∈ {'weak','general','explicit'} (LLM labels the language strength of the evidence)
    base = {'weak': 0.50, 'general': 0.65, 'explicit': 0.78}[max_strength]
    if multi_paper:        base += 0.12     # corroborated across papers
    if n_chunks >= 3:      base += 0.05
    return round(min(base, 0.95), 2)        # induced never gets 1.0: leave calibration headroom
```
> This is the most on-point part: the misconception isn't something you made up — it's a pitfall the field's own papers call out; and "how trustworthy it is" is also decided by an explainable rule, not model conjecture.

### 5.4 Responsible AI / stands up to poking
- Every `induced` element is **explicitly labeled "machine-induced + openable evidence + confidence"** in the UI and rationale, distinguished from `curated`.
- Confidence is computed by the evidence rule, not model conjecture: display `confidence_basis` (how many papers, what language strength, whether multi-paper corroborated).
- When induced confidence is low, use S5 calibrated tone: "I infer A is a prerequisite of B from these two papers, medium confidence, you can overrule me."
- Turn "is your induction reliable?" into "the evidence is here + the rule is here, you judge for yourself" — a responsible-AI bonus.

---

## 6. Data scale (frozen, don't exceed)

### 6.0 M0 seed fixture (build this first)

M0 uses a deterministic toy fixture, not the competition data package:

| Item | M0 |
|---|---|
| Papers | 2 paper-like records |
| Concepts | 4 concepts (`dense_retrieval`, `negative_sampling`, `contrastive_learning`, `rag_pipeline`) |
| Prereq edges | 3 curated edges |
| Misconceptions | 0 required |
| Quiz items | 1 fixed item per concept |
| Retrieval | deterministic lookup by `concept_id` |
| Embeddings | none |
| External APIs | none |

This exists only to prove state-machine flow and SQLite writes. Do not block M0 on ingestion, embeddings, GROBID, Chroma, or live APIs.

### 6.1 Competition data package (M1+)

| Item | MVP |
|---|---|
| Papers | 30–50 |
| Concepts | 8–15 human-confirmed (skeleton) |
| Prereq edges | 15–30 human-confirmed; **leave 1–2 concepts out of the skeleton for the induction demo** |
| Misconception library | humans do only 2–3 demo-core concepts; **leave 1 to be mined by induction** |
| Parallel quiz forms | **2–3 equal-difficulty parallel items per demo-core concept (pre/post draw one each, see §4.2)** |
| Induction candidates | **pre-run offline once on D1–2**, spot-checked by humans, to reduce live risk (still marked induced) |
| PDF full text | abstract+intro+conclusion first; full text optional |
| embedding | bge-m3; SPECTER2 a bonus |
| Concept-system anchor | OpenAlex Topics |

> External APIs are only for building the data package offline (Semantic Scholar ~1 RPS); no live fetch during the demo. "Induction" at demo time runs LLM extraction over **already-ingested chunks**, offline.

---

## 7. Database schema (complete)

Storage: **SQLite** (metadata + graph edges + state, single-file zero-ops) + **Chroma** (vectors) + **networkx** (in-memory graph algorithms). 30–50 papers, **no Neo4j**.

> **Persist NavState via LangGraph's native `SqliteSaver` checkpointer**, don't hand-roll all graph-state persistence — leave inter-node state transitions and resume-from-checkpoint to the framework. The **domain tables** below are still kept, as auditable / demo-visualization / acceptance queryable records (learner_state / decisions / induction_log / tutor_turns / route_steps, etc.). That is: framework tables manage "runtime state," domain tables manage "traceable evidence."

```sql
-- external anchor
CREATE TABLE topics (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, openalex_topic_id TEXT,
    domain TEXT, field TEXT, subfield TEXT, description TEXT
);

-- internal teaching concepts (nodes of the teaching-dependency graph)
CREATE TABLE concepts (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE,
    topic_id INTEGER REFERENCES topics(id),
    description TEXT, level INTEGER, is_demo_core BOOLEAN DEFAULT 0,
    frontier_flag TEXT CHECK(frontier_flag IN ('consensus','contested','open'))
);

-- prerequisite DAG: explicit direction + provenance + evidence
CREATE TABLE concept_edges (
    prereq_concept INTEGER REFERENCES concepts(id),
    target_concept INTEGER REFERENCES concepts(id),
    edge_type TEXT CHECK(edge_type IN ('prerequisite','related','supports','contrasts')),
    weight REAL DEFAULT 1.0,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence TEXT,                       -- JSON: source chunks (human/LLM/paper)
    PRIMARY KEY (prereq_concept, target_concept, edge_type)
);

-- misconception library: provenance + evidence
CREATE TABLE misconceptions (
    id TEXT PRIMARY KEY,
    concept_id INTEGER REFERENCES concepts(id),
    wrong_model TEXT, correct_model TEXT,
    detect_hint TEXT, reteach_strategy TEXT,
    source TEXT CHECK(source IN ('curated','induced')) DEFAULT 'curated',
    confidence REAL DEFAULT 1.0,
    evidence_chunk_id TEXT
);

-- papers + chunks
CREATE TABLE papers (
    id INTEGER PRIMARY KEY, arxiv_id TEXT UNIQUE, title TEXT, abstract TEXT,
    authors TEXT, source_org TEXT, year INTEGER, full_text TEXT, pdf_path TEXT
);
CREATE TABLE paper_chunks (
    id TEXT PRIMARY KEY, paper_id INTEGER REFERENCES papers(id),
    section TEXT, chunk_index INTEGER, text TEXT, token_count INTEGER, embedding_id TEXT
);
CREATE TABLE paper_concepts (
    paper_id INTEGER REFERENCES papers(id),
    concept_id INTEGER REFERENCES concepts(id),
    relevance REAL, PRIMARY KEY (paper_id, concept_id)
);
CREATE TABLE citations (
    citing_paper INTEGER REFERENCES papers(id),
    cited_paper INTEGER REFERENCES papers(id),
    PRIMARY KEY (citing_paper, cited_paper)
);

-- demo lifesaver: concept → top papers precomputed
CREATE TABLE concept_paper_rank (
    concept_id INTEGER REFERENCES concepts(id),
    paper_id INTEGER REFERENCES papers(id),
    rank INTEGER, reason TEXT,
    PRIMARY KEY (concept_id, paper_id)
);

-- quiz bank + attempts (hard-bound to evidence)
CREATE TABLE quiz_items (
    id INTEGER PRIMARY KEY, concept_id INTEGER REFERENCES concepts(id),
    question TEXT, answer_key TEXT,
    qtype TEXT,                          -- 'mcq'|'predict'|'explain'|'transfer'
    difficulty INTEGER,                  -- parallel forms group by same concept+qtype+difficulty
    evidence_chunk_id TEXT,              -- required
    source_paper_id INTEGER REFERENCES papers(id),
    rubric TEXT, expected_concepts TEXT,
    targets_misconception TEXT           -- which misconception this item probes
);
CREATE TABLE quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    quiz_item_id INTEGER REFERENCES quiz_items(id),
    user_answer TEXT, score REAL, feedback TEXT,
    concept_score_delta TEXT, detected_misconception TEXT, created_at TIMESTAMP
);

-- sessions + state (the soul)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, user_id TEXT, topic TEXT, status TEXT, created_at TIMESTAMP
);
CREATE TABLE learner_state (
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    mastery REAL, confidence REAL,       -- confidence written by §4.3 confidence_update
    n_observations INTEGER DEFAULT 0,    -- input to confidence
    held_misconceptions TEXT,            -- JSON
    tried_strategies TEXT,               -- JSON
    depth TEXT, evidence TEXT, updated_at TIMESTAMP,
    PRIMARY KEY (session_id, concept_id)
);

-- teaching turns: prove "the explanation changed" + record pre/post performance (learning gain)
CREATE TABLE tutor_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    concept_id INTEGER REFERENCES concepts(id),
    turn_type TEXT,                      -- 'teach'|'reteach'
    strategy TEXT, pre_check_score REAL, post_check_score REAL,
    cited_chunks TEXT,
    token_cost INTEGER,                  -- lightweight cost accounting (§1.3/§12)
    created_at TIMESTAMP
);

-- route evolution
CREATE TABLE route_steps (
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER, step_id TEXT,
    concept_id INTEGER REFERENCES concepts(id),
    paper_id INTEGER REFERENCES papers(id),
    status TEXT, reason TEXT, confidence REAL, created_at TIMESTAMP,
    PRIMARY KEY (session_id, route_version, step_id)
);

-- decision log (most useful when judges push back)
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    route_version INTEGER, from_node TEXT,
    decision TEXT, rationale TEXT, state_snapshot TEXT,
    token_cost INTEGER,                  -- lightweight cost per decision step
    created_at TIMESTAMP
);

-- induction audit
CREATE TABLE induction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT, kind TEXT,          -- 'prereq'|'misconception'
    output TEXT, evidence_chunks TEXT, confidence REAL,
    confidence_basis TEXT,               -- JSON: n_chunks/max_strength/multi_paper
    created_at TIMESTAMP
);
```

> The demo main path only needs to wire up: `learner_state / concept_edges / misconceptions / tutor_turns / route_steps / decisions / quiz_items+attempts / paper_chunks / induction_log`. The schema can be more complete than what the code reaches, but don't let "build every table" become a rabbit hole.

---

## 8. Learning-science foundations + why it's novel

**Teaching side (design basis + deck argument)**

| Design | Theory |
|---|---|
| The whole project | Bloom 2-sigma (1984): 1-on-1 + mastery learning ≈ +2σ, carried to the research frontier |
| per-concept mastery + BKT | Bayesian Knowledge Tracing (1994) |
| no advance without mastery | Mastery Learning (Bloom/Keller) |
| check is learning | retrieval practice / testing effect (Roediger & Karpicke 2006) |
| force predict/recall/transfer | ICAP (Chi 2014): constructive ≫ passively reading papers |
| misconception → switch explanation | formative-assessment feedback loop (Black & Wiliam) |
| adjust depth by level | scaffolding/fading + expertise reversal (Kalyuga) |
| pre/post gain via parallel forms | the testing effect requires avoiding re-testing the same item; equal-difficulty parallel forms make pre/post comparable |

**Innovation side (one-line defense)**: the adaptive tutor loop is standard mature ITS (detect misconceptions, adaptive feedback, pacing); NotebookLM can already generate grounded quizzes/guides from papers — **neither half is the novelty**. The novelty is in the product, and in **scaffolding induced from the living literature**: a fixed-curriculum tutor can't (order/misconceptions are hard-coded by humans), a static literature assistant can't (doesn't model you, doesn't reteach, doesn't sequence).

---

## 9. Retrieval (tiered — don't build full RRF up front)

| Tier | Approach | When |
|---|---|---|
| L0 lifesaver | `concept_paper_rank` precomputed | ready in Phase 0, demo fallback |
| L1 minimal RAG | SQLite FTS5(BM25) + Chroma | main line; FTS5 has BM25 built in, no ES needed |
| L2 full | BM25 + vector + citation/topic boost + RRF | bonus, only after the core is done |

---

## 10. S1–S5 intelligence signals → testable acceptance

| Signal | Acceptance |
|---|---|
| S1 "because" | rationale cites check_result + misconception/prereq edge + this action |
| S2 branching | same question: correct→advance; misconception→reteach; missing prereq→replan. true three paths |
| S2+ induction | off-skeleton concept→induce: induced edge/misconception written with evidence and used |
| S3 push-back | jump-step→point out which prereq is missing, "viewable but not recommended as the main path" |
| S4 coverage warning | flag that papers cluster in a year/org, without making a strong claim |
| S5 calibration | consensus/contested/open tiers; induced low-confidence admits "tentative, can be overruled"; on concede, admit "this hasn't landed" + when confidence is low with few observations, say so plainly |

---

## 11. Hard acceptance criteria (grouped by milestone, see §12)

| Test | Content | Stage |
|---|---|---|
| T1 state truly written | after one check, DB shows mastery change + quiz_attempts + decisions | M1 |
| T2 true three paths | correct→advance; misconception→reteach; missing prereq→replan, not hard-coded | M1→M2 |
| T2b concede termination | reteach exhausted with no missing prereq → `concede` (flag low confidence + S5 honesty + advance), **no infinite loop** | M2 |
| T3 reteach truly switches | tried_strategies shows two different strategies | M2 |
| T4 rationale traceable | check→misconception/prereq edge→cited_chunk→action | M1→M2 |
| T5 in-session learning gain | within tutor_turns, post_check_score > pre_check_score; pre/post drawn from same-concept equal-difficulty parallel items | M2 |
| T5b confidence calibration | confidence rises monotonically with n_observations; on a single observation, UI/rationale state "low confidence" | M2 |
| T6 induction with evidence | every induced edge/misconception has ≥1 cited chunk + source='induced' + induction_log + confidence_basis | M3 |
| T7 induction demoable | demo shows ≥1 corpus-induced element (or induced offline + evidence chain shown live) | M3 |
| T8 honest provenance | UI/rationale distinguishes curated vs induced, low confidence uses S5 tone; show that confidence is rule-computed | M3 |
| T9 jump-step interception | skipping a prereq → "viewable but not recommended as main path, because [prereq] not met" | M2 (bonus) |
| T10 no hallucinated citations | every teach/reteach assertion points back to a real chunk_id | M2 |
| T11 runs offline | no dependence on live arXiv/OpenAlex/S2 | M0 |

---

## 12. Milestones & phased plan (10-day risk ladder)

**Principle**: 3 people, hard deadline 6/25 lock (no content can be added after submission). So phase by "vertical slice + risk ladder" — **every phase is a self-contained, submittable, recordable complete system**, and each later phase is a superset of the previous. At any point in time there is a version you can submit.

**Target line**: floor at **M2** (qualifies for the finals), main push for **M3** (gold contender). M1 is the floor (basically only a participation award), don't settle there.

### Three-person parallel tracks (from D1; milestones are cross-track convergence points)

| Track | Owner | Responsibilities | Cross-milestone deliverables |
|---|---|---|---|
| **A · Data/content** | 1 person | first create the 4-concept M0 fixture; then ingest 30–50 papers, 8–15-concept skeleton, prereq edges, misconception library, parallel quiz forms, pre-run induction candidates offline, concept↔paper binding | M0 fixture ready → M1 competition data ready → M2 add demo-core items/misconceptions → M3 leave off-skeleton concepts ready |
| **B · Graph engine** | 1 person | package skeleton + deterministic M0 flow first; then LangGraph nodes + four-path + concede routing + BKT/confidence + `SqliteSaver` persistence + `induce_scaffold` | M0 skeleton → M1 routing/reroute → M2 inner loop → M3 induction |
| **C · UI + evaluation** | 1 person | M0 verification script first; then thin UI (incremental per milestone) + T1–T11 acceptance scripts + recording scripts + token/cost accounting | from M0, every gate has a command; from M1, a recordable view every time a gate passes |

> This way M0 is not blocked by the real corpus. Track A can grow the competition data package in parallel, while track B proves the loop and track C proves every gate with commands.

### M0 · Fake-data walking skeleton (foundation, not demoed standalone) | target D1–D2
- **Deliverable**: a tiny deterministic Python package runs end-to-end on rails: seed fixture → init session → plan route → select concept → fixed quiz → deterministic grade → mastery/confidence update → advance. SQLite shows real writes. LangGraph is optional for M0; preserving node boundaries is required.
- **Content track in parallel (track A)**: create the 4-concept M0 fixture first. Then start the 30–50 paper competition data package without blocking the M0 gate.
- **Verification**: `python -m litnav.evaluation.verify_m0` creates a fresh local SQLite DB and prints G0 PASS lines for session, route, learner_state, quiz_attempt, decision, and offline run.
- **Gate G0**: the verification command passes, and the run performs no network calls.

### M1 · Navigator (floor, first submittable/recordable system) | target D4–D5
- **Add**: planner orders the route from the DAG; real quiz bound to evidence; grade uses BKT-lite to write mastery + confidence; router two paths (advance / diagnose→replan insert prereq).
- **Thin UI increment**: a minimal panel (left chat / right route+evidence), so "the route changed because of your quiz" is recordable on the spot, not saved up to D9.
- **Cost**: decisions/tutor_turns start logging token_cost.
- **Money shot ①**: adaptive reroute (wrong answer → insert prereq → route_version+1).
- **Gate G1**: T1 + true conditional edges (correct→advance / wrong→replan, not hard-coded) + T4 rationale traceable.
- **Positioning**: complete but **undifferentiated** (≈ a smart reading list / Elicit+). **At this point there is already a qualifying submission.**

### M2 · Tutor (teacher capability, the competitive threshold) | target D5–D7
- **Add the inner loop**: presenter→`teach` (grounded explanation, with citations); `check` (Socratic, pre/post draw parallel items); grade gains **misconception detection**; `reteach` (switch to an unused strategy); router upgraded to **four paths (+reteach +concede)**.
- **Thin UI increment**: add the three-color concept graph + reteach trail (tried_strategies visible) + dual mastery/confidence display.
- **Money shot ②**: switch explanation and reteach on the same concept (misconception → switch to analogy, re-teach → pass).
- **Gate G2**: T2 (true three-path branching) + T2b (concede, no infinite loop) + T3 (reteach truly switches) + T5 (learning gain pre<post) + T5b (confidence calibration) + T10 (no hallucinated citations).
- **Positioning**: a real tutor, but **still mature ITS**. A shot at the finals, novelty not yet prominent.

### M3 · Literature induction (novelty, gold target line) | target D7–D8
- **Add**: `induce_scaffold` (induce prereqs + mine misconceptions, with source='induced'+evidence+transparent confidence); teach gains frontier annotation (consensus/contested/open); off-curriculum triggers induction.
- **Thin UI increment**: curated vs induced visual distinction + openable evidence + `confidence_basis` display.
- **Money shot ③**: induce scaffolding from papers (user asks an off-skeleton concept → agent induces prereqs/misconceptions, with openable evidence, taught as contested).
- **Gate G3**: T6 (induction with evidence) + T7 (≥1 induction demoable / induced offline + live evidence chain) + T8 (honest provenance).
- **Positioning**: **occupy the square nobody occupies. The gold narrative.**

### M4 · Icing on the cake (only if M3 finishes early) | D slack
Priority: Langfuse trace → S3 refuse_jump → coverage warning (S4) → multi-concept induction → better/interactive UI → cross-session memory → RRF → SPECTER2 → GROBID full text.

### Submission & presentation (throughout, not a phase) | D9–D10
- **D9**: the UI has grown incrementally with the milestones, so D9 is only "final integration + polish" (no longer building the frontend from scratch under pressure) + record the demo of the highest phase reached.
- **D10**: deck (problem → benchmark Khanmigo/NotebookLM → architecture (dual loop + induction) → the current phase's money shots → learning science → value → cost data) + buffer.
- **6/25**: submit ≥2h early.

### Time–progress coupling (go / no-go decision table)

| Checkpoint | Ideal progress | If behind → action |
|---|---|---|
| **late D2** | M0 passes (fake-data skeleton runs) | drop all ingestion/UI work and secure the deterministic SQLite loop first |
| **late D3** | M1 data package has started | trim the data package to 30 papers / 8 concepts if needed |
| **late D5** | M1 passes (navigator recordable) | **freeze at M1 to guarantee a submission**; compress M2 scope |
| **late D7** | M2 passes (tutor recordable) | freeze M2; M3 only does the minimal "induced offline + live evidence shown" version |
| **late D8** | M3 passes (induction demoable) | if M3 is unstable → fall back to recording M2, present M3 in the deck as "implemented capability + evidence screenshots" |
| **D9** | the highest phase reached is recorded | — |

### Three iron rules (write them where you'll see them, re-read often)
1. **Gate not passed, never advance to the next phase.** A half-baked M3 that crashes hurts far more than a polished M2 — the final judging pokes live, and the submission is locked with no way to patch.
2. **Tag / save a runnable snapshot the moment a gate passes.** At any time you can fall back to "the last submittable version."
3. **Goal: floor at M2, push for M3.** Only reaching M1 is basically a participation award.

---

## 13. Frozen demo script (three scenarios, mapping to the three phases)

**Topic:** "I want to understand retrieval-augmented generation (RAG) for scientific QA."
Initial skeleton route: `Dense retrieval → Contrastive learning → RAG pipeline → Evaluation/hallucination`

**Scenario ② (M2) · same-concept reteach**
teach dense retrieval → check (draw parallel item A) exposes the misconception "thinks it's just keyword/BM25 matching" (`dr_is_keyword_match`) → prereqs OK → `reteach` switches to the analogy of nearest neighbors in embedding space → check again (draw parallel item B) passes. `mastery 0.40→0.81`, `confidence` rises to ~0.64 on the 2nd observation, `tried_strategies=[direct, analogy]`.

**Scenario ① (M1) · cross-concept reroute**
teach contrastive learning → check fails on the negative-sampling question → maps to the prereq `negative_sampling` (mastery<threshold) → `replan` inserts a negative-sampling primer before contrastive learning, `route_version+1`.

**Scenario ③ (M3) · literature induction ★ hard evidence of novelty**
User introduces an off-skeleton concept: "I keep seeing hard negative mining — where does it go, and what are the pitfalls?"
→ `induce_scaffold`:
  - prereq edge: `negative_sampling → hard_negative_mining`, evidence "…builds on standard negative sampling…" (marked induced; confidence rule-computed: explicit phrasing, single paper → 0.78);
  - misconception: mined from the papers "thinks more negatives is better" → correct: "hard negatives matter more than quantity" (marked induced, with cited chunk);
  - frontier annotation: taught as `contested` — "how to mine hard negatives is still unsettled; here are two schools."
→ slot into the route and teach; the induced elements carry **openable evidence + confidence_basis**, visually distinguished from the human skeleton.

> **The progression of the three money shots is the whole story's value**: switch explanation (like a teacher) → back up and backfill (like a teacher with a curriculum view) → **induce scaffolding from papers (like a research partner who's actually reading the frontier and laying out the field's structure for you)**. The third fully separates LitNavigator from Khanmigo/NotebookLM.
> **Which scenarios you record depends on which milestone you froze at**: record ① at M1; add ② at M2; add ③ at M3.

**Counterfactual (S2, must be shown live)**: answer scenario ②'s question correctly → advance directly without reteach. The two paths side by side — perceived intelligence rides entirely on this contrast.
**Counterfactual (concede, optional to show)**: deliberately construct a concept that "still fails after two explanations, with prereqs all OK" → demonstrate `concede` honestly exiting, showing honesty and no infinite loop.

---

## 14. MVP cut / must-keep list

**Cut/downgrade**: fully automatic construction of the whole concept DAG (induction only at 1–2 points) · multi-hop prereq-chain induction · PDF full text as the main path · 200 papers · full GROBID · strong S4 bias detection (→ coverage warning) · cross-session memory · full RRF · SPECTER2 · the full interactive concept graph (static three-color is enough)

**Must keep (deleting these regresses the product)**:
- Delete and it regresses to **Elicit**: LearnerState · conditional edges · grade writes mastery · diagnose · replan · rationale
- Delete and it regresses to **a navigator that writes quizzes**: teach grounded explanation · reteach switches explanation · misconception detection · four-path router (incl. concede) · tutor_turns
- Delete and it regresses to **a Khanmigo/NotebookLM reskin (no novelty)**: `induce_scaffold` induction · source provenance + evidence · transparent confidence · frontier annotation · scenario ③

---

## 15. Positioning statement (for the deck and README)

> LitNavigator is a stateful tutor that is **built from and teaches through the living research literature**. It induces a concept's prerequisites and mines a field's misconceptions directly from the papers (each shown with its citing evidence and a rule-computed confidence), models your concept-level mastery and specific misconceptions, re-teaches differently when you don't get it, re-routes when you're missing a prerequisite, honestly concedes when a concept won't land, and teaches the frontier's open disagreements with calibrated confidence. Unlike fixed-curriculum tutors that teach an authored course, and unlike static source-grounded assistants that generate one-shot quizzes without a learner model, LitNavigator's curriculum, misconceptions, and teaching content all come from the live corpus.

---

## 16. One line

LitNavigator = the adaptive tutor loop × curriculum scaffolding induced from the living literature. 10 days along a risk ladder: M0 skeleton → M1 navigator (floor, submittable) → M2 tutor (teacher capability, floor into the finals) → M3 literature induction (novelty, gold contender) → M4 icing. Three people on three parallel tracks, a submittable/recordable snapshot saved at every phase, never advancing past a gate that hasn't passed. Learning happens directly in the conversation, scaffolding comes from the living literature, every step is traceable, it concedes when it hasn't taught something through, and its confidence is computed from evidence — this is the version that doesn't collapse when judges poke it, and can still contend for gold.
