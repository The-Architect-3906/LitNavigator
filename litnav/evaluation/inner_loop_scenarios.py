"""Inner-loop (LangGraph) live validation — drive the REAL compiled tutor graph turn-by-turn on
FRESHLY-DIGESTED open-world graphs, with scripted learner personas that exercise every branch
(teach→assess→grade→reteach→advance→concede→handle_lost→select_next→done), in the learner's
language (A8), with granular citations (A9).

Driver: interrupt_after=["assess_next"] + get_state/update_state/resume — the real interactive path.
Personas answer the ACTUAL posed quiz; "correct" uses the quiz's real answer_key so grade_kp does
genuine grading. Skips at provider=none for the live matrix; _smoke() validates the driver offline ($0).

Run:  (load .env)  python -m litnav.evaluation.inner_loop_scenarios
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import traceback
from pathlib import Path

from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.graph.builder import build_graph, make_initial_state
from litnav.ui.trace import build_trace
from litnav.discover.contract import DiscoverInput
from litnav.discover import find_sources
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact
from litnav.llm import lang as lang_mod, client as llm_client

_OUT = Path("docs/e2e-logs")
_BUDGET = 120000
_MAX_TURNS = 40
_WRONG = "I am not sure — possibly something unrelated to the question."
_EMPTY = {"concepts": [], "keypoints": [], "prereq_edges": [], "similarity_edges": [],
          "quiz_seeds": [], "judge_labels": {}}


class _Learner:
    """Scripted persona. Returns (answer, user_intent) for a posed quiz."""
    def __init__(self, persona: str):
        self.persona = persona
        self._wronged: set = set()     # keypoints answered wrong once (struggle)
        self._lost_done = False

    def answer(self, quiz: dict) -> tuple[str, str | None]:
        key = quiz.get("answer_key", "") or ""
        kp = quiz.get("keypoint_id") or quiz.get("id")
        if self.persona == "mastery":
            return key, None
        if self.persona == "give_up":
            return _WRONG, None
        if self.persona == "lost_then_recover":
            if not self._lost_done:
                self._lost_done = True
                return "", "lost"
            return key, None
        if self.persona == "struggle":
            if kp not in self._wronged:
                self._wronged.add(kp)
                return _WRONG, None
            return key, None
        return key, None


def run_session(conn, ckpt, sid, topic, target_ids, persona, *, goal_text, log) -> dict:
    app = build_graph(conn, ckpt, interrupt_after=["assess_next"])
    state0 = make_initial_state(sid, topic, target_ids, pending_answers=[],
                                goal_text=goal_text, mastery_threshold=0.75)
    config = {"configurable": {"thread_id": sid}, "recursion_limit": 80}
    learner = _Learner(persona)
    app.invoke(state0, config)
    turns = 0
    while turns < _MAX_TURNS:
        snap = app.get_state(config)
        if not snap.next:                      # reached END
            break
        quiz = snap.values.get("current_quiz_item")
        if not quiz:                            # paused somewhere without a quiz — just continue
            app.invoke(None, config); turns += 1; continue
        ans, intent = learner.answer(quiz)
        app.update_state(config, {"pending_answers": [ans], "user_answer": ans, "user_intent": intent})
        app.invoke(None, config)
        turns += 1

    tr = build_trace(conn, sid)
    final = app.get_state(config)
    hist = final.values.get("history") or []
    scores = [r[0] for r in conn.execute("SELECT score FROM quiz_attempts WHERE session_id=?", (sid,)).fetchall()]
    tts = [r[0] for r in conn.execute("SELECT turn_type FROM tutor_turns WHERE session_id=?", (sid,)).fetchall()]
    statuses = [r[0] for r in conn.execute("SELECT status FROM route_steps WHERE session_id=?", (sid,)).fetchall()]
    fired = {
        "teach": "teach" in tts,
        "reteach": "reteach" in tts,
        "graded": len(scores),
        "correct": sum(1 for s in scores if s == 1.0),
        "mastered": "done" in statuses,
        "conceded": "conceded" in statuses,
        "handle_lost": any(h.get("event") == "handle_lost" for h in hist),
    }
    teach_text = " ".join(h.get("text", "") for h in hist if h.get("event") in ("teach_kp", "handle_lost"))[:600]
    return {"trace": tr, "turns": turns, "fired": fired, "teach_text": teach_text,
            "route_status": statuses, "reached_done": not final.next}


# ───────────────────────── OFFLINE SMOKE ($0) ─────────────────────────
def _smoke() -> int:
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    fix = json.loads(Path("data/seed/digest_sources_fixture.json").read_text(encoding="utf-8"))
    di = DigestInput(fix["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in fix["sources"]], fix.get("target_slugs", []))
    for persona in ("mastery", "struggle", "give_up", "lost_then_recover"):
        conn = sqlite3.connect(":memory:"); init_db(conn)
        ck = sqlite3.connect(":memory:", check_same_thread=False)
        pipeline.digest(di, conn=conn, candidate=fix["candidate"], session_id="dg")
        repo.create_session(conn, f"sm-{persona}", topic=fix["domain_key"])
        tids = [r[0] for r in conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:3]
        r = run_session(conn, ck, f"sm-{persona}", fix["domain_key"], tids, persona,
                        goal_text="learn this", log=print)
        print(f"[smoke {persona:18}] reached_done={r['reached_done']} turns={r['turns']} fired={r['fired']}")
    print("inner-loop smoke: done"); return 0


# ───────────────────────── LIVE MATRIX ─────────────────────────
_MATRIX = [
    (1, "diffusion-models", "English", "I want to deeply master how diffusion models generate images.", "mastery"),
    (2, "crispr", "Chinese", "给我一个关于 CRISPR 基因编辑原理的快速概览。", "struggle"),
    (3, "raft-consensus", "English", "How do I build a working Raft consensus implementation?", "give_up"),
    (4, "quantum-error-correction", "English", "Explain the basics of quantum error correction.", "lost_then_recover"),
    (5, "black-scholes", "Spanish", "Quiero entender a fondo el cálculo de precios con Black-Scholes.", "mastery"),
    (6, "mrna-vaccines", "English", "A working understanding of how mRNA vaccines are designed.", "struggle"),
    (7, "transformer-attention", "Chinese", "深入掌握 Transformer 自注意力机制的数学原理。", "mastery"),
    (8, "behavioral-economics", "English", "An overview of behavioral economics and nudges.", "give_up"),
    (9, "rlhf", "English", "How to apply RLHF to fine-tune an LLM.", "struggle"),
    (10, "graph-neural-nets", "French", "Donne-moi une introduction aux réseaux de neurones sur graphes.", "lost_then_recover"),
]


def _digest_topic(conn, sid, goal_text):
    res = find_sources.find(DiscoverInput(goal_text, k=6), conn=conn, session_id=sid, budget=_BUDGET)
    withft = [s for s in res.sources if s.chunks and sum(len(x) for x in s.chunks) > 200]
    if not withft:
        return None, res
    top = withft[0]
    di = DigestInput(goal_text, [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                     target_slugs=[])
    pipeline.digest(di, conn=conn, candidate=_EMPTY, session_id=sid, budget=_BUDGET)
    return top, res


def _run_live_one(sc, log) -> dict:
    cid, slug, language, goal, persona = sc
    sid = f"il{cid}"
    summ = {"id": cid, "slug": slug, "language": language, "persona": persona, "errors": []}
    conn = sqlite3.connect(":memory:"); init_db(conn); repo.create_session(conn, sid, topic=goal)
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    log(f"# Inner-loop scenario {cid} — {slug}  (persona={persona}, {language})")
    log(f"- goal: {goal}\n")
    t0 = time.time()
    top, res = _digest_topic(conn, sid, goal)
    if top is None:
        summ["errors"].append("no full-text source"); return summ
    tids = [r[0] for r in conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:4]
    log(f"- digested top source: {top.title[:70]!r} → {len(tids)} target concepts, "
        f"{conn.execute('SELECT COUNT(*) FROM keypoints').fetchone()[0]} keypoints, "
        f"{conn.execute('SELECT COUNT(*) FROM quiz_items').fetchone()[0]} quiz items")
    try:
        r = run_session(conn, ck, sid, goal, tids, persona, goal_text=goal, log=log)
    except Exception as e:
        summ["errors"].append(f"graph: {e}"); log("```\n" + traceback.format_exc() + "\n```"); return summ
    tr = r["trace"]
    # final artifact in the learner's language
    od = tempfile.mkdtemp()
    art = make_artifact(ArtifactInput(tids, {}, format="notes", language=language),
                        conn=conn, session_id=sid, out_dir=od)
    abody = Path(art.artifact_path).read_text(encoding="utf-8")
    art_lang = lang_mod.detect_language(abody)
    teach_lang = lang_mod.detect_language(r.get("teach_text") or "x")
    sp = cost_repo.session_spend(conn, sid)
    summ.update({
        "reached_done": r["reached_done"], "turns": r["turns"], "fired": r["fired"],
        "route": [f"{s['name']}[{s['status']}]" for s in tr["route"]],
        "concepts_taught": sum(1 for c in tr["concepts"] if c["n_observations"]),
        "teach_lang": teach_lang, "teach_lang_ok": (teach_lang == language),
        "artifact_lang": art_lang, "artifact_lang_ok": (art_lang == language),
        "artifact_citations": art.citations, "secs": round(time.time() - t0, 1),
        "cost_usd": sp["usd"], "was_live": llm_client.was_live(),
    })
    log(f"\n## RESULT  reached_done={r['reached_done']} turns={r['turns']} fired={r['fired']}")
    log(f"- route: {summ['route']}")
    log(f"- teaching language={teach_lang} (want {language}, ok={summ['teach_lang_ok']})")
    log(f"- artifact language={art_lang} (want {language}, ok={summ['artifact_lang_ok']}) citations={art.citations}")
    log(f"- cost usd={sp['usd']} was_live={llm_client.was_live()}")
    log("\n--- teaching turns (first 3, language check) ---")
    for tt in tr["tutor_turns"][:3]:
        log(f"  [{tt['turn_type']}/{tt['strategy']}] {tt['name']}")
    return summ


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("inner-loop-live SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    import sys
    for _st in (sys.stdout, sys.stderr):
        try: _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    _OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for sc in _MATRIX:
        lines: list[str] = []
        def log(m, _l=lines): _l.append(m); print(m, flush=True)
        print(f"\n===== INNER-LOOP {sc[0]}/{len(_MATRIX)} : {sc[1]} ({sc[4]}) =====", flush=True)
        try:
            summ = _run_live_one(sc, log)
        except Exception as e:
            summ = {"id": sc[0], "slug": sc[1], "errors": [f"FATAL: {e}"]}
            log("```\n" + traceback.format_exc() + "\n```")
        (_OUT / f"innerloop-{sc[0]:02d}-{sc[1]}.md").write_text("\n".join(lines), encoding="utf-8")
        results.append(summ)
    (_OUT / "innerloop-summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    tot = sum(r.get("cost_usd", 0.0) for r in results)
    print(f"\n=== DONE: {len(results)} inner-loop scenarios; total usd={round(tot,4)} ===")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
