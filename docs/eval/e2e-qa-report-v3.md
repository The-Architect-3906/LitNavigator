I have all the per-scenario data I need. Let me synthesize it into the QA report.

# LitNavigator — Live Tutor QA Synthesis

9 testers drove 10 live open-world tutor scenarios (cold start → routed teaching) against the running server. Coverage: English mastery (#1 diffusion, #3 Raft, #9 RLHF), English survey (#4 QEC, #8 behavioral econ), Chinese (#2 CRISPR survey, #7 transformers mastery), Spanish (#5 Black-Scholes mastery), French (#10 GNNs intro). All 10 ran end-to-end with no crashes.

---

## 1. Overall Usability

**Average rating: 2.8 / 5** (ratings: #1=3, #2=3, #3=3, #4=2, #5=3, #7=3, #8=3, #9=3, #10=2).

**Holistic read:** The product is a *strong demo of adaptive remediation wrapped around a shallow, often-stuck delivery loop.* When a learner answers and the tutor reacts — specific feedback, strategy-cycling reteaches, graceful "lost" handling — it feels genuinely intelligent and is the best part of every scenario. But the spine that should carry a learner *through a curriculum* is fragile: two scenarios (#4 QEC, #10 GNN) never advanced past concept 1 at all, several truncate or orphan concepts, every concept cites the same single evidence chunk, and the glass-box trace frequently misrepresents what happened. The ceiling is high; the floor is unreliable.

**The 3 things that hurt most:**
1. **The route stalls or never progresses.** #4 and #10 are effectively unusable surveys — 8 turns, never left concept 1, mastery oscillating *down on correct answers* (#4: 0.667→0.467 then conceded). Even where it works, advancing one concept takes 3–4 correct answers from a 0.4 floor, which every mastery scenario (#1, #3, #8, #9) called "grindy."
2. **Verbatim question repetition + invisible Bloom progression.** Every single scenario reported the same quiz text re-posed across reteach / lost / and rising Bloom levels (4+ identical turns in #2, #3, #5, #9, #10). The advertised recall→comprehension→application escalation changes a hidden tag but not the words the learner reads, so the tutor "feels broken / not listening."
3. **No closure + content depth mismatch.** Routes complete silently with `mastery:None` and no summary (#1), and the taught content routinely misses the stated goal: "build a working Raft" got 4 conceptual facts and zero RPCs/leader-election (#3); "master the math" of attention got analogies and zero equations (#7); "intro to GNNs" got a niche MECCH heterogeneous-graph paper (#10).

---

## 2. Consolidated BUG List (deduped, ranked by severity then frequency)

### BLOCKER
- **B1. Route never advances past concept 1** — multiple correct answers do not trigger `advance_kp`; concepts 2–N never taught. **Hit: #4 (all 8 turns, conceded), #10 (all 8 turns, route_version stuck at 1).** Session unusable as a survey.
- **B2. Mastery decreases / oscillates on correct answers** — #4: correct turn-7 (0.667) → turn-8 dropped to 0.467; sequence 0.475→0.275→0.075→0.445→0.667→0.467. **Hit: #4 (blocker), #10 (0.691→0.491 on a correct answer, see B6).**

### MAJOR
- **B3. Verbatim question repetition across reteach/lost/Bloom levels** — same prompt 4+ turns in a row; Bloom tag rises but text is identical. **Hit: #1, #2, #3, #5, #7, #8, #9, #10 (8 of 10).** Most pervasive bug in the suite.
- **B4. Evidence is not concept-specific** — `retrieve` logs "0 chunks" for concepts 2+, teach falls back to the same chunk c0; `trace.evidence` stays length 1 all session. **Hit: #1, #2, #3, #4, #5, #7, #9, #10 (8 of 10).**
- **B5. Glass-box timeline mis-joins answer → decision (off-by-one) and drops rows** — answers paired with the *next* turn's decision; correct answers labeled `reteach`, wrong answers labeled `advance`. #9: a 0.0 wrong answer shown with `decision=advance / Concept mastered`. **Hit: #1, #8, #9** (and timeline freezes/incomplete in #2, #3, #5 — see B11).
- **B6. Correct-but-differently-framed answer graded WRONG and penalized** — #10 turn 7: textbook metapath definition marked `correct=false`, mastery 0.691→0.491, because it didn't match the expected framing. **Hit: #1 (application scenario), #10 (major).** Flip side of the leniency in B8.
- **B7. Off-corpus / topic-switch mid-session penalized instead of handled** — #9: "teach me diffusion models instead" classified `action=answer`, graded wrong, dropped mastery 0.475→0.275. The out-of-corpus honesty boundary does not fire mid-session. **Hit: #9.**
- **B8. Grading too lenient on vague/hand-wave answers** — keyword-echo answers graded fully correct (score 1.0) with full mastery gain. **Hit: #1, #2, #5, #7, #8, #10 (6 of 10).**
- **B9. Route silently truncates / orphans concepts** — DAG has N concepts, route visits fewer; dropped ones are often exactly the goal-relevant ones. #3: route 4 of 7, the implementation concepts dropped. #1: concepts 5–6 never routed (stuck at 0.4 forever). **Hit: #1, #3 (major), #2, #5, #7, #10.**
- **B10. Quiz questions emitted in English regardless of learner language** — teaching localizes but questions (and lost/don't-know re-explanations) revert to English. **Hit: #5 (Spanish), #7 (Chinese), #10 (French) — all 3 non-English-question scenarios; #10 also has English route-overview bubble.**
- **B11. trace.timeline / trace.decisions stale or incomplete** — timeline freezes at 2–3 rows while tutor_turns grows to 6–16; decisions empty on cold start / early turns or stop logging mid-session. **Hit: #1, #2, #3, #5, #7, #8, #9 (7 of 10).**
- **B12. No route-completion closure** — final `done:true` carries `mastery:None`, no summary/celebration teach; post-done input is a silent no-op. **Hit: #1.**
- **B13. Cross-session DISCOVER non-determinism** — identical goal yields different source paper + curriculum across sessions (#8 Nudge-theory-5 vs Behavioral-econ-3; #10 MECCH vs GCN/GraphSAGE benchmark). Reproducibility/fairness concern. **Hit: #8, #10.**
- **B14. Concept-count mismatch across UI surfaces** — map label / route / concepts list disagree (4 vs 5 vs 6 vs 7/8). **Hit: #1 (6 vs 4), #2 (4 vs 5), #4 (4 vs 8), #5, #7 (4/5/6), #8 (4 vs 5), #10 (4 vs 7) — 7 of 10.**
- **B15. Grindy pacing / Bloom never escalates despite mastery** — #8: same keypoint quizzed ~7 turns, 4 correct answers to advance, Bloom never rose above comprehension even at mastery 0.8/conf 1.0. **Hit: #8 (major), echoed as minor in #1, #3, #9.**

### MINOR
- **B16. Misconception detection never fires on keypoint path** — `held_misconceptions`/`detected_misconception` stay empty even for textbook misconceptions matching authored `detect_hint`. **Hit: #1, #8, #9** (and #2 detected one but never *cleared* it — see B17).
- **B17. Held misconception never cleared after mastery** — #2: `dg_site_specific_targeting_0` persisted after concept reached mastery 0.815 / conf 1.0 "mastered." Contradictory signal. **Hit: #2.**
- **B18. Cost not metered on lost/reteach LLM paths** — `total_token_cost` frozen across handle_lost / reteach turns that generate real LLM text; per-turn `token_cost=0`. **Hit: #2, #3, #7, #8 (and per-step token_cost=0 broadly across #1, #5, #9, #10).**
- **B19. Confidence does not drop on a clearly-wrong answer** — mastery falls but confidence stays pinned (e.g. 0.6). Inconsistent with BKT-lite framing. **Hit: #2, #3, #7.**
- **B20. Disproportionate mastery penalty for vague/first-answer** — a vague non-answer drops a fresh concept 0.4→0.1 (-0.3 with n_observations still 0), harsher than a confidently-wrong answer. **Hit: #1, #3.**
- **B21. Spanish teach blocks get an untranslated English tail** — "Now let's check your understanding." appended verbatim. **Hit: #5.**
- **B22. Misleading concede rationale string** — #4: "confidence=0.900<0.5" inside an OR-clause though 0.900 is not <0.5. **Hit: #4.**
- **B23. Lost path has no escape hatch / unbounded re-explain** — handle_lost doesn't consume the reteach budget or offer to skip/lower Bloom; a learner saying "I don't know" repeatedly can loop forever on one keypoint. **Hit: #4, #9, #10.**
- **B24. Lost path re-poses the same (often application-level) question** — doesn't drop back to recall for a just-confused learner. **Hit: #1, #4, #5, #10.**

### NIT
- **B25. Headline cost shown as raw token integer, not USD** despite USD existing internally. **Hit: #4, #9, #10 (cumulative, no per-turn breakdown).**
- **B26. `retrieve` logs "0 chunks" but teach still cites c0** — misleading detail line. **Hit: #5, (root of B4 everywhere).**
- **B27. Post-`done` input silent no-op** (subset of B12). **Hit: #1.**
- **B28. French formality register flips vous↔tu within one session.** **Hit: #10.**
- **B29. `pre_check_score` always null** — glass box can't show per-turn learning gain. **Hit: #4.**
- **B30. drive_session.py harness has no per-session isolation** (test-harness, not server; server isolated correctly by SID). **Hit: #2.**

---

## 3. Glass-Box Problems

The transparency *plumbing* is praised everywhere, but the *data is frequently wrong or incomplete*:

- **Timeline is the worst offender** (B5, B11): off-by-one answer→decision joins that produce actively-misleading rows (correct→reteach, wrong→advance, wrong answer credited with "Concept mastered" in #9), plus dropped rows (3 rows for 8–19 turns in #1, #2, #5, #8). Anyone reading the glass box to understand "why" is misled.
- **No prereq DAG** (#1): all concept_edges are `similarity` (conf 0.55–0.75) and *cyclic* (3→1, 4→1, 1→2, 6→2, 2→6); zero `prereq` edges. The route is just concept IDs in order, despite UI/narration advertising a "RefD prereq DAG." Consequence: `recommend[]` shows "Ready now — unlocks 0 concepts," score 0.0 for every candidate every turn (#1).
- **Evidence panel is static** (B4): one chunk c0 for the whole session in 8/10 scenarios; `paper_title` dropped to null in trace despite being present in the event stream (#2).
- **Misconception channel is dead** (B16/B17): detection never fires on the keypoint path even with matching detect_hints; when it does fire it never clears.
- **Cost metering under-reports** (B18): frozen on lost/reteach turns, per-step `token_cost=0`, headline in tokens not USD.
- **Decisions trace is the bright spot:** once populated, rationales are human-readable and trustworthy, with exact dual-threshold math ("ADVANCE concept 2: mastery=0.804≥0.75, confidence=0.900≥0.5, ≥2 correct observations"). Routing is verifiably rule-computed, consistent with project design — but it's empty on cold start / early turns and sometimes stops mid-session (#5).
- **Standout (only in #1):** the cost_ledger itself — 77 entries, per-stage/per-tier/per-model detail, total $0.0766 — is excellent and trustworthy. The contradiction is that this rich ledger coexists with the frozen per-turn meters elsewhere.

---

## 4. Edge-Case Handling Summary

| Input | Verdict | Notes |
|---|---|---|
| **"I'm lost" (literal)** | **Excellent** | Every scenario: classified `action=lost` → `handle_lost`, **no mastery penalty**, fresh strategy. #1 called it the best explanations of the session. |
| **"I don't know" (literal)** | **Excellent** | Also `lost`; reliably escalates to a *different* strategy than the prior lost turn (analogy→worked_example). Good non-repetition. |
| **Clearly wrong** | **Good** | Accurately graded false with specific, non-generic, on-topic corrections that name the confused component. Mastery drops sensibly. The consistent strength. |
| **Vague / partial** | **Too lenient (B8)** | 6/10 scenarios graded keyword-echo hand-waves as fully correct (score 1.0) with full mastery gain. No partial-credit state — grading is binary. |
| **Off-question-but-correct** | **Too harsh (B6)** | The flip side: correct content in unexpected framing graded wrong (#1, #10). |
| **Off-corpus topic switch** | **Not handled (B7)** | #9 penalized it as a wrong answer; boundary honesty doesn't fire mid-session. |

**Shared edge-case weaknesses:** (a) the lost path re-poses the *same, often application-level* question instead of dropping to recall (B24), and (b) it has no escape hatch / can loop unbounded (B23) — which is exactly the trap that made #4 unusable.

---

## 5. What Worked Well

1. **Cold-start UX (every scenario):** the 30–90s wait is fully narrated with streamed discover → digest → map stages, real source titles, skill/method/paper labels, and a rendered SVG concept map. "Never staring at a blank spinner" — cited as the single biggest UX win by #1, and a highlight in #2, #3, #4, #5, #7, #8, #9, #10.
2. **Adaptive remediation ladder:** strategies genuinely cycle direct → analogy → worked_example → contrast with distinct, well-pitched, on-topic explanations — not canned re-prints. Praised in all 10.
3. **Specific, grounded feedback prose:** names the exact misconception or missing idea, stays encouraging; quality holds up in Chinese (#2, #7) and French (#10).
4. **Lost/don't-know detection:** robust intent separation (answer vs lost), non-punitive, supportive tone.
5. **Decision transparency (when correct):** rule-computed routing with explicit dual-threshold rationale and state snapshots — matches stated design that mastery/confidence/routing are never LLM-emitted.
6. **Robustness:** all 10 ran fully end-to-end, no crashes/stream errors across adversarial inputs; server session isolation by SID verified correct (#2).
7. **Cost instrumentation (#1):** the 77-entry per-tier/per-model cost_ledger is exemplary.

---

## 6. Cross-Scenario Patterns

**Language handling (Chinese / Spanish / French):** Consistent and consistently *half-broken* (B10). Teaching body and feedback localize well — fluent Chinese (#2, #7), fluent Spanish after turn 1 (#5), fluent French (#10) — but **quiz questions and lost/don't-know re-explanations always revert to English** in all three non-English scenarios. Learners are graded on questions in a language different from the course. Secondary defects: Spanish gets an English tail appended (#5, B21); French route-overview bubble is English and formality flips vous↔tu (#10, B28). #2 (Chinese) fared best because the *questions* happened to stay survey-generic. Net: bilingual teaching is a real feature; bilingual *assessment* is not implemented.

**Survey vs mastery vs functional depth:** A clear pattern by goal type.
- *Survey* (#2, #4, #8): worst hit by the stall bug — surveys want breadth, but #4 never left concept 1, #2 taught the same intro paragraph at rising Bloom labels (never reached CRISPR specifics — no gRNA/Cas9/PAM), #8 spent ~7 turns on one keypoint. Surveys expose B1/B9/B15 hardest.
- *Mastery* (#1, #5, #7): the grindy 0.4-floor / 3-4-correct-to-advance pacing is the main friction; #7 ("master the *math*") got zero equations — a depth/goal mismatch.
- *Functional / "how do I build/apply"* (#3 Raft, #9 RLHF): worst goal-content mismatch — the tutor teaches conceptual facts, never the actionable mechanics asked for (no RPCs/leader-election; no fine-tuning steps), and #3 truncates away the exact implementation concepts (B9). **Across all three depth types the root cause is shared:** concepts are single phrases mined from one short paragraph, and all teaching cites one chunk c0 (B4) — so there is no deep content to deliver regardless of goal type.

**Cold-start UX:** Uniformly the best-received moment (see §5) and uniformly trustworthy in its *narration* — but it sets expectations the rest of the session breaks: the map label undercounts concepts (B14), narrates a pedagogical "progression" the graph doesn't encode (no prereq edges, #1), and the discovered source is non-deterministic for the same goal (B13). The cold start over-promises a curriculum the delivery loop under-delivers.

**Meta-pattern:** Reactive intelligence (per-turn grading, feedback, remediation, lost-handling) is excellent and consistent. Stateful progression (route advancement, per-concept evidence, mastery dynamics, misconception tracking, multilingual assessment, trace accuracy) is where nearly every bug lives. Prioritize B1/B2 (stall + mastery-on-correct) and B3/B4 (repetition + evidence) — fixing those four lifts the floor across all 10 scenarios.