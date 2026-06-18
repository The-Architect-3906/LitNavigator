# Two-Mode Agent UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `/tutor` UI into two switchable views of one live session — a streaming Chat and an agentic Glass-box — driven by real per-node SSE streaming, and fix the evidence-pollution regression.

**Architecture:** Keep the backend (TutorSession over the LangGraph graph, SQLite, `current()`). The session still runs to the first interrupt when created (so the page is always complete and the no-JS fallback + existing tests hold). Each *answer* turn is streamed live via `app.stream(stream_mode="updates")` over an SSE endpoint, so the glass-box flow lights up node-by-node. The first teaching turn is server-rendered and given a client-side typewriter reveal. One template holds both views; a client-side toggle switches them. Native `EventSource` + `fetch`, no framework.

**Tech Stack:** FastAPI + Jinja2, LangGraph streaming, SQLite, vanilla JS (EventSource), pytest.

**Spec:** `docs/2026-06-18-two-mode-ui-design.md`

**Baseline:** commit `debe78d`, 86 tests + G0–G3 green offline.

**Resolution of spec §8 (made here):** rather than deferring the first run to the stream, the session runs at creation (unchanged `_start_tutor`/`start()`), the first teach is server-rendered + client-typewritered, and **per-answer turns animate live** via SSE (this is where reteach/replan/concede/induce — the agentic money shots — happen). This keeps all existing tests green and is lower-risk than deferring first-run.

**Conventions:** Work in the worktree `C:/Users/Architect117/LitNavigator/.claude/worktrees/eloquent-khorana-8c9ed9` (prefix shell commands with `cd "<worktree>" &&`; confirm `git rev-parse --show-toplevel` ends with `eloquent-khorana-8c9ed9` before committing). After each task: `python -m pytest -q` + the four gates green offline (`LITNAV_LLM_PROVIDER=none`). Commit per task; do not push. Co-Authored-By trailer on every commit:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `litnav/nodes/retrieve.py` (modify) | rank curated (`c_`) chunks before expansion (`cx_`) | 1 |
| `tests/test_retrieve_order.py` (new) | curated-first ordering | 1 |
| `litnav/ui/interactive.py` (modify) | `current()` adds `cited`; add `stream_answer()` + step/terminal events | 2, 3 |
| `tests/test_interactive.py` (modify) | `cited` is cited-only; stream emits steps + terminal events | 2, 3 |
| `litnav/ui/server.py` (modify) | SSE endpoint `/tutor/{sid}/events` | 4 |
| `tests/test_tutor_routes.py` (modify) | events endpoint streams `text/event-stream` | 4 |
| `litnav/ui/templates/agent.html` (rewrite) | two views + toggle + EventSource JS + typewriter | 5 |
| (preview verification) | live screenshots of both modes + an answer turn | 6 |

---

## Task 1: Rank curated chunks before expansion chunks

**Files:**
- Modify: `litnav/nodes/retrieve.py` (`_concept_tagged`)
- Test: `tests/test_retrieve_order.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retrieve_order.py
import sqlite3
from litnav.nodes.retrieve import retrieve_node
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data


def test_curated_chunks_rank_before_expansion():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, "data/seed/agents_m2.json")   # react = concept 1, curated c_react_* chunks
    # inject an expansion-style chunk tagged to the same concept
    conn.execute(
        "INSERT INTO paper_chunks (id, paper_id, concept_id, text, chunk_index) "
        "VALUES ('cx_test_0', NULL, 1, 'tangential expansion text', 9)")
    conn.commit()

    out = retrieve_node({"current_concept_id": 1}, conn)
    ids = [e["chunk_id"] for e in out["current_evidence"]]
    assert ids, "react has evidence"
    assert ids[0].startswith("c_") and not ids[0].startswith("cx_"), "curated chunk first"
    assert ids[-1] == "cx_test_0", "expansion chunk pushed to the end"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_retrieve_order.py -q`
Expected: FAIL (current `_concept_tagged` has no ORDER BY; `cx_test_0` may appear before curated chunks).

- [ ] **Step 3: Add ordering to `_concept_tagged`**

Replace the `conn.execute(...)` in `_concept_tagged` with:

```python
    rows = conn.execute(
        "SELECT id, text, paper_id FROM paper_chunks WHERE concept_id=? "
        "ORDER BY CASE WHEN substr(id, 1, 3)='cx_' THEN 1 ELSE 0 END, rowid",
        (concept_id,),
    ).fetchall()
```

(`rowid` preserves seed insertion order for curated chunks — unchanged behavior — while `cx_` chunks sort last.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_retrieve_order.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` (expect all green — `test_m2_tutor::test_teach_cites_chunk` still passes since curated order is preserved).
```bash
git add litnav/nodes/retrieve.py tests/test_retrieve_order.py
git commit -m "fix(retrieve): rank curated chunks before expansion chunks"
```

---

## Task 2: `current()` exposes cited-only evidence

**Files:**
- Modify: `litnav/ui/interactive.py` (`current()` return dict)
- Test: `tests/test_interactive.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_interactive.py`)**

```python
def test_current_cited_is_only_the_cited_chunk():
    ts = _session()
    s = ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    assert s["cited"], "the cited chunk(s) are exposed for the glass box"
    cited_ids = {c["chunk_id"] for c in s["cited"]}
    ev_ids = {e["chunk_id"] for e in s["evidence"]}
    assert cited_ids <= ev_ids, "cited is a subset of retrieved evidence"
    assert len(s["cited"]) <= len(s["evidence"])
    assert all(cid.startswith("c_react") for cid in cited_ids), "cited the curated react chunk"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_interactive.py::test_current_cited_is_only_the_cited_chunk -q`
Expected: FAIL with `KeyError: 'cited'`.

- [ ] **Step 3: Add `cited` to the `current()` return dict**

In `litnav/ui/interactive.py`, inside the `return { ... }` of `current()`, add this key (next to `evidence`):

```python
            "cited": [
                {"chunk_id": cid,
                 "text": (self.conn.execute("SELECT text FROM paper_chunks WHERE id=?", (cid,)).fetchone() or [""])[0],
                 "paper_id": (self.conn.execute("SELECT paper_id FROM paper_chunks WHERE id=?", (cid,)).fetchone() or [None])[0]}
                for cid in (vals.get("current_cited_chunks") or [])
            ],
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_interactive.py -q`
Expected: PASS (all interactive tests).

- [ ] **Step 5: Commit**

```bash
git add litnav/ui/interactive.py tests/test_interactive.py
git commit -m "feat(ui): current() exposes cited-only evidence for the glass box"
```

---

## Task 3: Stream an answer turn node-by-node

**Files:**
- Modify: `litnav/ui/interactive.py` (add label map, `_step_event`, `_terminal_events`, `stream_answer`)
- Test: `tests/test_interactive.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_interactive.py`)**

```python
def test_stream_answer_emits_steps_and_terminal_events():
    ts = _session()
    ts.start("agents", target_concept_ids=[REACT], mastery_threshold=0.75)
    events = list(ts.stream_answer("it is just chain of thought"))  # wrong -> misconception -> reteach
    types = [e["type"] for e in events]
    nodes = [e["node"] for e in events if e["type"] == "step"]
    assert "grade" in nodes
    assert any(n in ("reteach", "teach") for n in nodes), "reteach/teach step streamed"
    assert "teach" in types and "question" in types and "state" in types
    assert types[-1] == "done"
    grade_ev = next(e for e in events if e.get("node") == "grade")
    assert "react_is_just_cot" in grade_ev["detail"], "grade step carries the detected misconception"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_interactive.py::test_stream_answer_emits_steps_and_terminal_events -q`
Expected: FAIL with `AttributeError: 'TutorSession' object has no attribute 'stream_answer'`.

- [ ] **Step 3: Add streaming to `TutorSession`**

Add `from litnav.ui.cost import session_cost` to the imports of `litnav/ui/interactive.py`. Add this class attribute and these methods to `TutorSession` (after `answer`):

```python
    _STEP_LABELS = {
        "planner": "Planning the route",
        "induce": "Inducing scaffold from the papers",
        "select_next": "Selecting the next concept",
        "retrieve": "Retrieving evidence",
        "teach": "Teaching (grounded in evidence)",
        "check": "Posing a quiz",
        "grade": "Grading your answer",
        "diagnose": "Diagnosing a missing prerequisite",
        "replan": "Re-planning the route",
        "advance": "Advancing",
        "reteach": "Re-teaching with a new strategy",
        "concede": "Conceding honestly",
    }

    def _step_event(self, node: str, delta: dict) -> dict:
        detail = ""
        if node == "retrieve":
            detail = f"{len(delta.get('current_evidence') or [])} chunks"
        elif node in ("teach", "reteach"):
            detail = delta.get("current_strategy") or ""
        elif node == "grade":
            qr = delta.get("quiz_result") or {}
            detail = "correct" if qr.get("score") == 1.0 else "wrong"
            if qr.get("detected_misconception"):
                detail += f" · {qr['detected_misconception']}"
        elif node == "induce":
            detail = "source=induced"
        return {"type": "step", "node": node,
                "label": self._STEP_LABELS.get(node, node), "detail": detail}

    def _terminal_events(self) -> list[dict]:
        cur = self.current()
        return [
            {"type": "teach", "text": cur.get("teach") or "", "cited": cur.get("cited") or []},
            {"type": "question", "text": cur.get("question") or ""},
            {"type": "state", "route": cur["route"], "route_version": cur["route_version"],
             "learner": cur["learner"], "cited": cur["cited"], "decision": cur["decision"],
             "rationale": cur["rationale"], "induced": cur["induced"], "intent": cur.get("intent"),
             "cost": session_cost(self.conn, self.sid)},
            {"type": "done", "done": cur["done"], "mastery": cur.get("mastery"),
             "confidence": cur.get("confidence")},
        ]

    def stream_answer(self, text: str):
        """Inject the answer and resume, yielding one event per executed node, then the
        terminal teach/question/state/done events. Used by the SSE endpoint."""
        self.app.update_state(self.config, {"user_answer": text, "pending_answers": []})
        for update in self.app.stream(None, self.config, stream_mode="updates"):
            for node, delta in update.items():
                yield self._step_event(node, delta or {})
        for ev in self._terminal_events():
            yield ev
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_interactive.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add litnav/ui/interactive.py tests/test_interactive.py
git commit -m "feat(ui): stream an answer turn node-by-node for the live glass box"
```

---

## Task 4: SSE endpoint

**Files:**
- Modify: `litnav/ui/server.py` (import + new route)
- Test: `tests/test_tutor_routes.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_tutor_routes.py`)**

```python
def test_events_endpoint_streams_answer_turn(client):
    r = client.get("/tutor/start", params={"goal": "I want to understand ReAct"})
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.get(f"/tutor/{sid}/events",
                    params={"answer": "the agent takes actions and observations"})
    assert ev.status_code == 200
    assert "text/event-stream" in ev.headers["content-type"]
    assert "data:" in ev.text
    assert '"done"' in ev.text          # the terminal done event was streamed


def test_events_endpoint_unknown_session_404(client):
    ev = client.get("/tutor/does-not-exist/events")
    assert ev.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_tutor_routes.py -q`
Expected: FAIL (no `/tutor/{sid}/events` route).

- [ ] **Step 3: Add the SSE endpoint to `litnav/ui/server.py`**

Add `StreamingResponse` to the fastapi.responses import line:

```python
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
```

Add this route (next to the other `/tutor` routes):

```python
@app.get("/tutor/{sid}/events")
def tutor_events(sid: str, answer: str = ""):
    ts = _TUTORS.get(sid)
    if ts is None:
        return JSONResponse({"type": "error", "message": "no such session"}, status_code=404)

    def gen():
        try:
            stream = ts.stream_answer(answer) if answer.strip() else iter(ts._terminal_events())
            for ev in stream:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
```

(No answer → emit the current terminal state as events, for the JS to hydrate the glass box on load. An answer → stream the turn live.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_tutor_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + gates + commit**

Run: `python -m pytest -q` and `python -m litnav.evaluation.verify_m0` … `verify_m3` (all green offline).
```bash
git add litnav/ui/server.py tests/test_tutor_routes.py
git commit -m "feat(ui): SSE endpoint streaming the agent's per-node steps"
```

---

## Task 5: Rewrite `agent.html` — two views, toggle, streaming JS

**Files:**
- Rewrite: `litnav/ui/templates/agent.html`

No unit test (HTML/JS); verified live in Task 6. The server-rendered content keeps the
no-JS fallback working (route tests in Task 4 still pass). The page renders the initial
turn from `current()` server-side, then JS adds the mode toggle, a typewriter reveal of the
first teach, and live SSE animation for each answer.

- [ ] **Step 1: Replace `litnav/ui/templates/agent.html` with:**

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LitNavigator — {{ concept_name or "tutor" }}</title>
<style>
 :root{--accent:#5b49c4;--ok:#258a51;--warn:#b3700d}
 *{box-sizing:border-box}
 body{font-family:system-ui,sans-serif;margin:0;background:#f6f7fb;color:#1c2430}
 header{background:#1c2430;color:#fff;padding:.7rem 1.1rem;display:flex;align-items:center;gap:.8rem;flex-wrap:wrap}
 header b{color:#7fd1a6}
 .toggle{margin-left:auto;display:flex;border:1px solid #3a4456;border-radius:8px;overflow:hidden}
 .toggle button{background:transparent;color:#cdd5e0;border:0;padding:.35rem .8rem;font-size:.85rem;cursor:pointer}
 .toggle button.on{background:var(--accent);color:#fff}
 .mut{color:#7a8699;font-size:.8rem}
 .cols{display:flex;gap:1rem;max-width:60rem;margin:1.2rem auto;padding:0 1rem;align-items:flex-start}
 .card{background:#fff;border:1px solid #e2e6ee;border-radius:10px;padding:1rem;margin-bottom:1rem}
 /* chat */
 #chat{flex:1;min-width:0}
 .bubble{max-width:85%;padding:.6rem .85rem;border-radius:14px;margin:.5rem 0;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
 .me{margin-left:auto;background:#e6e2fb;color:#2a2270}
 .ai{background:#fff;border:1px solid #e2e6ee}
 .qa{font-weight:500}
 .working{color:var(--accent);font-size:.85rem;margin:.3rem 0}
 .answer{display:flex;gap:.5rem;margin-top:.6rem}
 .answer input{flex:1;padding:.55rem .7rem;border:1px solid #c5ccd8;border-radius:8px;font-size:1rem}
 .answer button{padding:.55rem 1rem;border:0;border-radius:8px;background:var(--accent);color:#fff;cursor:pointer}
 /* glass box */
 #glass{flex:1;min-width:0;font-size:.9rem}
 .step{display:flex;gap:.5rem;padding:.25rem 0;align-items:baseline}
 .step .ic{width:1.1rem;text-align:center}
 .step.done .ic{color:var(--ok)} .step.active{background:#eef0ff;border-radius:6px;padding:.25rem .4rem}
 .step.pending{color:#9aa3b2}
 .bars span{display:inline-block;height:.55rem;border-radius:3px;vertical-align:middle}
 .barm{background:var(--accent)} .barc{background:#7fd1a6}
 .ev{font-size:.82rem;color:#3a4456;border-left:2px solid var(--accent);padding-left:.5rem;margin:.3rem 0}
 .costp{background:#eef3ff;border-color:#cfe0ff}
 body.mode-chat #glass{display:none}
 body.mode-glass #chat{display:none}
 @media(max-width:760px){.cols{flex-direction:column} body.mode-glass #chat,body.mode-chat #glass{display:block}}
</style></head>
<body class="mode-chat" data-sid="{{ sid }}">
<header><b>LitNavigator</b>
  <span>{{ concept_name or "tutor" }}</span>
  <span class="mut">{{ n_papers }} papers{% if intent %} · {{ intent }}{% endif %}</span>
  <span class="toggle"><button id="t-chat" class="on" onclick="setMode('chat')">Chat</button><button id="t-glass" onclick="setMode('glass')">Glass box</button></span>
</header>
<div class="cols">
  <div id="chat">
    <div id="thread">
      <div class="bubble me">{{ concept_name or "Teach me" }}</div>
      {% if teach %}<div class="bubble ai" id="first-teach" data-text="{{ teach|replace('**','') }}"></div>{% endif %}
      {% if question %}<div class="bubble ai qa">{{ question }}</div>{% endif %}
    </div>
    <div class="working" id="working" style="display:none">● agent working…</div>
    {% if not done %}
    <form class="answer" id="answer-form" onsubmit="return submitAnswer(event)">
      <input id="answer-input" autocomplete="off" autofocus placeholder="type your answer…">
      <button type="submit">Answer</button>
    </form>
    {% else %}
    <div class="card"><b>Session complete.</b> <a href="/sessions/{{ sid }}">full trace &rarr;</a> · <a href="/tutor">start another</a></div>
    {% endif %}
  </div>

  <div id="glass">
    <div class="card"><b>Agent flow</b> <span class="mut" id="route-v">route v{{ route_version }}</span>
      <div id="flow"></div>
    </div>
    <div class="card"><b>Cited evidence</b><div id="evidence">
      {% for e in cited %}<div class="ev">{{ e.chunk_id }}: {{ e.text[:140] }}…</div>{% endfor %}
    </div></div>
    <div class="card"><b>Learner model</b><div id="learner">
      {% for c in learner %}<div>{{ c.name }} — m {{ c.mastery }} · c {{ c.confidence }}</div>{% endfor %}
    </div></div>
    <div class="card" id="why" style="{% if not rationale %}display:none{% endif %}"><b>Why this step</b>
      <div class="mut" id="why-text">{{ decision }} — {{ rationale }}</div></div>
    {% if induced %}<div class="card"><b>Induced (machine-derived)</b>
      {% for e in induced %}<div>{{ e.prereq }} &rarr; {{ e.target }} <span class="mut">conf {{ e.confidence }}</span></div>{% endfor %}</div>{% endif %}
    <div class="card costp"><b>Cost so far</b> <span id="cost">{{ cost.tokens }} tok ≈ ${{ cost.usd }}</span> <span class="mut">(offline = $0)</span></div>
  </div>
</div>

<script>
const SID = document.body.dataset.sid;
function setMode(m){document.body.className='mode-'+m;
  document.getElementById('t-chat').classList.toggle('on',m==='chat');
  document.getElementById('t-glass').classList.toggle('on',m==='glass');
  try{localStorage.setItem('litnav-mode',m)}catch(e){}}
const saved=(()=>{try{return localStorage.getItem('litnav-mode')}catch(e){return null}})();
if(saved)setMode(saved);

function typewriter(el,text){el.textContent='';let i=0;(function tick(){if(i<=text.length){el.textContent=text.slice(0,i++);setTimeout(tick,12)}})();}
const ft=document.getElementById('first-teach'); if(ft)typewriter(ft,ft.dataset.text);

function addBubble(cls,text,tw){const t=document.getElementById('thread');const d=document.createElement('div');d.className='bubble '+cls;t.appendChild(d);if(tw){typewriter(d,text)}else{d.textContent=text}return d;}
function setFlow(steps){const f=document.getElementById('flow');f.innerHTML='';steps.forEach(s=>{const d=document.createElement('div');d.className='step '+s.state;const ic=s.state==='done'?'✓':(s.state==='active'?'▶':'○');d.innerHTML='<span class="ic">'+ic+'</span><span>'+s.label+(s.detail?' <span class="mut">· '+s.detail+'</span>':'')+'</span>';f.appendChild(d)});}

function submitAnswer(ev){ev.preventDefault();const inp=document.getElementById('answer-input');const text=inp.value.trim();if(!text)return false;
  addBubble('me',text,false);inp.value='';inp.disabled=true;document.getElementById('working').style.display='block';
  const steps=[];const es=new EventSource('/tutor/'+SID+'/events?answer='+encodeURIComponent(text));
  es.onmessage=(m)=>{const e=JSON.parse(m.data);
    if(e.type==='step'){steps.forEach(s=>s.state='done');steps.push({label:e.label,detail:e.detail,state:'active'});setFlow(steps);}
    else if(e.type==='teach'){steps.forEach(s=>s.state='done');setFlow(steps);if(e.text)addBubble('ai',e.text,true);}
    else if(e.type==='question'){if(e.text)addBubble('ai qa',e.text,false);}
    else if(e.type==='state'){updateGlass(e);}
    else if(e.type==='done'){es.close();document.getElementById('working').style.display='none';
      if(e.done){location.href='/tutor/'+SID;}else{inp.disabled=false;inp.focus();}}
    else if(e.type==='error'){es.close();location.href='/tutor/'+SID;}
  };
  es.onerror=()=>{es.close();location.href='/tutor/'+SID;};
  return false;}

function updateGlass(e){document.getElementById('route-v').textContent='route v'+e.route_version;
  document.getElementById('evidence').innerHTML=(e.cited||[]).map(c=>'<div class="ev">'+c.chunk_id+': '+(c.text||'').slice(0,140)+'…</div>').join('');
  document.getElementById('learner').innerHTML=(e.learner||[]).map(c=>'<div>'+c.name+' — m '+c.mastery+' · c '+c.confidence+'</div>').join('');
  if(e.rationale){document.getElementById('why').style.display='';document.getElementById('why-text').textContent=(e.decision||'')+' — '+e.rationale;}
  if(e.cost){document.getElementById('cost').textContent=e.cost.tokens+' tok ≈ $'+e.cost.usd;}}
</script>
</body></html>
```

- [ ] **Step 2: Server passes `cited` + `cost` (already does via `**ts.current()` + `cost=`); confirm no template var is missing**

Run a quick render check (offline):
```bash
cd "<worktree>" && LITNAV_LLM_PROVIDER=none python -c "
import sqlite3, uuid, json
from litnav.storage.schema import init_db; from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import TutorSession
from litnav.ui.cost import session_cost
from jinja2 import Environment, FileSystemLoader, select_autoescape
c=sqlite3.connect(':memory:',check_same_thread=False); init_db(c); seed_demo_data(c,'data/seed/agents_m3.json')
ck=sqlite3.connect(':memory:',check_same_thread=False); ts=TutorSession(c,ck,str(uuid.uuid4()))
ts.start('agents', target_concept_ids=[1], mastery_threshold=0.75)
env=Environment(loader=FileSystemLoader('litnav/ui/templates'), autoescape=select_autoescape(['html']))
html=env.get_template('agent.html').render(sid='x', n_papers=25, cost=session_cost(c,ts.sid), **ts.current())
assert 'Agent flow' in html and 'Cited evidence' in html and 'type your answer' in html
print('render OK', len(html), 'chars')
"
```
Expected: `render OK ...` (no Jinja errors, no missing variables).

- [ ] **Step 3: Full suite + gates**

Run: `python -m pytest -q` and the four gates — all green (route tests still pass: the page server-renders content + the answer form; `/tutor/{sid}` unchanged on the server).

- [ ] **Step 4: Commit**

```bash
git add litnav/ui/templates/agent.html
git commit -m "feat(ui): two-view agent page (Chat + Glass box) with live SSE streaming"
```

---

## Task 6: Live verification via the preview

No code. Verify the real rendered experience and refine CSS/JS if the preview reveals issues
(overflow, broken animation). This is the gate for "feels like a real agent."

- [ ] **Step 1: Start the server via the preview tool** (launch config `litnav-panel` already exists; free port 8000 first if held).

- [ ] **Step 2: Screenshot `/tutor` (home)** — confirm clean.

- [ ] **Step 3: Start a goal session, screenshot Chat mode** — confirm the first teach typewriters, the answer box is present, no overflow.

- [ ] **Step 4: Toggle to Glass box, screenshot** — confirm the flow list, cited-only evidence (no `cx_` wall), learner bars, cost panel; no horizontal scroll.

- [ ] **Step 5: Submit a wrong answer; screenshot Glass box mid/after** — confirm the flow lights up step-by-step (grade → reteach → teach → check) and the glass box updates (mastery, decision rationale, cost). Toggle to Chat — confirm the reteach bubble typewritered in.

- [ ] **Step 6: Resize to mobile width, screenshot** — confirm the glass box stacks under chat, nothing clipped.

- [ ] **Step 7: If issues found**, edit `agent.html` (CSS/JS only), reload, re-verify. Commit any fixes:
```bash
git add litnav/ui/templates/agent.html
git commit -m "fix(ui): polish two-view layout from live preview"
```

---

## Final verification
- [ ] `python -m pytest -q` → all green (≈ 86 + new tests).
- [ ] `verify_m0..m3` → all PASS offline.
- [ ] Preview: Chat typewriter + Glass-box live flow both confirmed on an answer turn; evidence shows only the cited chunk; no overflow.
- [ ] When the user approves publishing: push + ff local main + verify three refs.
