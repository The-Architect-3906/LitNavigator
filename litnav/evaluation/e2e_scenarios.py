"""OW-0..5 full-pipeline LIVE evaluation over 10 diverse real learning scenarios.

Each scenario varies ALL FIVE dimensions — learning goal, intended depth, the learner's prior
knowledge, language habit, and discipline/domain — and is run end-to-end through the real
orchestrators: DISCOVER (OW-3) -> DIGEST (OW-2/1) -> goal elicitation + ASSESS (OW-4) ->
make-artifact (OW-5), every call metered through the cost spine (OW-0).

This is a documented ASSESSMENT, not a pass/fail gate: it writes a detailed per-step log per
scenario under docs/e2e-logs/ and a machine-readable summary.json, so real performance and every
bug/gap are captured. Skips at provider=none (it must run LIVE to mean anything).

Run:  (load .env, then)  python -m litnav.evaluation.e2e_scenarios
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

from litnav.storage.schema import init_db
from litnav.storage import repo, cost_repo
from litnav.discover.contract import DiscoverInput
from litnav.discover import find_sources
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.digest import pipeline
from litnav.nodes import goal_elicit, grade_kp
from litnav.assess import quizgen, strategy
from litnav.artifact.contract import ArtifactInput
from litnav.artifact.make_artifact import make_artifact
from litnav.llm import client as llm_client

_OUT = Path("docs/e2e-logs")
_BUDGET = 90000
_EMPTY = {"concepts": [], "keypoints": [], "prereq_edges": [], "similarity_edges": [],
          "quiz_seeds": [], "judge_labels": {}}

# 10 scenarios — goal / intended depth / prior knowledge / language / domain ALL distinct.
SCENARIOS = [
    {"id": 1, "slug": "diffusion-models", "language": "English", "domain": "ML / generative models",
     "intended_depth": "mastery", "prior": "ML practitioner (knows CNNs/transformers)",
     "goal_text": "I want to deeply master how diffusion models generate images, end to end."},
    {"id": 2, "slug": "crispr", "language": "Chinese", "domain": "Biology / gene editing",
     "intended_depth": "survey", "prior": "undergraduate biology background",
     "goal_text": "给我一个关于 CRISPR 基因编辑原理的快速概览。"},
    {"id": 3, "slug": "raft-consensus", "language": "English", "domain": "Distributed systems",
     "intended_depth": "functional", "prior": "backend engineer, no distributed-systems theory",
     "goal_text": "How do I actually build a working Raft consensus implementation?"},
    {"id": 4, "slug": "quantum-error-correction", "language": "English", "domain": "Physics / quantum computing",
     "intended_depth": "survey", "prior": "physics undergraduate",
     "goal_text": "Explain the basics of quantum error correction for a beginner."},
    {"id": 5, "slug": "black-scholes", "language": "Spanish", "domain": "Finance / quantitative",
     "intended_depth": "mastery", "prior": "finance novice, decent calculus",
     "goal_text": "Quiero entender a fondo el cálculo de precios de opciones con Black-Scholes."},
    {"id": 6, "slug": "mrna-vaccines", "language": "English", "domain": "Biochemistry",
     "intended_depth": "functional", "prior": "interested layperson",
     "goal_text": "I need a working understanding of how mRNA vaccines are designed."},
    {"id": 7, "slug": "transformer-attention", "language": "Chinese", "domain": "NLP / deep learning",
     "intended_depth": "mastery", "prior": "CS graduate student",
     "goal_text": "深入掌握 Transformer 自注意力机制背后的数学原理。"},
    {"id": 8, "slug": "behavioral-economics", "language": "English", "domain": "Economics",
     "intended_depth": "survey", "prior": "layperson, curious",
     "goal_text": "Give me an overview of behavioral economics and nudges."},
    {"id": 9, "slug": "rlhf", "language": "English", "domain": "ML / alignment",
     "intended_depth": "functional", "prior": "ML engineer who has fine-tuned models",
     "goal_text": "How do I apply reinforcement learning from human feedback to fine-tune an LLM?"},
    {"id": 10, "slug": "graph-neural-nets", "language": "French", "domain": "Graph machine learning",
     "intended_depth": "survey", "prior": "data scientist new to graphs",
     "goal_text": "Donne-moi une introduction aux réseaux de neurones sur graphes."},
]

# Map intended depth -> expertise label for the strategy policy.
_EXPERTISE = {"survey": "novice", "functional": "intermediate", "mastery": "expert"}


def _run_one(sc: dict, log) -> dict:
    sid = f"s{sc['id']}"
    summ: dict = {"id": sc["id"], "slug": sc["slug"], "language": sc["language"],
                  "domain": sc["domain"], "intended_depth": sc["intended_depth"],
                  "errors": []}
    c = sqlite3.connect(":memory:"); init_db(c); repo.create_session(c, sid, topic=sc["goal_text"])
    log(f"# Scenario {sc['id']} — {sc['slug']}")
    log(f"- **goal** ({sc['language']}): {sc['goal_text']}")
    log(f"- **intended depth**: {sc['intended_depth']}  ·  **prior**: {sc['prior']}  ·  **domain**: {sc['domain']}\n")

    # ── OW-3 DISCOVER ─────────────────────────────────────────────────────────
    t0 = time.time()
    res = find_sources.find(DiscoverInput(sc["goal_text"], k=6), conn=c, session_id=sid, budget=_BUDGET)
    withft = [s for s in res.sources if s.chunks and sum(len(x) for x in s.chunks) > 200]
    summ["discover"] = {"intent": res.intent_used, "n_sources": len(res.sources),
                        "n_fulltext": len(withft), "secs": round(time.time() - t0, 1)}
    log(f"## OW-3 DISCOVER  ({summ['discover']['secs']}s)")
    log(f"- intent classified: `{res.intent_used}`  ·  {len(res.sources)} sources  ·  {len(withft)} with full text")
    for s in res.sources[:6]:
        log(f"  - [{s.source_type} auth={s.authority_score:.2f}] {s.title[:90]}")
    log("")
    if not withft:
        summ["errors"].append("DISCOVER: no source with full text")
        return summ

    # ── OW-2/1 DIGEST ─────────────────────────────────────────────────────────
    # Digest the TOP-RANKED full-text source (res.sources is ranked relevance×authority, and
    # `withft` preserves that order) — this measures DISCOVER honestly (what the real system
    # would teach from), not whichever source happened to be longest.
    t0 = time.time()
    top = withft[0]
    summ["discover"]["top_source"] = {"title": top.title[:90], "type": top.source_type,
                                      "authority": round(top.authority_score, 2)}
    log(f"- digesting top-ranked source: _{top.title[:80]}_ (auth={top.authority_score:.2f})\n")
    di = DigestInput(sc["goal_text"],
                     [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)],
                     target_slugs=[])
    dres = pipeline.digest(di, conn=c, candidate=_EMPTY, session_id=sid, budget=_BUDGET)
    db_concepts = c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    db_kp = c.execute("SELECT COUNT(*) FROM keypoints").fetchone()[0]
    db_quiz = c.execute("SELECT COUNT(*) FROM quiz_items").fetchone()[0]
    n_prereq = sum(1 for e in dres.edges if e["edge_type"] == "prerequisite")
    valid = {r[0] for r in c.execute("SELECT id FROM paper_chunks").fetchall()}
    kp_ok = all(e in valid for (e,) in c.execute("SELECT evidence_chunk_id FROM keypoints") if e)
    summ["digest"] = {"source": top.title[:80], "chars": sum(len(x) for x in top.chunks),
                      "db_concepts": db_concepts, "db_keypoints": db_kp, "db_quiz": db_quiz,
                      "edges": len(dres.edges), "prereq": n_prereq, "edge_accuracy": dres.edge_accuracy,
                      "kp_evidence_resolves": kp_ok, "secs": round(time.time() - t0, 1)}
    log(f"## OW-2 DIGEST  ({summ['digest']['secs']}s)")
    log(f"- source: _{top.title[:80]}_ ({summ['digest']['chars']} chars full text)")
    log(f"- **persisted**: {db_concepts} concepts · {db_kp} keypoints · {db_quiz} quiz items")
    log(f"- edges: {len(dres.edges)} ({n_prereq} prereq survived) · edge_accuracy={dres.edge_accuracy} · kp_evidence_resolves={kp_ok}")
    for cc in dres.concepts[:8]:
        log(f"  - `{cc['slug']}` — {cc.get('name','')[:50]}")
    log("")
    cids = [r[0] for r in c.execute("SELECT id FROM concepts ORDER BY id").fetchall()]
    if not cids:
        summ["errors"].append("DIGEST: 0 concepts persisted")
        return summ

    # ── OW-4 GOAL ELICITATION + ASSESS ────────────────────────────────────────
    t0 = time.time()
    gt = goal_elicit.classify_goal(sc["goal_text"], conn=c, session_id=sid)
    depth_match = (gt == sc["intended_depth"])
    expertise = _EXPERTISE[sc["intended_depth"]]
    strat = strategy.choose_strategy(gt, expertise, 0.3)
    summ["teach"] = {"goal_type": gt, "intended": sc["intended_depth"], "depth_match": depth_match,
                     "expertise": expertise, "strategy": strat}
    log(f"## OW-4 TEACH / ASSESS  ({round(time.time()-t0,1)}s)")
    log(f"- goal_elicit → `{gt}`  (intended `{sc['intended_depth']}` → match={depth_match})")
    log(f"- strategy policy (expertise={expertise}) → `{strat}`")
    qrow = c.execute("SELECT id, concept_id, question, answer_key FROM quiz_items LIMIT 1").fetchone()
    if qrow:
        qid, qcid, question, ans = qrow
        ds = quizgen.make_distractors(question, ans, conn=c, session_id=sid, n=3, fallback=[])
        ok, why = quizgen.flaw_gate({"question": question, "answer_key": ans, "distractors": ds})
        state = {"session_id": sid,
                 "concept_progress": {"concept_id": qcid, "phase": "assessing", "keypoints": ["kp1"],
                     "taught_idx": 1, "current_keypoint_id": "kp1", "current_bloom": "recall",
                     "keypoint_state": {"kp1": {"keypoint_id": "kp1", "mastery": 0.4, "correct_obs": 0,
                         "last_result": None, "reteach_count": 0, "strategies_used": []}},
                     "misconceptions": {}},
                 "current_quiz_item": {"id": qid, "question": question, "answer_key": ans,
                     "rubric": f"must convey: {ans}", "expected_keypoints": ans,
                     "evidence_chunk_id": None, "targets_misconception": None},
                 "pending_answers": [ans], "user_answer": ans, "current_cited_chunks": [], "history": []}
        gout = grade_kp.grade_kp_node(state, c)
        summ["teach"].update({"quiz_q": question[:80], "n_distractors": len(ds), "flaw_gate_ok": ok,
                              "grade_score": gout["quiz_result"]["score"]})
        log(f"- seed quiz: _{question[:80]}_")
        log(f"- distractors (live): {len(ds)} · flaw_gate={ok} ({'clean' if ok else why})")
        log(f"- grade (answer=key): score={gout['quiz_result']['score']} mastery→{gout['quiz_result']['mastery']:.2f}")
    else:
        summ["teach"]["quiz_q"] = None
        summ["errors"].append("ASSESS: no quiz item to grade")
        log("- no quiz item persisted → grade skipped")
    log("")

    # ── OW-5 MAKE-ARTIFACT ────────────────────────────────────────────────────
    t0 = time.time()
    od = tempfile.mkdtemp()
    chosen = []
    for fmt in ("notes", "mindmap"):
        try:
            r = make_artifact(ArtifactInput(cids[:4], {"goal_type": gt}, format=fmt),
                              conn=c, session_id=sid, out_dir=od)
            body = Path(r.artifact_path).read_text(encoding="utf-8")
            resolve = all(c.execute("SELECT 1 FROM paper_chunks WHERE id=?", (x,)).fetchone() for x in r.citations)
            chosen.append({"format": fmt, "len": len(body), "citations": r.citations,
                           "citations_resolve": resolve, "nonempty": len(body) > 80})
            log(f"## OW-5 ARTIFACT `{fmt}`  len={len(body)} citations={r.citations} resolve={resolve}")
            if fmt == "notes":
                snippet = "\n".join(body.splitlines()[:18])
                log("```markdown\n" + snippet + "\n```")
        except Exception as e:
            chosen.append({"format": fmt, "error": str(e)})
            summ["errors"].append(f"ARTIFACT {fmt}: {e}")
    summ["artifact"] = {"selector_format": select_fmt(gt), "rendered": chosen, "secs": round(time.time() - t0, 1)}

    sp = cost_repo.session_spend(c, sid)
    summ["cost"] = {"tokens": sp["tokens"], "usd": sp["usd"], "was_live": llm_client.was_live()}
    log(f"\n## COST  tokens={sp['tokens']} usd={sp['usd']} was_live={llm_client.was_live()}")
    return summ


def select_fmt(gt: str) -> str:
    from litnav.artifact.selector import select_format
    return select_format({"goal_type": gt, "user_request": ""})


def main() -> int:
    if os.getenv("LITNAV_LLM_PROVIDER", "none") == "none":
        print("e2e-scenarios SKIP: set LITNAV_LLM_PROVIDER=openai to run."); return 0
    os.environ["LITNAV_LLM_STRICT"] = "1"
    # This Windows host's console is GBK; force UTF-8 so logging multilingual content (−, É, 中文)
    # doesn't crash a scenario mid-run.
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for sc in SCENARIOS:
        lines: list[str] = []

        def log(m: str) -> None:
            lines.append(m); print(m, flush=True)

        print(f"\n========== SCENARIO {sc['id']} / {len(SCENARIOS)} : {sc['slug']} ==========", flush=True)
        try:
            summ = _run_one(sc, log)
        except Exception as e:
            summ = {"id": sc["id"], "slug": sc["slug"], "language": sc["language"],
                    "domain": sc["domain"], "intended_depth": sc["intended_depth"],
                    "errors": [f"FATAL: {e}"]}
            log("\n**FATAL ERROR**\n```\n" + traceback.format_exc() + "\n```")
        (_OUT / f"scenario-{sc['id']:02d}-{sc['slug']}.md").write_text("\n".join(lines), encoding="utf-8")
        results.append(summ)

    (_OUT / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(r.get("cost", {}).get("usd", 0.0) for r in results)
    print(f"\n=== DONE: {len(results)} scenarios; total live usd={round(total,6)} ===")
    print(f"=== logs: {_OUT}/scenario-*.md ; summary: {_OUT}/summary.json ===")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
