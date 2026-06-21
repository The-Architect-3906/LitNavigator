# Frontend: Live Open-World + Artifact Download — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the web UI (a) run the *real* open-world pipeline (find-sources → digest → teach any goal) when a live LLM key is present, with streamed build progress, and (b) generate a take-away artifact at session end that the user can download from the page.

**Architecture:** `_start_agent` decides mode by provider. Offline (`provider=none`) keeps today's curated agent-papers pack (instant, $0). Live (`provider!=none` + a typed goal) creates a session in a "building" state; the page auto-opens the SSE stream on load, which runs discover→digest (coarse streamed stages), builds the per-session concept graph, then teaches from it — reusing the proven `TutorSession`. At session end, `make_artifact` runs once and an `artifact` SSE event surfaces a Download button backed by a new `GET /tutor/{sid}/artifact` endpoint. The curated path is untouched except for the shared artifact step.

**Tech Stack:** FastAPI + Jinja2 + SSE (fetch+ReadableStream), LangGraph `TutorSession`, `litnav.discover.find_sources`, `litnav.digest.pipeline`, `litnav.artifact.make_artifact`, SQLite per-session DB.

**Reference implementation (proven):** `litnav/evaluation/inner_loop_scenarios.py::_digest_topic` + `_run_live_one` is the canonical discover→digest→`tids`→teach→artifact sequence. Mirror it.

---

## Locked design decisions
1. **Mode = provider.** `live = os.getenv("LITNAV_LLM_PROVIDER","none") != "none"`. Live + a typed goal (no `intent`) → open-world. Otherwise → curated pack (unchanged).
2. **Open-world session does NOT seed the fixture.** It builds its own graph into the per-session DB. `self.concepts` is repopulated from the DB after digest (so dispatch on answer/aside still works).
3. **Coarse streamed stages**, not a pipeline refactor: `discover` → `discover_done` → `digest` → `map` → teach.
4. **No sources found → honest boundary reply**, not a crash, not a silent fixture fallback.
5. **Artifact at end of every completed session** (both modes), generated exactly once (guard flag). Markdown download now; slides→PPTX deferred.
6. **No key is ever embedded.** Live mode requires the user's own `.env`. Offline stays the $0 default.

## File structure
- Modify `litnav/ui/interactive.py` — `TutorSession.start(goal_text=...)`; new artifact step in `_terminal_events`; `AgentSession` open-world build generator + building snapshot.
- Modify `litnav/ui/server.py` — `_start_agent` mode branch; `GET /tutor/{sid}/artifact` download route.
- Modify `litnav/ui/flow_meta.py` — meta for the synthetic build steps (optional; reuse find-sources/digest meta).
- Modify `litnav/ui/templates/agent.html` — building state + auto-stream on load; `build` + `artifact` event handling; Download button.
- Test: `tests/test_ui_openworld.py` (new), `tests/test_ui_artifact.py` (new).
- Docs (final task): `docs/FRONTEND-COMPLETE.md`, `docs/FRONTEND-ROADMAP.md`, `README.md`.

---

## Task 1: `TutorSession.start` forwards `goal_text` (depth elicitation)

**Files:** Modify `litnav/ui/interactive.py:35-44`; Test `tests/test_ui_openworld.py`

- [ ] **Step 1 — failing test**
```python
# tests/test_ui_openworld.py
import sqlite3
from litnav.storage.schema import init_db
from litnav.storage import repo
from litnav.digest import pipeline
from litnav.digest.contract import DigestInput, SourceDoc
from litnav.ui.interactive import TutorSession

def _seed_min_graph(conn):
    # Reuse the offline digest fixture to get a tiny real graph deterministically ($0).
    import json, os
    from pathlib import Path
    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    fix = json.loads(Path("data/seed/digest_sources_fixture.json").read_text(encoding="utf-8"))
    di = DigestInput(fix["domain_key"],
                     [SourceDoc(s["source_type"], s["source_id"], s["title"], s.get("url"), s["chunks"])
                      for s in fix["sources"]], fix.get("target_slugs", []))
    pipeline.digest(di, conn=conn, candidate=fix["candidate"], session_id="t")
    return fix["domain_key"]

def test_start_accepts_goal_text():
    conn = sqlite3.connect(":memory:"); init_db(conn)
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    topic = _seed_min_graph(conn); repo.create_session(conn, "s1", topic=topic)
    tids = [r[0] for r in conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:2]
    ts = TutorSession(conn, ck, "s1")
    snap = ts.start(topic, target_concept_ids=tids, goal_text="quick overview", mastery_threshold=0.75)
    assert snap["route"]  # planned a route over the built graph
```

- [ ] **Step 2 — run, expect FAIL** (`TypeError: start() got an unexpected keyword 'goal_text'`)
Run: `python -m pytest tests/test_ui_openworld.py::test_start_accepts_goal_text -q`

- [ ] **Step 3 — implement.** In `litnav/ui/interactive.py`, add `goal_text` to `TutorSession.start` and forward it:
```python
    def start(self, topic: str, target_concept_ids: Optional[List[int]] = None,
              intent: Optional[str] = None, pending_induction: Optional[dict] = None,
              mastery_threshold: float = 0.8, goal_text: Optional[str] = None) -> dict:
        state = make_initial_state(
            self.sid, topic, target_concept_ids or [],
            intent=intent, pending_induction=pending_induction,
            mastery_threshold=mastery_threshold, goal_text=goal_text,
        )
        self.app.invoke(state, self.config)
        return self.current()
```

- [ ] **Step 4 — run, expect PASS.**
- [ ] **Step 5 — commit** `feat(ui): TutorSession.start forwards goal_text for depth elicitation`

---

## Task 2: Artifact generated once at session end + `artifact` terminal event

**Files:** Modify `litnav/ui/interactive.py` (`TutorSession.__init__`, `_terminal_events`); Test `tests/test_ui_artifact.py`

- [ ] **Step 1 — failing test** (offline, $0 — curated path produces a downloadable artifact)
```python
# tests/test_ui_artifact.py
import os, sqlite3
from pathlib import Path
os.environ["LITNAV_LLM_PROVIDER"] = "none"
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession
import json

def _run_to_done(tmp_path):
    conn = sqlite3.connect(":memory:"); init_db(conn)
    seed_demo_data(conn, "data/seed/agents_expanded.json")
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    data = json.loads(Path("data/seed/agents_expanded.json").read_text(encoding="utf-8"))
    ag = AgentSession(conn, ck, "sa", data, out_dir=str(tmp_path))
    slug = data["concepts"][0]["slug"]
    list(ag._start_teaching(slug))
    # answer correctly until done
    for _ in range(40):
        cur = ag._cur()
        if cur.get("done"): break
        q = cur.get("question")
        if not q: break
        key = (cur.get("answer_key") or "the key idea")
        list(ag.handle(key))
    return ag

def test_artifact_event_and_file(tmp_path):
    ag = _run_to_done(tmp_path)
    evs = ag.tutor._terminal_events()
    art = [e for e in evs if e.get("type") == "artifact"]
    assert art, "expected an artifact event at session end"
    assert art[0]["url"] == "/tutor/sa/artifact"
    assert Path(ag.tutor.artifact_path).exists()
```

- [ ] **Step 2 — run, expect FAIL** (no `artifact` event; `AgentSession()` has no `out_dir`).
Run: `python -m pytest tests/test_ui_artifact.py -q`

- [ ] **Step 3 — implement.**
In `TutorSession.__init__` add `out_dir: str = "artifacts"` param; store `self.out_dir`, `self.artifact_path=None`, `self._artifact_made=False`.
Add a helper and call it from `_terminal_events` when done:
```python
    def _artifact_event(self):
        """Generate the take-away once when the route is complete; return an event or None."""
        cur = self.current()
        if not cur.get("done") or self._artifact_made:
            return None
        tids = [st["concept_id"] for st in cur["route"] if st.get("concept_id") is not None]
        if not tids:
            return None
        from litnav.artifact.contract import ArtifactInput
        from litnav.artifact.make_artifact import make_artifact
        from litnav.llm import lang as lang_mod
        teach_blob = " ".join(cur.get("teach_messages") or []) or "x"
        language = lang_mod.detect_language(teach_blob)
        out = f"{self.out_dir}/{self.sid}"
        try:
            res = make_artifact(ArtifactInput(tids, {}, language=language),
                                conn=self.conn, session_id=self.sid, out_dir=out)
        except Exception:
            return None
        self._artifact_made = True
        self.artifact_path = res.artifact_path
        body = ""
        try:
            from pathlib import Path as _P
            body = _P(res.artifact_path).read_text(encoding="utf-8")
        except Exception:
            pass
        return {"type": "artifact", "format": res.format, "url": f"/tutor/{self.sid}/artifact",
                "citations": res.citations, "preview": body[:600]}
```
In `_terminal_events`, before the final `done` event, append the artifact event if present:
```python
        art = self._artifact_event()
        if art:
            events.append(art)
```
(Place it after the `state` event and before `done` so the UI can render the card then unlock.)
Thread `out_dir` from `AgentSession`: add `out_dir="artifacts"` to `AgentSession.__init__`, store it, and pass `out_dir=self.out_dir` when constructing `TutorSession` in `_start_teaching` and (Task 4) the open-world builder.

- [ ] **Step 4 — run, expect PASS.**
- [ ] **Step 5 — commit** `feat(ui): generate take-away artifact at session end + artifact event`

---

## Task 3: `GET /tutor/{sid}/artifact` download endpoint

**Files:** Modify `litnav/ui/server.py`; Test `tests/test_ui_artifact.py`

- [ ] **Step 1 — failing test** (TestClient)
```python
def test_artifact_download_route(tmp_path, monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from fastapi.testclient import TestClient
    from litnav.ui import server
    monkeypatch.setattr(server, "_ARTIFACT_DIR", str(tmp_path))  # see Step 3
    c = TestClient(server.app)
    sid = c.get("/tutor/start", params={"goal": "ReAct"}, follow_redirects=False).headers["location"].split("/tutor/")[1]
    # drive to done
    for _ in range(40):
        r = c.post(f"/tutor/{sid}/events", json={"answer": "the key idea"})
        if '"type": "done"' in r.text and '"done": true' in r.text:
            break
    resp = c.get(f"/tutor/{sid}/artifact")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
```

- [ ] **Step 2 — run, expect FAIL** (404 — no route).

- [ ] **Step 3 — implement.** In `server.py`: add a module-level `_ARTIFACT_DIR = "artifacts"`, pass it into `AgentSession(..., out_dir=_ARTIFACT_DIR)` in `_start_agent`, and add:
```python
from fastapi.responses import FileResponse
from pathlib import Path as _Path

@app.get("/tutor/{sid}/artifact")
def tutor_artifact(sid: str):
    ag = _AGENTS.get(sid)
    path = getattr(getattr(ag, "tutor", None), "artifact_path", None) if ag else None
    if not path or not _Path(path).exists():
        return JSONResponse({"error": "no artifact yet"}, status_code=404)
    fname = f"litnavigator-{sid[:8]}-{_Path(path).stem}.md"
    return FileResponse(path, media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
```

- [ ] **Step 4 — run, expect PASS.**
- [ ] **Step 5 — commit** `feat(ui): artifact download endpoint`

---

## Task 4: Open-world build generator in `AgentSession` + building snapshot

**Files:** Modify `litnav/ui/interactive.py` (`AgentSession`); Test `tests/test_ui_openworld.py`

- [ ] **Step 1 — failing test** (monkeypatch discover+digest so it's offline/$0/deterministic)
```python
def test_open_world_build_streams_and_teaches(monkeypatch, tmp_path):
    import sqlite3, json
    from pathlib import Path
    from litnav.storage.schema import init_db
    from litnav.storage import repo
    from litnav.ui import interactive
    from litnav.digest import pipeline
    from litnav.digest.contract import DigestInput, SourceDoc

    os.environ["LITNAV_LLM_PROVIDER"] = "none"
    fix = json.loads(Path("data/seed/digest_sources_fixture.json").read_text(encoding="utf-8"))
    src = fix["sources"][0]

    class _S:  # stand-in for a discovered source
        source_type, source_id, title, url = src["source_type"], src["source_id"], src["title"], src.get("url")
        chunks = src["chunks"]
    class _Res: sources = [_S()]
    monkeypatch.setattr(interactive.find_sources, "find", lambda *a, **k: _Res())
    def _fake_digest(di, *, conn, candidate, session_id, budget=0):
        return pipeline.digest(DigestInput(fix["domain_key"],
            [SourceDoc(src["source_type"], src["source_id"], src["title"], src.get("url"), src["chunks"])],
            target_slugs=[]), conn=conn, candidate=fix["candidate"], session_id=session_id)
    monkeypatch.setattr(interactive.pipeline, "digest", _fake_digest)

    conn = sqlite3.connect(":memory:"); init_db(conn); repo.create_session(conn, "ow1", topic="g")
    ck = sqlite3.connect(":memory:", check_same_thread=False)
    ag = interactive.AgentSession(conn, ck, "ow1", fixture_data=None,
                                  open_world_goal="explain X", live=True, out_dir=str(tmp_path))
    assert ag.current().get("building") is True
    evs = list(ag.current_events())
    stages = [e["stage"] for e in evs if e.get("type") == "build"]
    assert "discover" in stages and "digest" in stages and "map" in stages
    assert any(e.get("type") in ("teach", "question") for e in evs)
    assert ag.built is True
```

- [ ] **Step 2 — run, expect FAIL.**

- [ ] **Step 3 — implement.** Add imports at top of `interactive.py`:
```python
from litnav.discover import find_sources
from litnav.discover.contract import DiscoverInput
from litnav.digest import pipeline
from litnav.digest.contract import DigestInput, SourceDoc
```
Extend `AgentSession.__init__` signature and state:
```python
    def __init__(self, domain_conn, checkpoint_conn, session_id, fixture_data=None,
                 *, open_world_goal=None, live=False, out_dir="artifacts"):
        self.conn = domain_conn; self.ckpt = checkpoint_conn; self.sid = session_id
        self.out_dir = out_dir
        self.open_world = bool(open_world_goal and live)
        self.goal = open_world_goal or ""
        self.built = False
        self.tutor = None
        if fixture_data:
            self.data = fixture_data
            self.concepts = fixture_data["concepts"]
            self.off = fixture_data["induction"]["off_skeleton"]
            self.topic = fixture_data.get("topic", "agents")
        else:
            self.data = None; self.concepts = []; self.off = None; self.topic = self.goal or "agents"
```
Building snapshot in `current()`:
```python
    def current(self):
        if self.open_world and not self.built:
            from litnav.ui.trace import concept_graph
            return {"done": False, "building": True, "goal": self.goal, "concept_name": None,
                    "teach": None, "teach_messages": [], "question": None, "route": [],
                    "route_version": 1, "learner": [], "cited": [], "evidence": [],
                    "decision": None, "rationale": None, "induced": [], "intent": None,
                    "mastery": None, "confidence": None,
                    "graph": to_svg(concept_graph(self.conn, None))}
        if self.tutor:
            return self.tutor.current()
        return { ...existing conversing snapshot... }   # unchanged
```
Route `current_events()` to the builder:
```python
    def current_events(self):
        if self.open_world and not self.built:
            return self._build_open_world()
        if self.tutor:
            return self.tutor._terminal_events()
        return [{"type": "reply", "text": "Hi! Tell me what you'd like to learn from the agent papers."},
                {"type": "done", "done": False}]
```
Add the builder generator:
```python
    _BUDGET = 120000
    def _build_open_world(self):
        from litnav.ui.trace import concept_graph
        yield {"type": "build", "stage": "discover", "label": f"Finding real sources for: {self.goal}",
               "skill": "find-sources", "method": "BM25 + embedding rerank + relevance gate", "paper": "Robertson; Cohan 2020"}
        try:
            res = find_sources.find(DiscoverInput(self.goal, k=6), conn=self.conn, session_id=self.sid, budget=self._BUDGET)
        except Exception as e:
            yield {"type": "reply", "kind": "boundary", "text": f"Source search failed: {e}"}
            yield {"type": "done", "done": False}; return
        withft = [s for s in res.sources if s.chunks and sum(len(x) for x in s.chunks) > 200]
        if not withft:
            yield {"type": "reply", "kind": "boundary",
                   "text": f"I couldn't find an open, full-text source for “{self.goal}”. Try rephrasing or a more specific topic."}
            yield {"type": "done", "done": False}; return
        top = withft[0]
        yield {"type": "build", "stage": "discover_done", "label": f"Source: {top.title[:80]}"}
        yield {"type": "build", "stage": "digest", "label": "Reading it and building your concept map…",
               "skill": "digest-corpus", "method": "concept extraction + RefD prereqs + gpt-4o verify", "paper": "Liang 2015"}
        di = DigestInput(self.goal, [SourceDoc(top.source_type, top.source_id, top.title, top.url, top.chunks)], target_slugs=[])
        pipeline.digest(di, conn=self.conn, candidate={"concepts": [], "keypoints": [], "prereq_edges": [],
                        "similarity_edges": [], "quiz_seeds": [], "judge_labels": {}},
                        session_id=self.sid, budget=self._BUDGET)
        tids = [r[0] for r in self.conn.execute("SELECT id FROM concepts ORDER BY id").fetchall()][:4]
        if not tids:
            yield {"type": "reply", "kind": "boundary", "text": "I read the source but couldn't extract teachable concepts. Try another topic."}
            yield {"type": "done", "done": False}; return
        # repopulate concepts so dispatch works during teaching
        self.concepts = [{"id": r[0], "slug": r[1], "name": r[2]} for r in
                         self.conn.execute("SELECT id, slug, name FROM concepts ORDER BY id").fetchall()]
        yield {"type": "build", "stage": "map", "label": f"Concept map ready — {len(tids)} concepts",
               "graph": to_svg(concept_graph(self.conn, self.sid))}
        self.tutor = TutorSession(self.conn, self.ckpt, self.sid, out_dir=self.out_dir)
        self.tutor.start(self.goal, target_concept_ids=tids, goal_text=self.goal, mastery_threshold=0.75)
        self.built = True
        for ev in self.tutor._terminal_events():
            yield ev
```
Also: in `handle()`, when `self.open_world and not self.built`, treat any message as the (already-known) goal and run the builder: at the top of `handle`, add
```python
        if self.open_world and not self.built:
            yield from self._build_open_world(); return
```

- [ ] **Step 4 — run, expect PASS.**
- [ ] **Step 5 — commit** `feat(ui): open-world cold-start build generator (discover→digest→teach) with streamed stages`

---

## Task 5: `_start_agent` mode branch (server)

**Files:** Modify `litnav/ui/server.py:153-172`; Test `tests/test_ui_openworld.py`

- [ ] **Step 1 — failing test**
```python
def test_start_agent_open_world_when_live(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "openai")
    from litnav.ui import server
    # don't actually discover/digest — just assert the session is in building mode
    sid = server._start_agent("teach me about quantum error correction", None)
    ag = server._AGENTS[sid]
    assert ag.open_world is True and ag.built is False
    assert ag.current().get("building") is True

def test_start_agent_curated_when_offline(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    from litnav.ui import server
    sid = server._start_agent("ReAct", None)
    assert server._AGENTS[sid].open_world is False
```

- [ ] **Step 2 — run, expect FAIL.**

- [ ] **Step 3 — implement.** Rewrite `_start_agent`:
```python
def _start_agent(goal: str, intent: str | None) -> str:
    sid = str(uuid.uuid4())
    base = Path(DEMO_DB_PATH).parent; base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / f"tutor-{sid}.sqlite"), check_same_thread=False)
    init_db(conn)
    ckpt = sqlite3.connect(str(base / f"tutor-{sid}-ckpt.sqlite"), check_same_thread=False)
    live = os.getenv("LITNAV_LLM_PROVIDER", "none") != "none"
    if live and goal.strip() and not intent:
        # Open-world: build this learner's own graph from real sources (streamed on first /events).
        ag = AgentSession(conn, ckpt, sid, fixture_data=None,
                          open_world_goal=goal.strip(), live=True, out_dir=_ARTIFACT_DIR)
        _AGENTS[sid] = ag
        repo.create_session(conn, sid, topic=goal.strip())
        return sid
    # Curated offline pack (unchanged behavior)
    seed_demo_data(conn, _TUTOR_FIXTURE)
    ag = AgentSession(conn, ckpt, sid, _fixture_data(), out_dir=_ARTIFACT_DIR)
    _AGENTS[sid] = ag
    if intent:
        ag.tutor = TutorSession(conn, ckpt, sid, out_dir=_ARTIFACT_DIR)
        ag.tutor.start(ag.topic, target_concept_ids=[], intent=intent, mastery_threshold=0.75)
    else:
        plan = resolve_goal(goal, ag.concepts, ag.off)
        if plan["kind"] in ("concept", "induce"):
            list(ag._start_teaching(plan["slug"]))
    return sid
```
Add `from litnav.storage import repo` and `import os` if not present (os is already imported).

- [ ] **Step 4 — run, expect PASS** (and `python -m pytest tests/test_ui_openworld.py tests/test_ui_artifact.py -q`).
- [ ] **Step 5 — commit** `feat(ui): route to open-world build when a live provider + goal is set`

---

## Task 6: Template — building state, auto-stream on load, `build`/`artifact` events, Download button

**Files:** Modify `litnav/ui/templates/agent.html`

- [ ] **Step 1 — refactor the SSE reader out of `submitAnswer`** into a reusable function:
```javascript
async function streamEvents(body){
  document.getElementById('working').style.display='block';
  const inp=document.getElementById('answer-input');
  const steps=[];
  try{
    const resp=await fetch('/tutor/'+SID+'/events',
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf='';
    while(true){const r=await reader.read(); if(r.done)break;
      buf+=dec.decode(r.value,{stream:true}); let i;
      while((i=buf.indexOf('\n\n'))>=0){const block=buf.slice(0,i); buf=buf.slice(i+2);
        const dl=block.split('\n').find(l=>l.startsWith('data:'));
        if(dl)handleEvent(JSON.parse(dl.slice(5).trim()),steps,inp);}}
  }catch(err){location.href='/tutor/'+SID;}
}
async function submitAnswer(ev){
  ev.preventDefault();
  const inp=document.getElementById('answer-input'); const text=inp.value.trim();
  if(!text)return false; addBubble('me',text,false); inp.value=''; inp.disabled=true;
  await streamEvents({answer:text}); return false;
}
```

- [ ] **Step 2 — handle `build` and `artifact` events** in `handleEvent`:
```javascript
  } else if(e.type==='build'){
    steps.forEach(s=>s.state='done');
    steps.push({label:e.label,detail:'',state:'active',skill:e.skill,method:e.method,paper:e.paper});
    setFlow(steps);
    if(e.stage==='discover')addBubble('ai','🔎 '+e.label,false);
    if(e.stage==='map'){addBubble('ai','🗺️ '+e.label,false);
      if(e.graph){const g=document.getElementById('concept-map'); if(g)g.innerHTML=e.graph;}}
  } else if(e.type==='artifact'){
    renderArtifact(e);
```
Add the renderer (a card with a Download button + preview):
```javascript
function renderArtifact(e){
  const host=document.getElementById('artifact-card');
  if(!host)return;
  host.style.display='';
  host.innerHTML='<div class="art-h">📄 Take-away ('+esc(e.format)+')</div>'
    +'<a class="art-dl" href="'+e.url+'" download>Download .md</a>'
    +'<pre class="art-pre">'+esc((e.preview||'').slice(0,500))+'…</pre>';
}
```

- [ ] **Step 3 — building state + auto-stream on load.** In the template body, where the chat renders, add (Jinja):
```html
{% if building %}
  <div id="artifact-card" class="art-card" style="display:none"></div>
  <script>window.__BUILDING__=true;</script>
{% else %}
  <div id="artifact-card" class="art-card" style="display:none"></div>
{% endif %}
```
At the end of the script, kick the build stream on load:
```javascript
if(window.__BUILDING__){addBubble('ai','Building your course from real sources… this can take ~30–90s.',false);
  streamEvents({});}
```
Add minimal CSS for `.art-card/.art-h/.art-dl/.art-pre` consistent with existing styles (small bordered card, button-styled link). Ensure `#concept-map` is the id of the glass-box SVG container (rename in template if it differs).

- [ ] **Step 4 — browser verification** (offline first, then live): see Task 7.
- [ ] **Step 5 — commit** `feat(ui): building state + streamed build stages + artifact download card`

---

## Task 7: Verification (offline tests, live smoke, browser)

- [ ] **Step 1 — full offline suite green:** `python -m pytest -q` (expect prior 353 + new tests pass).
- [ ] **Step 2 — browser, offline ($0):** `preview_start` the server (provider=none); start a curated session, answer to completion, confirm the **artifact card + Download** appears and the file downloads. Screenshot.
- [ ] **Step 3 — browser, live (key from local `.env`, metered):** set `LITNAV_LLM_PROVIDER=openai`; submit a fresh goal NOT in the agent pack (e.g. "explain quantum error correction"); confirm streamed stages (Finding sources → map ready), real teaching from the discovered source, and a downloadable artifact. Record live cost from the meter (expect ~$0.02). Do this once; do not commit any key.
- [ ] **Step 4 — no-source path:** submit a deliberately empty/garbage goal live; confirm the honest boundary reply (no crash).

---

## Task 8: Docs (per the request)

- [ ] **`docs/FRONTEND-COMPLETE.md`:** replace the two overclaiming lines — now true: live mode runs real discover→digest→teach (streamed build stages); artifacts generate at session end and download via `GET /tutor/{sid}/artifact`. Add the build-stage flow and the Download button to the feature list; add `/tutor/{sid}/artifact` to the routes table.
- [ ] **`docs/FRONTEND-ROADMAP.md`:** move "stream cold-start digest" and "artifact download" out of pending into done; keep slides→PPTX (marp) and incremental partial-graph preview as remaining.
- [ ] **`README.md`:** note the UI now does live open-world (with a key) + artifact download; the v0.1.0/exe description already covers offline-vs-live.
- [ ] **Commit + PR to main** (consistent with prior doc syncs), then update the release notes if the UI capability statement changed.

---

## Self-review checklist
- Offline curated path unchanged except the shared (guarded) artifact step. ✓
- Open-world path mirrors the proven harness sequence (`find_sources.find` → `pipeline.digest` → `tids` → `TutorSession`). ✓
- No key embedded; live gated by env. ✓
- Artifact generated exactly once (`_artifact_made`), download endpoint reads `tutor.artifact_path`. ✓
- New tests are offline/$0/deterministic (monkeypatched discover/digest; real make_artifact on the fixture). ✓
