# UI / UX follow-ups (queued)

## 1. BUG — glass-box "story band" shows the offline fixture on a live session
On a live open-world session, the top DISCOVER/DIGEST/Representative panels render the **static agents
fixture** (e.g. DISCOVER "LLM-based autonomous agents", "7-concept map" with ReAct/Tool-use/Agent-memory,
"25 papers", representative = ReAct/Toolformer/Reflexion/MetaGPT) while the chat teaches the real topic
(e.g. CRISPR). Confirmed cause: `litnav/ui/server.py::tutor_page` always renders
`**_story_context(_fixture_data())` regardless of whether the session is a live open-world run.
**Fix:** for live sessions, build the story band from the session's REAL sources/concepts (the data is in
the per-session DB / the build events), or hide the fixture story band for live sessions. Severity: major
(undermines the glass-box trust — panels contradict the lesson).

## 2. Direction-B Phase 2 (bigger bets) — deferred, not started
Decision-trail timeline · confidence-as-uncertainty-band (replace dual mastery/confidence bars) · ⌘K
command palette · interactive concept map (click node → scope) · persistent artifact tab with version
history. Specced in docs/eval/ui-redesign-directions.md (Direction B, Phase 2).

## 3. Home "Test scenarios" redesign
Current: thin left-accent pills showing the slug + id + lang. Wanted:
- ~3-row **marquee** layout, nicely-sized buttons (not thin pills).
- Show the **real scenario name/title**, not the slug.
- A **big emoji** per scenario (domain-appropriate).
- Surface metadata: number of sources, language, depth, etc.
Source of truth: `litnav/evaluation/e2e_scenarios.py::SCENARIOS`.

## 4. BUG — glass-box timeline under-logs turns (trace shows ~half the questions)
A live session asked/answered 8 questions (8 quiz_attempts) but the trace panel showed only 4 timeline
rows. Cause: the timeline/`decisions` table logs only routing DECISIONS (advance/concede), not every
quiz / reteach / recap / "lost" turn — so intermediate turns never appear. Confirmed on session
026d1e3b (8 quiz_attempts, 7 keypoints, 4 decisions). Fix: write a timeline row per TURN (teach/quiz/
grade/reteach/recap/lost), not just per routing decision, so the trace + provenance rail show the full
history. Severity: major (the glass-box is the headline feature; an incomplete trace undermines trust).
