# Competition Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn LitNavigator from a preset-button vertical-slice demo into a cohesive, free-input agent UI with a visible cost panel and a broader evidence corpus, ready to record for the ICCSE 2026 submission.

**Architecture:** Keep the proven backend (LangGraph state machine, `TutorSession` interrupt/resume, `build_trace`, SQLite). Add a goal resolver (free text → concept/induce/unknown), a cost helper, a cohesive server-rendered UI (Jinja + CSS, no SPA), an evidence-only corpus-expansion ingest, and recast the reroute demo onto the agent corpus. Every LLM seam keeps a deterministic offline fallback so the 68 tests + G0–G3 stay green with `provider=none`.

**Tech Stack:** Python 3.11, FastAPI + Jinja2, SQLite, OpenAI (`gpt-4o-mini`, `text-embedding-3-small`), pytest, langgraph.

**Spec:** `docs/2026-06-17-competition-push-design.md`

**Baseline:** commit `93687a8`, working tree clean, 68 tests + 4 gates green offline.

**Conventions (follow throughout):**
- After each task: `python -m pytest -q` and the four gates (`python -m litnav.evaluation.verify_m0..m3`) stay green with `LITNAV_LLM_PROVIDER=none`.
- Commit per task. When the user asks to publish: `git push origin HEAD:main`, then ff local main, then verify three refs match. Never commit `.env` or any API key. Co-Authored-By trailer on commits.
- Live smoke (provider=openai) only after an LLM-touching task, run manually.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `litnav/goal.py` (new) | Map free-text goal → `concept` / `induce` / `unknown` | 1 |
| `tests/test_goal.py` (new) | Goal-resolver behavior offline + LLM-slug validation | 1 |
| `litnav/ui/cost.py` (new) | Sum session token cost → tokens + estimated USD | 2 |
| `tests/test_cost.py` (new) | Cost summation correctness | 2 |
| `litnav/ui/templates/agent_home.html` (new) | Goal-entry landing (free-text box + examples + scope line) | 3 |
| `litnav/ui/templates/agent.html` (new) | Cohesive session page: left chat / right glass-box + cost | 3 |
| `litnav/ui/server.py` (modify) | Free-text `/tutor` routes; render the cohesive page | 3 |
| `tests/test_tutor_routes.py` (new) | Route behavior via FastAPI TestClient (offline) | 3 |
| `litnav/ingest/corpus_expand.py` (new) | Evidence-only ingest: download → extract → embed → auto-tag | 4 |
| `tests/test_corpus_expand.py` (new) | Nearest-concept auto-tag + ingest assembly (fakes) | 4 |
| `data/seed/agents_reroute.json` (new) | Agent-corpus fixture with a prerequisite gap | 5 |
| `tests/test_reroute_agents.py` (new) | Reroute increments `route_version` on agents | 5 |
| `docs/demo/shot-script.md` (new) | Shot-by-shot video script | 6 |
| `docs/demo/ppt-outline.md` (new) | Page-by-page PPT outline | 6 |

---

## Task 1: Free-text goal resolver

**Files:**
- Create: `litnav/goal.py`
- Test: `tests/test_goal.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goal.py
import json
from litnav.goal import resolve_goal

_DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))
CONCEPTS = _DATA["concepts"]
OFF = _DATA["induction"]["off_skeleton"]


def test_maps_to_curated_concept_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("I want to understand ReAct", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "react"


def test_maps_to_off_skeleton_induction_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("I keep seeing multi-agent debate, where does it fit?", CONCEPTS, OFF)
    assert r["kind"] == "induce" and r["slug"] == "multi_agent_debate"


def test_unknown_goal_lists_available(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    r = resolve_goal("teach me quantum chromodynamics", CONCEPTS, OFF)
    assert r["kind"] == "unknown" and any("ReAct" in n for n in r["available"])


def test_empty_goal_is_unknown(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert resolve_goal("   ", CONCEPTS, OFF)["kind"] == "unknown"


def test_hallucinated_llm_slug_falls_back_to_keyword(monkeypatch):
    from litnav import goal as goal_mod
    monkeypatch.setattr(goal_mod.llm_client, "complete_json",
                        lambda *a, **k: {"slug": "totally_made_up"})
    r = resolve_goal("tell me about reflection and self-correction", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "reflection"


def test_valid_llm_slug_is_used(monkeypatch):
    from litnav import goal as goal_mod
    monkeypatch.setattr(goal_mod.llm_client, "complete_json",
                        lambda *a, **k: {"slug": "agent_memory"})
    r = resolve_goal("how do agents remember things across steps", CONCEPTS, OFF)
    assert r["kind"] == "concept" and r["slug"] == "agent_memory"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_goal.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'litnav.goal'`.

- [ ] **Step 3: Implement `litnav/goal.py`**

```python
"""Map a learner's free-text goal to a tutor action (the agent's front door).

LLM-backed when a provider is set, with a deterministic keyword fallback so it works
offline and in tests. The LLM only *classifies* into a known slug — validated against the
candidate set, so a hallucinated slug can never start a bogus session.
"""
from __future__ import annotations

from litnav.llm import client as llm_client


def _deterministic(goal: str, concepts: list[dict], off: dict | None) -> dict:
    text = goal.lower()
    if off:
        aliases = {off["slug"].replace("_", " "), off["name"].lower(), "debate"}
        if any(a and a in text for a in aliases):
            return {"kind": "induce", "slug": off["slug"], "name": off["name"]}
    for c in concepts:
        if c["slug"].replace("_", " ") in text:
            return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
        for word in c["name"].lower().replace("(", " ").replace(")", " ").split():
            if len(word) > 3 and word in text:
                return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
    return {"kind": "unknown", "available": [c["name"] for c in concepts]}


def resolve_goal(goal: str, concepts: list[dict], off: dict | None = None) -> dict:
    """Return one of:
        {"kind": "concept", "slug", "name"}    -> plan a route to this curated concept
        {"kind": "induce",  "slug", "name"}    -> induce the off-skeleton scaffold, then teach
        {"kind": "unknown", "available": [..]} -> goal is outside this corpus
    """
    if not (goal or "").strip():
        return {"kind": "unknown", "available": [c["name"] for c in concepts]}
    fallback = _deterministic(goal, concepts, off)

    off_line = f"{off['slug']} ({off['name']})" if off else "(none)"
    prompt = (
        "A learner stated a learning goal. Map it to exactly one option below.\n"
        f"Goal: {goal!r}\n"
        f"Curated concepts (slug: name): {[(c['slug'], c['name']) for c in concepts]}\n"
        f"Off-skeleton concept to INDUCE only if explicitly requested: {off_line}\n"
        'Respond as JSON: {"slug": "<the matching slug, the off-skeleton slug, or null>"}'
    )
    result = llm_client.complete_json(prompt, fallback={"slug": None})
    slug = result.get("slug")

    if off and slug == off["slug"]:
        return {"kind": "induce", "slug": off["slug"], "name": off["name"]}
    by_slug = {c["slug"]: c for c in concepts}
    if slug in by_slug:
        c = by_slug[slug]
        return {"kind": "concept", "slug": c["slug"], "name": c["name"]}
    return fallback  # null/unknown/hallucinated -> deterministic keyword match
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_goal.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add litnav/goal.py tests/test_goal.py
git commit -m "feat(goal): free-text goal resolver (concept/induce/unknown) with offline fallback"
```

---

## Task 2: Session cost helper

**Files:**
- Create: `litnav/ui/cost.py`
- Test: `tests/test_cost.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cost.py
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.ui.cost import session_cost


def _conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    repo.create_session(c, "s", "agents")
    return c


def test_zero_cost_when_no_turns():
    c = _conn()
    assert session_cost(c, "s") == {"tokens": 0, "usd": 0.0}


def test_sums_token_cost_across_turns():
    c = _conn()
    for tok in (281, 190, 64):
        repo.record_tutor_turn(c, "s", 1, "teach", "direct",
                               pre_check_score=0.0, post_check_score=1.0,
                               cited_chunks=[], token_cost=tok,
                               mastery_after=0.8, confidence_after=0.4)
    out = session_cost(c, "s")
    assert out["tokens"] == 535
    assert out["usd"] == round(535 / 1000 * 0.0004, 5)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cost.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'litnav.ui.cost'`.

- [ ] **Step 3: Implement `litnav/ui/cost.py`**

```python
"""Per-session LLM cost, for the efficiency panel.

token_cost is the total tokens recorded per tutor turn (0 offline). We estimate USD with a
single blended gpt-4o-mini rate (input $0.15/1M, output $0.60/1M -> ~$0.0004/1k blended).
Offline (provider=none) every turn costs 0, so a fully offline session shows $0.
"""
from __future__ import annotations

import sqlite3

_USD_PER_1K_TOKENS = 0.0004  # blended gpt-4o-mini estimate


def session_cost(conn: sqlite3.Connection, session_id: str) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(token_cost), 0) FROM tutor_turns WHERE session_id=?",
        (session_id,),
    ).fetchone()
    tokens = int(row[0] or 0)
    return {"tokens": tokens, "usd": round(tokens / 1000 * _USD_PER_1K_TOKENS, 5)}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_cost.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add litnav/ui/cost.py tests/test_cost.py
git commit -m "feat(ui): per-session token/cost helper for the efficiency panel"
```

---

## Task 3: Cohesive free-input UI

Replaces preset buttons with a free-text goal box and a single cohesive session page
(left: conversation; right: glass-box state + cost). Reuses `TutorSession`, `build_trace`,
`resolve_goal`, `session_cost`.

**Files:**
- Create: `litnav/ui/templates/agent_home.html`
- Create: `litnav/ui/templates/agent.html`
- Modify: `litnav/ui/server.py` (tutor section, lines ~91-149)
- Test: `tests/test_tutor_routes.py`

- [ ] **Step 1: Write the failing route tests**

```python
# tests/test_tutor_routes.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")  # deterministic, offline
    from litnav.ui import server
    return TestClient(server.app)


def test_home_shows_free_text_goal_box(client):
    r = client.get("/tutor")
    assert r.status_code == 200
    assert 'name="goal"' in r.text
    assert "Built from" in r.text  # corpus scope line


def test_concept_goal_starts_session(client):
    r = client.get("/tutor/start", params={"goal": "I want to understand ReAct"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)         # redirected to a session page
    assert "ReAct" in r.text               # teaching the matched concept
    assert "route" in r.text.lower()       # right-hand glass box rendered


def test_unknown_goal_returns_home_with_message(client):
    r = client.get("/tutor/start", params={"goal": "teach me quantum chromodynamics"})
    assert r.status_code == 200
    assert 'name="goal"' in r.text          # back on the home form
    assert "isn't in" in r.text or "not in" in r.text


def test_induce_goal_starts_session(client):
    r = client.get("/tutor/start", params={"goal": "I keep seeing multi-agent debate"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tutor_routes.py -q`
Expected: FAIL (current `/tutor/start` takes `mode`, ignores `goal`; no `name="goal"` in home).

- [ ] **Step 3: Create `litnav/ui/templates/agent_home.html`**

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>LitNavigator</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#f6f7fb;color:#1c2430}
 header{background:#1c2430;color:#fff;padding:.8rem 1.2rem}header b{color:#7fd1a6}
 .wrap{max-width:44rem;margin:2rem auto;padding:0 1rem}
 form{display:flex;gap:.5rem;margin:1rem 0}
 input{flex:1;padding:.7rem;font-size:1rem;border:1px solid #c5ccd8;border-radius:8px}
 button{padding:.7rem 1.2rem;border:0;border-radius:8px;background:#5b49c4;color:#fff;font-size:1rem;cursor:pointer}
 .note{color:#b3700d;background:#fff6e5;padding:.6rem .8rem;border-radius:6px}
 .scope{color:#7a8699;font-size:.85rem}
 ul{color:#444}a{color:#5b49c4}
</style></head>
<body>
<header><b>LitNavigator</b> &nbsp; interactive tutor</header>
<div class="wrap">
 <p>Tell the agent what you want to learn. It reads the papers, plans a route, teaches from
    cited evidence, quizzes you, and adapts — inducing new scaffolding when you ask about
    something off the curated map.</p>
 {% if message %}<p class="note">{{ message }}</p>{% endif %}
 <form action="/tutor/start" method="get">
   <input name="goal" autofocus required placeholder="e.g. I want to understand multi-agent debate">
   <button type="submit">Teach me</button>
 </form>
 <p>Try, for example:</p>
 <ul>
   <li><a href="/tutor/start?goal=I want to understand ReAct">I want to understand ReAct</a>
       &nbsp;<i>(misconception &rarr; reteach)</i></li>
   <li><a href="/tutor/start?goal=how do agents remember things across steps">how do agents remember things across steps</a></li>
   <li><a href="/tutor/start?goal=I keep seeing multi-agent debate, where does it fit">I keep seeing multi-agent debate</a>
       &nbsp;<i>(off-skeleton &rarr; induced from the papers)</i></li>
 </ul>
 <p class="scope">Built from {{ n_papers }} LLM-agent papers. Ask within this scope; out-of-scope goals get an honest decline.</p>
</div></body></html>
```

- [ ] **Step 4: Create `litnav/ui/templates/agent.html`**

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>LitNavigator — {{ concept_name }}</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#f6f7fb;color:#1c2430}
 header{background:#1c2430;color:#fff;padding:.8rem 1.2rem}header b{color:#7fd1a6}
 .cols{display:flex;gap:1rem;max-width:72rem;margin:1.2rem auto;padding:0 1rem;align-items:flex-start}
 .left{flex:1.3}.right{flex:1;font-size:.9rem}
 .card{background:#fff;border:1px solid #e2e6ee;border-radius:8px;padding:1rem;margin-bottom:1rem}
 .teach{border-left:3px solid #5b49c4;white-space:pre-wrap;line-height:1.45}
 .q{font-size:1.1rem;font-weight:600;margin:.4rem 0}
 form{display:flex;gap:.5rem}input{flex:1;padding:.55rem .7rem;border:1px solid #c5ccd8;border-radius:8px}
 button{padding:.55rem 1rem;border:0;border-radius:8px;background:#5b49c4;color:#fff;cursor:pointer}
 .fb{background:#fff8ec;border-radius:6px;padding:.5rem .7rem}.miscon{color:#8a1f4c}
 .bars span{display:inline-block;height:.6rem;border-radius:3px;vertical-align:middle}
 .m{background:#5b49c4}.c{background:#7fd1a6}
 .step{padding:.15rem 0}.done-s{color:#258a51}.active-s{font-weight:600}
 .consensus{color:#258a51}.contested{color:#b3700d}.open{color:#cf4f24}
 .cost{background:#eef3ff;border:1px solid #cfe0ff}.mut{color:#7a8699;font-size:.8rem}
 a{color:#5b49c4}
</style></head>
<body>
<header><b>LitNavigator</b> &nbsp; goal: {{ concept_name or "…" }}
  &nbsp;<span class="mut">corpus: {{ n_papers }} papers</span></header>
<div class="cols">
 <div class="left">
  {% if teach %}<div class="card teach">{{ teach|replace('**','') }}</div>{% endif %}
  {% if last_feedback %}<div class="card fb">{{ last_feedback }}
    {% if last_detected_misconception %}<span class="miscon">· misconception: {{ last_detected_misconception }}</span>{% endif %}</div>{% endif %}
  {% if done %}
    <div class="card"><b>Session complete.</b><br>
      <a href="/sessions/{{ sid }}">full trace panel &rarr;</a> · <a href="/tutor">start another</a></div>
  {% else %}
    <div class="card"><div class="q">{{ question }}</div>
      <form method="get" action="/tutor/{{ sid }}/answer">
        <input name="answer" autocomplete="off" autofocus placeholder="type your answer…">
        <button type="submit">Answer</button></form></div>
  {% endif %}
 </div>
 <div class="right">
  <div class="card"><b>Route</b> <span class="mut">v{{ trace.route_version }}</span>
   {% for s in trace.route %}<div class="step {{ 'done-s' if s.status in ['done','conceded'] else ('active-s' if s.status=='active' else '') }}">
     {{ s.name }} <span class="mut">[{{ s.status }}]</span></div>{% endfor %}</div>
  <div class="card"><b>Learner model</b>
   {% for c in trace.concepts if c.n_observations %}
     <div class="step"><span class="{{ c.frontier_flag or '' }}">{{ c.name }}</span>
       <div class="bars">m<span class="m" style="width:{{ (c.mastery*80)|round }}px"></span> {{ c.mastery }}
        · c<span class="c" style="width:{{ (c.confidence*80)|round }}px"></span> {{ c.confidence }}</div>
       {% if c.held_misconceptions %}<span class="mut miscon">holds: {{ c.held_misconceptions|join(', ') }}</span>{% endif %}
     </div>{% endfor %}</div>
  {% if trace.induced_edges %}<div class="card"><b>Induced (machine-derived)</b>
   {% for i in trace.induction %}<div class="step">[{{ i.kind }}] conf {{ i.confidence }}
     <span class="mut">basis {{ i.confidence_basis }}</span></div>{% endfor %}</div>{% endif %}
  <div class="card cost"><b>Cost this session</b><br>
   {{ cost.tokens }} LLM tokens ≈ ${{ cost.usd }} <span class="mut">(gpt-4o-mini; offline = $0)</span></div>
 </div>
</div></body></html>
```

- [ ] **Step 5: Rewrite the tutor section of `litnav/ui/server.py`**

Replace the import block addition and the section from `# ── Interactive tutor` through `tutor_start` (lines ~91-133). Add near the top imports:

```python
from litnav.goal import resolve_goal
from litnav.ui.cost import session_cost
```

Replace `tutor_home` and `tutor_start` (and add a fixture constant + helpers); keep
`_start_tutor`, `tutor_page`, `tutor_answer` but update `tutor_page` to render the new page:

```python
# Prefer the evidence-expanded fixture (Task 4) when present; else the curated 8-paper one.
_TUTOR_FIXTURE = ("data/seed/agents_expanded.json"
                  if Path("data/seed/agents_expanded.json").exists()
                  else "data/seed/agents_m3.json")


def _fixture_data() -> dict:
    return json.loads(Path(_TUTOR_FIXTURE).read_text(encoding="utf-8"))


def _n_papers(data: dict) -> int:
    if data.get("papers"):
        return len(data["papers"])
    ids = {c.get("paper_id") for c in data.get("chunks", []) if c.get("paper_id") is not None}
    return len(ids) or len(data["concepts"])


@app.get("/tutor", response_class=HTMLResponse)
def tutor_home(message: str = ""):
    return _TEMPLATES.get_template("agent_home.html").render(
        message=message, n_papers=_n_papers(_fixture_data()))


@app.get("/tutor/start")
def tutor_start(goal: str = ""):
    data = _fixture_data()
    plan = resolve_goal(goal, data["concepts"], data["induction"]["off_skeleton"])
    if plan["kind"] == "concept":
        slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
        sid = _start_tutor(_TUTOR_FIXTURE, [slug_to_id[plan["slug"]]], None)
    elif plan["kind"] == "induce":
        sid = _start_tutor(_TUTOR_FIXTURE, [], data["induction"])
    else:
        avail = ", ".join(plan["available"])
        return tutor_home(message=f"“{goal}” isn't in this paper corpus. I can teach: {avail}.")
    return RedirectResponse(f"/tutor/{sid}", status_code=303)
```

Update `tutor_page` to render the cohesive page with trace + cost:

```python
@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ts = _TUTORS.get(sid)
    if ts is None:
        return RedirectResponse("/tutor", status_code=303)
    return _TEMPLATES.get_template("agent.html").render(
        sid=sid, n_papers=_n_papers(_fixture_data()), trace=_trace_for(sid),
        cost=session_cost(ts.conn, sid), **ts.current())
```

> Note: `RedirectResponse(status_code=303)` from `/tutor/start` makes `TestClient` follow to
> `/tutor/{sid}` (200), satisfying `test_concept_goal_starts_session`. The unknown branch
> returns the rendered home (200) directly.

- [ ] **Step 6: Run route tests + full suite**

Run: `python -m pytest tests/test_tutor_routes.py -q && python -m pytest -q`
Expected: route tests PASS; full suite still green (existing `test_interactive.py` untouched — it drives `TutorSession` directly, not the HTTP layer).

- [ ] **Step 7: Live smoke (manual, optional now)**

```bash
python -m litnav.ui.server   # open http://127.0.0.1:8000/tutor, type a goal, answer a quiz
```
Expected: free-text goal starts a session; right panel shows route/mastery/cost; out-of-scope goal returns an honest message.

- [ ] **Step 8: Commit**

```bash
git add litnav/ui/server.py litnav/ui/templates/agent_home.html litnav/ui/templates/agent.html tests/test_tutor_routes.py
git commit -m "feat(ui): cohesive free-input agent UI with glass-box state + cost panel"
```

---

## Task 4: Evidence-only corpus expansion (into a fixture the tutor uses)

Add ~20 more agent papers as **evidence only**, auto-tagged to the nearest existing concept,
and write the result as `data/seed/agents_expanded.json` (= the curated `agents_m3.json`
spine + appended `papers`/`chunks`). Because tutor sessions seed from this fixture (Task 3
points `_TUTOR_FIXTURE` at it when present), the broader corpus actually reaches the live
tutor and the "Built from N papers" count is real. No new concepts/quizzes; the teachable
spine and money shots are untouched. Auto-tagging uses concept-name embeddings at build
time, so the tagged result is baked into the fixture (no runtime embedding needed for
default concept-tagged teaching).

**Files:**
- Create: `litnav/ingest/corpus_expand.py`
- Test: `tests/test_corpus_expand.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_corpus_expand.py
import json
from litnav.ingest import corpus_expand as ce


def test_nearest_concept_picks_highest_cosine():
    centroids = {1: [1.0, 0.0], 2: [0.0, 1.0]}
    assert ce._nearest_concept([0.9, 0.1], centroids) == 1
    assert ce._nearest_concept([0.1, 0.9], centroids) == 2


def test_build_expanded_fixture_tags_and_appends(tmp_path, monkeypatch):
    """New papers' chunks are tagged to the nearest concept and appended; spine preserved."""
    # Concept-name embeddings: 'react' name -> [1,0]; all other names + chunks -> [0,1],
    # except a chunk containing 'reason' -> [1,0] so it tags to react.
    def fake_embed(texts):
        out = []
        for t in texts:
            low = t.lower()
            out.append([1.0, 0.0] if ("react" in low or "reason" in low) else [0.0, 1.0])
        return out
    monkeypatch.setattr(ce.llm_client, "embed_texts", fake_embed)

    papers = [{"arxiv_id": "9999.00001", "title": "A ReAct follow-up",
               "chunks": ["This work reasons then acts.", "Unrelated memory text."]}]
    out = tmp_path / "agents_expanded.json"
    n = ce.build_expanded_fixture("data/seed/agents_m3.json", papers, str(out))
    assert n == 2

    data = json.loads(out.read_text(encoding="utf-8"))
    base = json.loads(open("data/seed/agents_m3.json", encoding="utf-8").read())
    assert len(data["concepts"]) == len(base["concepts"])          # spine preserved
    assert "induction" in data                                     # induction candidate kept
    new = [c for c in data["chunks"] if c["id"].startswith("cx_9999.00001")]
    assert len(new) == 2 and all(c["concept_id"] is not None for c in new)
    react_id = next(c["id"] for c in data["concepts"] if c["slug"] == "react")
    assert new[0]["concept_id"] == react_id                        # 'reasons then acts' -> react
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_corpus_expand.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'litnav.ingest.corpus_expand'`.

- [ ] **Step 3: Implement `litnav/ingest/corpus_expand.py`**

```python
"""Evidence-only corpus expansion: add more agent papers as retrieval/teaching evidence
without authoring new concepts or quizzes.

build_expanded_fixture() embeds each new chunk, tags it to the nearest existing concept (by
concept-name embedding), and writes agents_m3.json's spine + the appended papers/chunks to a
new fixture. Tutor sessions seed from that fixture, so the broader corpus reaches the live
tutor. Offline (provider=none) embed_texts returns None -> raises a clear error (run with a
provider set); the gates never call this.

CLI:  python -m litnav.ingest.corpus_expand    # downloads the curated arXiv list -> fixture
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from litnav.llm import client as llm_client

# Curated starting list of well-known LLM-agent papers (arXiv ids). VERIFY each id resolves
# and DEDUPE against ids already in the base fixture's papers before downloading; adjust.
ARXIV_IDS = [
    "2302.04761",  # Toolformer
    "2303.17580",  # HuggingGPT
    "2307.16789",  # ToolLLM
    "2308.08155",  # AutoGen
    "2308.00352",  # MetaGPT
    "2303.17760",  # CAMEL
    "2305.10601",  # Tree of Thoughts
    "2308.09687",  # Graph of Thoughts
    "2303.17651",  # Self-Refine
    "2305.18323",  # ReWOO
    "2305.04091",  # Plan-and-Solve
    "2307.07924",  # ChatDev
    "2308.03688",  # AgentBench
    "2305.15334",  # Gorilla
    "2306.06070",  # Mind2Web
    "2307.13854",  # WebArena
    "2309.07864",  # Rise and Potential of LLM-Based Agents (survey)
    "2305.14325",  # Multi-agent debate (society of minds)
    "2302.01560",  # DEPS (describe-explain-plan-select)
    "2305.17390",  # SwiftSage
]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def _nearest_concept(vec: list[float], centroids: dict[int, list[float]]) -> int:
    return max(centroids, key=lambda cid: _cosine(vec, centroids[cid]))


def build_expanded_fixture(base_path: str, papers: list[dict], out_path: str) -> int:
    """Append evidence-only papers to the base fixture, tagging each chunk to its nearest
    concept. Returns the number of chunks appended. Raises if embeddings are unavailable."""
    base = json.loads(Path(base_path).read_text(encoding="utf-8"))
    concepts = base["concepts"]
    concept_vecs = llm_client.embed_texts([c["name"] for c in concepts])
    if not concept_vecs:
        raise RuntimeError("Embeddings unavailable (set LITNAV_LLM_PROVIDER=openai).")
    centroids = {c["id"]: v for c, v in zip(concepts, concept_vecs)}

    base.setdefault("papers", [])
    base.setdefault("chunks", [])
    next_pid = max((p["id"] for p in base["papers"]), default=0) + 1
    added = 0
    for paper in papers:
        chunk_vecs = llm_client.embed_texts(paper["chunks"])
        if not chunk_vecs:
            continue
        base["papers"].append({"id": next_pid, "arxiv_id": paper["arxiv_id"],
                               "title": paper.get("title", paper["arxiv_id"])})
        for i, (text, vec) in enumerate(zip(paper["chunks"], chunk_vecs)):
            base["chunks"].append({
                "id": f"cx_{paper['arxiv_id']}_{i}", "paper_id": next_pid,
                "concept_id": _nearest_concept(vec, centroids),
                "section": "evidence", "chunk_index": i, "text": text,
            })
            added += 1
        next_pid += 1

    Path(out_path).write_text(json.dumps(base, ensure_ascii=True, indent=2), encoding="utf-8")
    return added
```

> Verify the chunk dict keys (`section`, `chunk_index`, …) match what `seed_demo_data`
> expects by skimming `litnav/storage/seed.py`; adjust key names to the existing schema if
> they differ. Do not invent keys the seeder doesn't read.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_corpus_expand.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Add a CLI runner to `corpus_expand.py`**

```python
def _download_and_extract(arxiv_id: str) -> dict | None:  # pragma: no cover - network
    import urllib.request
    from litnav.ingest.pdf_extract import _chunks_from_pdf_bytes  # reuse the extractor
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        chunks = _chunks_from_pdf_bytes(data)  # list[str], abstract-onward
        return {"arxiv_id": arxiv_id, "title": arxiv_id, "chunks": chunks[:6]}
    except Exception as e:
        print(f"skip {arxiv_id}: {e}")
        return None


def main() -> int:  # pragma: no cover - manual
    from litnav.config import load_dotenv
    load_dotenv()
    base = json.loads(Path("data/seed/agents_m3.json").read_text(encoding="utf-8"))
    existing = {p.get("arxiv_id") for p in base.get("papers", [])}
    papers = []
    for aid in ARXIV_IDS:
        if aid in existing:
            continue
        p = _download_and_extract(aid)
        if p and p["chunks"]:
            papers.append(p)
            print(f"fetched {aid} ({len(p['chunks'])} chunks)")
    n = build_expanded_fixture("data/seed/agents_m3.json", papers,
                               "data/seed/agents_expanded.json")
    print(f"wrote data/seed/agents_expanded.json (+{n} evidence chunks, "
          f"{len(papers)} papers). If few succeeded, expansion is de-scopable.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

> Before relying on `_chunks_from_pdf_bytes`, open `litnav/ingest/pdf_extract.py` and confirm
> the helper name/signature; if the existing extractor only takes a path, add a small
> `_chunks_from_pdf_bytes(data)` that wraps `pypdf.PdfReader(io.BytesIO(data))` mirroring the
> existing extraction (abstract-onward trim). Keep it `# pragma: no cover`.

- [ ] **Step 6: Run the expansion (manual, needs key + network)**

```bash
python -m litnav.ingest.corpus_expand
python -m pytest -q          # full suite still green (new fixture doesn't break gates)
```
Expected: `data/seed/agents_expanded.json` written; tutor now seeds from it and shows the
larger paper count. If most downloads fail, the fixture isn't created and the tutor falls
back to `agents_m3.json` (8 papers) — acceptable (de-scopable).

- [ ] **Step 7: Commit**

```bash
git add litnav/ingest/corpus_expand.py tests/test_corpus_expand.py
git add data/seed/agents_expanded.json   # if produced
git commit -m "feat(ingest): evidence-only corpus expansion into agents_expanded.json fixture"
```

---

## Task 5: Recast the reroute money shot onto the agent corpus (de-scopable)

Goal: the missing-prerequisite reroute (Money Shot 1) should demo on agents, not the RAG
fixture, so the video's main thread stays in one domain. **Fallback if risky:** keep the RAG
reroute and do a labeled scene-switch in the video (no code) — decide at execution.

**Files:**
- Create: `data/seed/agents_reroute.json`
- Test: `tests/test_reroute_agents.py`

- [ ] **Step 1: Study the existing reroute mechanism**

Run and read:
```bash
python -m litnav.app demo-m1 --answer wrong_prereq
```
Open `data/seed/rag_demo.json`, `litnav/nodes/diagnose.py`, `litnav/nodes/replan.py`. Note
the fixture shape that makes reroute fire: a target concept with a curated **prerequisite
edge** to a concept NOT in `targets`, plus a quiz whose wrong answer the diagnoser maps to
that missing prerequisite. Replicate exactly this shape with agent concepts.

- [ ] **Step 2: Write the failing gate test**

```python
# tests/test_reroute_agents.py
import json, sqlite3, uuid
from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_reroute.json"


def test_wrong_prereq_reroutes_on_agents():
    data = json.loads(open(FIXTURE, encoding="utf-8").read())
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn); seed_demo_data(conn, FIXTURE)
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    slug_to_id = {c["slug"]: c["id"] for c in data["concepts"]}
    target_ids = [slug_to_id[s] for s in data["targets"]]
    sid = str(uuid.uuid4())
    app = build_graph(conn, ckpt)
    state = make_initial_state(sid, data["topic"], target_ids,
                               pending_answers=data["demo_wrong_prereq_answers"],
                               mastery_threshold=0.8)
    app.invoke(state, {"configurable": {"thread_id": sid}, "recursion_limit": 80})
    versions = [r[0] for r in conn.execute(
        "SELECT DISTINCT route_version FROM route_steps WHERE session_id=?", (sid,)).fetchall()]
    assert max(versions) >= 2, "a prerequisite gap must bump route_version"
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_reroute_agents.py -q`
Expected: FAIL (fixture file missing).

- [ ] **Step 4: Author `data/seed/agents_reroute.json`**

Mirror `rag_demo.json`'s reroute structure with agent concepts. Concretely: pick a target
(e.g. `reflection`) with a curated prerequisite edge from a concept left out of `targets`
(e.g. `tool_use`), add `targets`, `demo_wrong_prereq_answers`, and the chunks/quizzes/
misconception the diagnoser needs — using the same JSON keys `rag_demo.json` uses (verified
in Step 1). Keep it minimal: the two concepts, one prereq edge, one quiz per concept, one
short evidence chunk each. The exact field names come from Step 1; do not invent new keys.

- [ ] **Step 5: Run gate test to verify pass**

Run: `python -m pytest tests/test_reroute_agents.py -q`
Expected: PASS.

- [ ] **Step 6: Wire a CLI demo (optional) + commit**

Optionally add a `demo-reroute` branch in `litnav/app.py` mirroring `_run` with this fixture
and `targets`. Then:

```bash
python -m pytest -q   # full suite green
git add data/seed/agents_reroute.json tests/test_reroute_agents.py litnav/app.py
git commit -m "feat(demo): recast missing-prerequisite reroute onto the agent corpus"
```

---

## Task 6: Deliverable docs (video shot script + PPT outline)

Content, not code — produced from the design's §5. No tests; these guide the team's
recording and slides.

**Files:**
- Create: `docs/demo/shot-script.md`
- Create: `docs/demo/ppt-outline.md`

- [ ] **Step 1: Write `docs/demo/shot-script.md`**

One section per shot (0–7 from spec §5.1). Each section: **on-screen action** (exact
clicks/typed goal on the new UI), **narration** (one or two spoken sentences), **point-at**
(the exact trace fields to highlight: `route_version`, `detected_misconception`, the
mastery/confidence bars, `source='induced'`, `confidence_basis`, the cost panel), and
**counterfactual** where relevant. Keep total runtime 3–5 min.

- [ ] **Step 2: Write `docs/demo/ppt-outline.md`**

One bullet block per slide (10–12 slides from spec §5.2). Each slide: **title**, **3-5
bullets**, **visual** (which screenshot/diagram), and the **criterion it targets** (so the
D6 coverage review can confirm all six criteria appear).

- [ ] **Step 3: Commit**

```bash
git add docs/demo/shot-script.md docs/demo/ppt-outline.md
git commit -m "docs(demo): shot-by-shot video script + PPT outline mapped to the six criteria"
```

---

## Final verification

- [ ] `python -m pytest -q` → all green (≈ 68 + new tests).
- [ ] `LITNAV_LLM_PROVIDER=none` gates: `verify_m0..m3` all PASS offline.
- [ ] Live smoke (provider=openai): free-text goal → teach/quiz/adapt; cost panel > 0; out-of-scope decline; corpus shows expanded paper count.
- [ ] When the user approves publishing: push + ff local main + verify three refs.
