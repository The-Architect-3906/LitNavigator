I'll synthesize the 10 scenario reports into a QA report. Let me note the scenarios first: only 9 distinct reports are present (the set is labeled #2, #3, #5, #6, #7, #10 plus unlabeled ML/diffusion, QEC, behavioral econ, RLHF). Let me assign clear IDs and synthesize.

# LitNavigator — Live Tutor QA Report

10 testers each drove one live scenario end-to-end (cold start → edge cases → completion attempt). Scenario IDs used below:

| ID | Topic | Lang | Intent | Turns | Rating |
|----|-------|------|--------|-------|--------|
| S1 | Diffusion models | EN | mastery | 8 | 2 |
| S2 | CRISPR | 中文 | survey | 15 | 3 |
| S3 | Raft consensus | EN | functional | 8 | 2 |
| S4 | Quantum error correction | EN | survey | 8 | 2 |
| S5 | Black-Scholes | ES | mastery | 8 | 3 |
| S6 | mRNA vaccines | EN | functional | 15 | 3 |
| S7 | Transformer self-attention | 中文 | mastery | 8 | 2 |
| S8 | Behavioral economics | EN | survey | 23 | 3 |
| S9 | RLHF | EN | functional | 8 | 3 |
| S10 | Graph neural networks | FR | survey | 15 | 2 |

---

## 1. Overall Usability

**Average rating: 2.4 / 5** (five 2s, four 3s). Holistic read: **a structurally sound, genuinely transparent tutor engine wrapped in an experience that withholds the two things a learner most needs — feedback and citations — and, on the live path, often cannot be completed at all.** The skeleton (ORIENT→TEACH→ASSESS, adaptive reteach/concede, glass-box rationale) is real and impressive. But every single scenario hit the same wall of missing-feedback + empty-evidence + broken-cost-trace, and several hit a grader that makes the stated learning goal unreachable. No tester rated above 3.

**The 3 things that hurt most (universal across all 10):**

1. **No correctness feedback after grading (10/10).** Correct, vague, and wrong answers all produce only "(re)teach + next question." The learner can never tell if they were right or what they missed. Cited by every scenario (S1, S2, S3, S4, S5, S6, S7, S8, S9, S10).
2. **Cited evidence never surfaces (10/10).** `trace.evidence == []`, every `cited:[]`, retrieve logs "0 chunks" — despite a real source paper being named at discover and artifacts that literally print "Citations: c0/c1/c2" (S2, S8). For a product pitched as "reads papers and cites them," the core value prop is dark in every live session.
3. **The grader breaks the goal (varies, but devastating where it lands).** On the live path, mastery/confidence often cannot cross the advance gate (S1: confidence capped at 0.3 < 0.5 → every concept concedes; S10: a correct learner literally cannot finish the route). Where it isn't capped, it's miscalibrated/non-monotonic — rewarding vague hand-waves with 1.0 and rejecting expert-precise answers with 0.0 (S3, S4, S7, S10).

---

## 2. Consolidated BUG List (deduped, ranked by severity then frequency)

### BLOCKER

**B1 — Mastery goal structurally unreachable on the live path.** Confidence caps at 0.3 while advance gate needs ≥0.5; flawless answers leave mastery ~0.3–0.48, so every concept ends in concede. *(S1: blocker)*. Related live-only flat-bars manifestation also in S1 glass-box notes.

**B2 — Grader inverted / non-monotonic.** Textbook-correct expert answers scored 0.0 while vague hedges scored 1.0; rewards surface wording over correctness. *(S3 turn 1–2: blocker; S4 turns 6–8: blocker)*. Same failure mode in non-blocker form: S7 (expert multi-head answer graded wrong; one-line hand-wave got 1.0), S10 (non-monotonic, target concept never reached), S2/S5/S6 (vague-but-correct flat 0.0).

### MAJOR

**B3 — No learner-facing feedback bubble after grading.** *(S1, S2, S4, S6, S8, S9, S10 — flagged major; observed in all 10.)*

**B4 — Cited evidence never populated** (`evidence:[]`, `cited:[]`, retrieve "0 chunks"); artifacts claim citations that don't exist. *(All 10; S2 & S8 also expose the false "Citations: cN" in the artifact.)*

**B5 — `trace.total_token_cost` stuck at 0 on the live path** despite the live `state.cost` event metering real rising spend. Root cause (per S3): `litnav/ui/trace.py:224-225` sums `tutor_turns[].token_cost + decisions[].token_cost`, both persisted as 0; real cost only lives in the ephemeral `state.cost` event. *(S1, S2, S3, S4, S6, S7, S9, S10 — major; S5 offline so $0 expected.)*

**B6 — Misconception detection never fires.** Classic baited misconceptions (diffusion=one-pass deblurrer S1; CRISPR=antibiotic S2; no-cloning/majority-vote S4; caching removes proofs S3; genome-rewrite S6; positional-encoding-reorders S7; reward-model=tokenizer S9; graphs-are-drawings S10; B-S=riskless-profit S5) all produced `detected_misconception=null`, `held_misconceptions=[]`. The reteach never names or corrects the specific false claim. *(S1, S2, S4 — major/blocker; S3, S5, S6, S7, S9, S10 — major/minor. 10/10 dark.)*

**B7 — "I don't know" graded as a wrong answer.** Dispatched `action=answer`, scored 0.0, tanks mastery (often to 0.0 → forces concede), while the near-identical "I'm lost" is correctly routed to `handle_lost` with no penalty. Punishes honesty. *(All 10 — major in S2, S4, S7, S8, S10; minor/major elsewhere.)*

**B8 — Goal→corpus relevance gate too loose.** "Build a working Raft implementation" retrieved only a Coq proof-maintenance paper and silently taught formal-verification theory — zero content on RPCs/leader election/log replication. No DISCOVER fallback or honest "I only have verification sources." *(S3 — major.)* Related off-brief drift: S4 (niche GRAND paper for "QEC basics"), S7 (math goal taught embeddings).

### MINOR

**B9 — No relevance gate on learner ANSWERS.** An off-topic carbonara-recipe answer was graded as PASSING and advanced the route — grader rewards length/keywords over correctness. *(S10 — major-tier; unique to S10's off-topic probe.)*

**B10 — Headline/"done" mastery jumps confusingly.** On advance/concede the `done` event shows the NEW concept's 0.4 prior, so the top-line number leaps up right after a concede (S1, S4) or drops from 0.858→0.4 right after mastering a concept (S9) — reads as the opposite of what happened. *(S1, S4, S9.)*

**B11 — Stale top-level `state.decision`.** Surfaces the previous turn's decision (e.g. "concede" shown while successfully teaching the next concept). *(S3, S4, S5, S6, S9, S10.)*

**B12 — Trace lags one full turn behind live state.** Turn N's grade/decision only appears in turn N+1's trace; timeline self-contradicts (perfect score paired with reteach decision). *(S1, S5.)*

**B13 — "Hold" / re-pose decisions not logged, and identical question re-posed verbatim** when mastery sits just under threshold or after "I'm lost" — reads as a stuck loop; not in `decisions[]`. *(S1, S4, S5, S7, S8, S9, S10.)*

**B14 — Difficulty does not de-escalate after "I'm lost" / repeated failure.** Same hard (often two-part comprehension) question re-posed instead of dropping to recall. *(S1, S2, S3, S4, S7, S9.)*

**B15 — `handle_lost` writes no `decisions`/`timeline` entry** — the lost event is invisible in the glass box. *(S1, S2, S4, S5, S6, S7.)*

**B16 — Empty question bubble on completion** (`text=''`, `bloom_level=null`) emitted alongside the artifact, with no congratulatory/summary message. *(S2, S8.)* Flat/abrupt completion also S6.

### NIT

**B17 — Reteach opens with an unanswerable rhetorical meta-question** ("What part felt unclear?") then immediately re-teaches and re-quizzes; mis-frames a confident-wrong learner as stuck-but-trying. *(S1, S2, S3, S4, S6, S7, S9, S10.)*
**B18 — `session.status` stays "active" after `done=True`.** *(S6.)*
**B19 — Minor factual slips in generated teaching:** "Cas-9 cuts ~3 bases upstream of the target" (should be upstream of the PAM) *(S2)*; first teach event mixes English overview + foreign-language lesson paragraph *(S5)*.

---

## 3. Glass-Box Problems

- **Cost pillar broken in the trace (B5)** — 8/9 live scenarios show $0 while real spend accrues. Root cause located: `litnav/ui/trace.py:224-225`.
- **Evidence pillar dead (B4)** — `trace.evidence` empty in all 10; per-turn `cited_chunks:[]` everywhere; artifacts cite sources that were never retrievable.
- **Concept-map vs route mismatch (frequent):** digest induces 5–8 concepts but the route schedules only 4. Orphaned concepts sit at default 0.4 mastery forever, never taught or explained. *(S1: 6 vs 4; S3: 8 vs 4; S4: 8 vs 4; S7: 5 vs 4; S8: 8 vs 4; S9: 5 vs 4; S2: 6 vs 4.)*
- **Decision log is incomplete:** only reteach/advance/concede are logged; `handle_lost`, `select_next`, `review_probe`, and "hold"/re-pose produce no `decisions` entry (B13, B15), so the most confusing learner moments are unexplainable from the glass box.
- **Stale / lagging surfaced state:** `state.decision` lags (B11), trace lags one turn (B12), timeline under-reports (S2: 6 entries vs 13 turns; S10: timeline 0→3), and `done.mastery` mismaps to the wrong concept_id (S10) or shows the new prior (B10).
- **`n_observations` anomalies:** stays at 1 after 3+ graded turns (S9); doesn't increment on wrong/IDK (S8); a *correct* spaced-review probe dropped mastery below threshold (S8: 0.843→0.743).
- **`review_probe`/`grade_probe` render with empty skill/method/paper "-"** so the glass box can't explain why a past question reappeared (S2).
- **Route `reason` is static** ("Initial route from concept DAG.") — never explains the ordering (S9).
- **What's genuinely good:** where decisions ARE logged, rationales are gold-standard — exact thresholds, strategy/attempt counters, and honest concede text ("reteach exhausted and thresholds not met (mastery=0.000<0.75 or confidence=0.300<0.5)... moving on rather than looping"). Praised in S1, S3, S4, S5, S6, S8, S9, S10. The `recommend` panel (eligible vs blocked with reasons + unlock counts) is a standout (S3, S9).

---

## 4. Edge-Case Handling Summary

| Case | Behavior | Verdict |
|------|----------|---------|
| **"I'm lost"** | Correctly `action=lost` → `handle_lost`, supportive fresh-angle re-explanation, **no mastery penalty**, no reteach-attempt consumed. | **Best-handled edge case in every scenario** (S1, S2, S3, S4, S5, S6, S7, S9, S10). Two caveats: re-poses the same hard question (B14) and writes no glass-box decision (B15); in non-English sessions the re-explanation reverts to English (S2, S5, S7, S10). |
| **"I don't know"** | Treated as `action=answer`, graded 0.0, mastery → 0.0, frequently forces concede. | **Mishandled / inconsistent in all 10.** Should mirror the no-penalty "I'm lost" path (B7). Worst outcome in S2/S4/S5/S10 where it abandoned the concept. |
| **Clearly wrong (misconception bait)** | Scored 0.0, mastery dropped (correct direction), reteach strategy switched. | Direction right, but **misconception never detected, named, or corrected** in any scenario (B6). |
| **Vague/partial** | Scored a flat 0.0 (no partial credit), triggered reteach. | **Too harsh** — half-right compound answers get the same 0.0 as fully wrong (S1, S2, S4, S5, S6, S8, S9). Inverted in S3/S7 where vagueness was over-rewarded with 1.0. |
| **Off-topic answer** | Accepted and graded PASSING, advanced the route. | **No answer-level relevance gate** (S10, B9). |
| **Recovery / anti-loop** | Reteach-exhaustion → concede with clear rationale; no infinite loops; sessions stayed resumable and never crashed across 8–23 turns. | **Solid.** The concede loop-guard is a genuine strength (S1, S2, S3, S4, S5, S6, S8, S9, S10). |

---

## 5. What Worked Well

- **Cold-start build streaming (10/10).** discover → discover_done (names real source paper) → digest → map ("Concept map ready — N concepts") + inline SVG graph. Makes the 30–90s wait feel intentional; cited as the strongest part of the experience in S1, S2, S4, S5, S6, S10.
- **ORIENT roadmap tour.** Previews the full concept sequence before teaching — orients beginners well (S1, S4, S6, S9).
- **Adaptive reteach with real strategy switching** (direct → analogy → contrast/simpler restate), not mere repetition; analogies are apt (S1 ball-down-hill, S5 garden/storm-cover, S6 recipe, S7 dinner-party, S8 buffet/organ-donation). Pedagogically sound (all scenarios).
- **Bloom laddering** (recall → comprehension → application) on success, holds on failure, resets per concept (S3, S5, S6, S8, S9).
- **Concede / route-replan transparency** — honest, threshold-explicit rationale; never loops (see §3).
- **Spaced-retrieval review probes** between concepts — real learning-science touch (S2, S8).
- **Mastery dynamics ARE coherent on the offline + well-behaved-grader scenarios** (S5, S6): bars move per-turn, reward correct / penalize wrong proportionally, ignore "I'm lost," dual mastery+confidence+n_obs gating fires exactly as documented. S5 and S6 explicitly *refute* the flat-bars bug for their path.
- **Cornell-style study-notes artifact** at completion (cues + summary + recall prompts), downloadable (S2, S8).
- **Robustness:** no crash/hang/stream error across any session, including the two edge-case strings (S3, S9 explicit).

---

## 6. Cross-Scenario Patterns

**Language handling (中文 S2/S7, ES S5, FR S10):** Consistent, pervasive **i18n failure** in all four non-English scenarios. Teach bodies render correctly in the learner's language, but the **ORIENT tour, every quiz question, fixed phrases ("Now let's check your understanding", "No problem — let me back up"), the "I'm lost" re-explanation, and the final notes artifact stay in English.** The learner code-switches mid-screen on every turn. Most jarring: the metacognitive "I'm lost" rescue — the one place a struggling learner most needs their own language — reverts to English in S2, S5, S7, S10. S5/S7 also show a bilingual first teach event (English overview + foreign lesson paragraph). This is a single systemic bug, not four separate ones: question generation and canned strings are not locale-aware.

**Survey vs mastery vs functional depth:**
- **Survey (S2, S4, S8, S10):** Over-escalates for the brief. Compound two-part comprehension questions and application-level jargon ("finite blocklength regime," S4) appear in turn 1 of a "quick overview." A survey becomes a 13–23-turn commitment (S2, S8). S8 was the one survey that respected a comprehension ceiling — and rated highest of its group.
- **Mastery (S1, S5, S7):** The intent the engine should serve best, yet **B1 makes "deeply master" literally unreachable on the live path** (S1 conceded every concept). Where the grader behaved (S5), mastery worked and rated 3. The mastery scenarios are also where missing misconception detection hurts most — diagnostic value is the whole point.
- **Functional (S3, S6, S9):** Exposes the **goal→corpus gap hardest** (S3: "build Raft" → Coq proof theory; S7-adjacent). When the corpus matched (S6 mRNA, S9 RLHF), functional sessions were among the better-rated (both 3) because the application-level Bloom questions are genuinely well-scoped scenarios. Recommendation: functional intent needs a corpus-relevance gate + honest "I only have X-type sources" fallback.

**Cold-start UX:** Uniformly the **strongest moment in the product** (10/10 positive). The discover→digest→map stream with source provenance and SVG graph reliably converts a long wait into a confidence-building reveal. The flip side — the **concept-map vs 4-step-route mismatch** (orphaned concepts shown but never taught) — is the recurring cold-start *glass-box* wart (7+ scenarios). And cold start is precisely where the **false-citation promise originates**: a real paper is named at discover, raising an expectation that the empty `evidence` array (B4) then breaks for the rest of the session.

**Net:** fix the three universals (feedback bubble B3, evidence pipeline + cost trace B4/B5, the grader B1/B2) and locale-aware question/string generation, and the median rating plausibly moves from 2.4 into the 3.5–4 range — the underlying state machine and glass-box rationale are already competition-grade.