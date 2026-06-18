# Conversational Agent Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the unchanged teaching graph in an LLM conversation layer so `/tutor` is a full chat agent (chat / set_goal / answer / aside / out_of_scope) that still only *teaches* from cited evidence.

**Architecture:** A `dispatch()` classifier (LLM + deterministic fallback) decides each turn's action. A new `AgentSession` holds the chat transcript and lazily creates a `TutorSession` (the existing graph) when teaching starts. The teaching graph and `TutorSession` are NOT modified. Offline (`provider=none`) the dispatcher degrades to today's behavior, so gates/tests stay green.

**Tech Stack:** Python 3.11, FastAPI + Jinja2, LangGraph (unchanged), vanilla JS, pytest.

**Spec:** `docs/2026-06-18-conversational-agent-design.md`

**Baseline:** commit `897b906`, 91 tests + G0–G3 green offline.

**Conventions:** Work in the worktree `C:/Users/Architect117/LitNavigator/.claude/worktrees/eloquent-khorana-8c9ed9` (prefix shell commands with `cd "<worktree>" &&`; confirm `git rev-parse --show-toplevel` ends with `eloquent-khorana-8c9ed9` before committing). After each task: `python -m pytest -q` + the four gates green offline (`LITNAV_LLM_PROVIDER=none`). Commit per task; do not push. Co-Authored-By trailer on every commit:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `litnav/conversation.py` (new) | `dispatch(message, …)` → `{action, slug, reply}` (LLM + offline fallback) | 1 |
| `tests/test_conversation.py` (new) | dispatch offline parity + mocked-LLM actions | 1 |
| `litnav/ui/interactive.py` (modify) | new `AgentSession` wrapping `TutorSession`; `handle(message)` event stream | 2 |
| `tests/test_agent_session.py` (new) | greeting→reply, goal→teach, answer→grade, aside→reply+re-pose | 2 |
| `litnav/ui/server.py` (modify) | `_AGENTS` registry; `/tutor/start` makes an `AgentSession`; `/tutor/{sid}/events` → `handle` | 3 |
| `tests/test_tutor_routes.py` (modify) | events drives a conversational turn | 3 |
| `litnav/ui/templates/agent.html` (modify) | multi-turn chat; render `reply`/`dispatch` events | 4 |
| (preview verification) | live: "你好" → greeting; goal → teach; mid-quiz aside → answer + re-pose | 5 |

---

## Task 1: The dispatcher

**Files:**
- Create: `litnav/conversation.py`
- Test: `tests/test_conversation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conversation.py
import json
from litnav.conversation import dispatch

_DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))
CONCEPTS = _DATA["concepts"]
OFF = _DATA["induction"]["off_skeleton"]


def _ctx(quiz_pending=False, question=None):
    return dict(concepts=CONCEPTS, off=OFF, quiz_pending=quiz_pending, question=question)


def test_offline_quiz_pending_is_answer(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("the agent takes actions and observations", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "answer"


def test_offline_goal_is_set_goal(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("I want to understand ReAct", **_ctx())
    assert d["action"] == "set_goal" and d["slug"] == "react"


def test_offline_greeting_is_out_of_scope_with_guidance(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    d = dispatch("你好", **_ctx())
    assert d["action"] == "out_of_scope"
    assert "ReAct" in d["reply"]   # names what it can teach


def test_llm_chat_action(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "chat", "slug": None, "reply": "Hi! What do you want to learn?"})
    d = dispatch("hello there", **_ctx())
    assert d["action"] == "chat" and "learn" in d["reply"]


def test_llm_aside_keeps_quiz(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "aside", "slug": "tool_use", "reply": ""})
    d = dispatch("wait, what is a tool?", **_ctx(quiz_pending=True, question="Q?"))
    assert d["action"] == "aside" and d["slug"] == "tool_use"


def test_hallucinated_slug_rejected(monkeypatch):
    from litnav import conversation as conv
    monkeypatch.setattr(conv.llm_client, "complete_json",
                        lambda *a, **k: {"action": "set_goal", "slug": "made_up", "reply": ""})
    d = dispatch("teach me made up thing", **_ctx())
    # invalid slug + set_goal with no quiz -> falls back to resolve_goal -> out_of_scope
    assert d["action"] == "out_of_scope"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_conversation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'litnav.conversation'`.

- [ ] **Step 3: Implement `litnav/conversation.py`**

```python
"""Conversation dispatcher — classify each user message into one tutor action.

LLM-backed when a provider is set; deterministic fallback offline (= today's behavior:
quiz pending -> answer; else resolve_goal). The reply text is only ever a greeting, a short
guiding sentence, or an honest decline — never domain teaching (that goes through the
grounded teaching graph). Any LLM-proposed slug is validated against the known concept set.
"""
from __future__ import annotations

from litnav.goal import resolve_goal
from litnav.llm import client as llm_client

ACTIONS = {"chat", "set_goal", "answer", "aside", "out_of_scope"}


def _fallback(message: str, concepts: list[dict], off: dict | None, quiz_pending: bool) -> dict:
    if quiz_pending:
        return {"action": "answer", "slug": None, "reply": ""}
    r = resolve_goal(message, concepts, off)
    if r["kind"] in ("concept", "induce"):
        return {"action": "set_goal", "slug": r["slug"], "reply": ""}
    names = ", ".join(c["name"] for c in concepts)
    return {"action": "out_of_scope", "slug": None,
            "reply": f"I can teach: {names}. What would you like to start with?"}


def dispatch(message: str, *, concepts: list[dict], off: dict | None,
             quiz_pending: bool, question: str | None = None) -> dict:
    """Return {action, slug, reply}. action ∈ ACTIONS; slug is a validated known slug or None."""
    fb = _fallback(message, concepts, off, quiz_pending)
    valid_slugs = {c["slug"] for c in concepts} | ({off["slug"]} if off else set())

    q = f'A quiz is pending: "{question}".' if quiz_pending else "No quiz is pending."
    prompt = (
        "You are the dispatcher for a tutor built ONLY from a fixed pack of LLM-agent papers.\n"
        f"Teachable concepts (slug: name): {[(c['slug'], c['name']) for c in concepts]}\n"
        f"Off-skeleton concept that can be INDUCED on request: {off['slug'] if off else None}\n"
        f"{q}\nUser message: {message!r}\n\n"
        "Choose ONE action:\n"
        "- answer: only if a quiz is pending AND the message is an attempt to answer it.\n"
        "- aside: a quiz is pending but the message is a side question/comment, not an answer; "
        "set slug to the concept it asks about if any.\n"
        "- set_goal: no quiz pending and the user wants to learn a listed/off-skeleton concept; set slug.\n"
        "- chat: a greeting, small talk, or a question about you/your capabilities.\n"
        "- out_of_scope: the user wants to learn something NOT in the concept list.\n"
        "HARD RULE: never put teaching or domain facts in 'reply'. 'reply' is only a greeting, "
        "a short guiding sentence, or an honest decline naming what you can teach. To teach, use set_goal.\n"
        'Respond as JSON: {"action": "<one of the five>", "slug": "<known slug or null>", "reply": "<short text or empty>"}'
    )
    res = llm_client.complete_json(prompt, fallback=fb)

    action = res.get("action")
    if action not in ACTIONS:
        return fb
    slug = res.get("slug")
    if slug not in valid_slugs:
        slug = None
    if action == "answer" and not quiz_pending:
        action = "chat"
    if action == "set_goal" and slug is None:
        return fb                      # can't teach an unknown target -> deterministic route
    reply = res.get("reply") or fb.get("reply") or ""
    return {"action": action, "slug": slug, "reply": reply}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_conversation.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add litnav/conversation.py tests/test_conversation.py
git commit -m "feat(conversation): LLM dispatcher (chat/set_goal/answer/aside/out_of_scope) with offline fallback"
```

---

## Task 2: AgentSession

Wraps a lazily-created `TutorSession`. `handle(message)` runs the dispatcher and yields UI
events. The teaching graph and `TutorSession` are untouched; teaching turns reuse the
existing `_terminal_events()` / `stream_answer()`.

**Files:**
- Modify: `litnav/ui/interactive.py` (add `AgentSession`; add a small grounded-aside helper)
- Test: `tests/test_agent_session.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_agent_session.py
import json, sqlite3, uuid
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession

DATA = json.load(open("data/seed/agents_m3.json", encoding="utf-8"))


def _agent():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(conn); seed_demo_data(conn, "data/seed/agents_m3.json")
    ckpt = sqlite3.connect(":memory:", check_same_thread=False)
    return AgentSession(conn, ckpt, str(uuid.uuid4()), DATA)


def _types(events):
    return [e["type"] for e in events]


def test_greeting_replies_without_teaching(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    evs = list(a.handle("你好"))
    assert "reply" in _types(evs)              # a conversational reply
    assert "teach" not in _types(evs)          # nothing taught
    assert a.tutor is None                     # no teaching session created


def test_goal_starts_grounded_teaching(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    evs = list(a.handle("I want to understand ReAct"))
    assert "teach" in _types(evs) and "question" in _types(evs)
    assert a.tutor is not None


def test_answer_grades_after_goal(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))
    evs = list(a.handle("the agent takes actions and observations"))
    assert "state" in _types(evs) and _types(evs)[-1] == "done"


def test_aside_answers_then_reposes_quiz(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    a = _agent()
    list(a.handle("I want to understand ReAct"))   # quiz now pending
    from litnav.ui import interactive as I
    monkeypatch.setattr(I, "dispatch",
                        lambda *args, **kw: {"action": "aside", "slug": "react", "reply": ""})
    evs = list(a.handle("wait, what does ReAct stand for?"))
    t = _types(evs)
    assert "reply" in t                # a brief grounded aside answer
    assert "question" in t             # the quiz is re-posed
    # and the learner can still answer it
    evs2 = list(a.handle("the agent takes actions and observations"))
    assert _types(evs2)[-1] == "done"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_agent_session.py -q`
Expected: FAIL with `ImportError: cannot import name 'AgentSession'`.

- [ ] **Step 3: Implement `AgentSession` in `litnav/ui/interactive.py`**

Add `from litnav.conversation import dispatch` and `from litnav.nodes.retrieve import retrieve_node`
to the imports, then append this class at the end of the file:

```python
class AgentSession:
    """Conversation layer over the teaching graph. Holds the transcript and a lazily-created
    TutorSession; handle(message) dispatches each turn and yields UI events. The teaching
    graph is never modified — set_goal/answer go through TutorSession unchanged."""

    def __init__(self, domain_conn, checkpoint_conn, session_id: str, fixture_data: dict):
        self.conn = domain_conn
        self.ckpt = checkpoint_conn
        self.sid = session_id
        self.data = fixture_data
        self.concepts = fixture_data["concepts"]
        self.off = fixture_data["induction"]["off_skeleton"]
        self.topic = fixture_data.get("topic", "agents")
        self.tutor: TutorSession | None = None

    def _cur(self) -> dict:
        return self.tutor.current() if self.tutor else {}

    def _quiz_pending(self) -> bool:
        cur = self._cur()
        return bool(self.tutor and not cur.get("done") and cur.get("question"))

    def current(self) -> dict:
        """Snapshot for the initial page render (empty 'conversing' state before teaching)."""
        if self.tutor:
            return self.tutor.current()
        return {"done": False, "concept_name": None, "teach": None, "question": None,
                "route": [], "route_version": 1, "learner": [], "cited": [], "evidence": [],
                "decision": None, "rationale": None, "induced": [], "intent": None,
                "mastery": None, "confidence": None}

    def _start_teaching(self, slug: str):
        slug_to_id = {c["slug"]: c["id"] for c in self.concepts}
        self.tutor = TutorSession(self.conn, self.ckpt, self.sid)
        if self.off and slug == self.off["slug"]:
            self.tutor.start(self.topic, target_concept_ids=[],
                             pending_induction=self.data["induction"], mastery_threshold=0.75)
        else:
            self.tutor.start(self.topic, target_concept_ids=[slug_to_id[slug]],
                             mastery_threshold=0.75)
        for ev in self.tutor._terminal_events():
            yield ev

    def _grounded_aside(self, slug: str) -> str:
        """A short answer to a side question, grounded ONLY in that concept's top chunk."""
        slug_to_id = {c["slug"]: c["id"] for c in self.concepts}
        cid = slug_to_id.get(slug)
        if cid is None:
            return "That's outside what these papers cover — let's stay with the question."
        ev = retrieve_node({"current_concept_id": cid}, self.conn).get("current_evidence") or []
        if not ev:
            return "I don't have evidence on that here — let's stay with the question."
        chunk = ev[0]
        from litnav.llm import client as llm_client
        det = chunk["text"][:200].rstrip() + "…"
        prompt = ("Answer the learner's side question in ONE short sentence, grounded ONLY in "
                  f"this evidence (do not add facts beyond it):\n{chunk['text']}")
        return llm_client.complete_text(prompt, fallback=det, max_tokens=80)

    def handle(self, message: str):
        cur = self._cur()
        pending = self._quiz_pending()
        question = cur.get("question") if pending else None
        d = dispatch(message, concepts=self.concepts, off=self.off,
                     quiz_pending=pending, question=question)
        yield {"type": "dispatch", "action": d["action"],
               "label": f"understood as: {d['action']}"}

        if d["action"] == "answer":
            yield from self.tutor.stream_answer(message)
        elif d["action"] == "set_goal":
            yield from self._start_teaching(d["slug"])
        elif d["action"] == "aside":
            yield {"type": "reply", "text": self._grounded_aside(d["slug"])}
            if question:
                yield {"type": "question", "text": question}
            yield {"type": "done", "done": False}
        else:  # chat or out_of_scope
            yield {"type": "reply", "text": d["reply"] or "What would you like to learn?"}
            if question:
                yield {"type": "question", "text": question}
            yield {"type": "done", "done": bool(cur.get("done"))}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_agent_session.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Full suite + gates + commit**

Run: `python -m pytest -q` and `verify_m0..m3` (all green offline).
```bash
git add litnav/ui/interactive.py tests/test_agent_session.py
git commit -m "feat(ui): AgentSession — conversation layer over the unchanged teaching graph"
```

---

## Task 3: Wire AgentSession into the server

**Files:**
- Modify: `litnav/ui/server.py`
- Test: `tests/test_tutor_routes.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_tutor_routes.py`)**

```python
def test_events_handles_a_chat_turn(client):
    # Start a session with a greeting goal -> conversational, no teaching yet.
    r = client.get("/tutor/start", params={"goal": "你好"})
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.post(f"/tutor/{sid}/events", json={"answer": "what can you teach me?"})
    assert ev.status_code == 200
    assert "text/event-stream" in ev.headers["content-type"]
    assert '"reply"' in ev.text or '"dispatch"' in ev.text
    assert '"done"' in ev.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_tutor_routes.py::test_events_handles_a_chat_turn -q`
Expected: FAIL (the session is a `TutorSession` with no `handle`, and `/tutor/start?goal=你好` currently 200s on the home decline rather than creating a session).

- [ ] **Step 3: Modify `litnav/ui/server.py`**

Add the import and an agent registry near `_TUTORS`:

```python
from litnav.ui.interactive import AgentSession, TutorSession

_AGENTS: dict[str, AgentSession] = {}
```

Replace `_start_tutor` usage in `tutor_start` so it ALWAYS creates an `AgentSession` (the
conversation entry), seeding the per-session DB once. Add this helper and rewrite the routes:

```python
def _start_agent(goal: str, intent: str | None) -> str:
    sid = str(uuid.uuid4())
    base = Path(DEMO_DB_PATH).parent
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(base / f"tutor-{sid}.sqlite"), check_same_thread=False)
    init_db(conn)
    seed_demo_data(conn, _TUTOR_FIXTURE)
    ckpt = sqlite3.connect(str(base / f"tutor-{sid}-ckpt.sqlite"), check_same_thread=False)
    ag = AgentSession(conn, ckpt, sid, _fixture_data())
    _AGENTS[sid] = ag
    # An intent (researcher/journalist) starts teaching immediately; an explicit teachable
    # goal also starts teaching; anything else stays in conversation until the user says more.
    if intent:
        ag.tutor = TutorSession(conn, ckpt, sid)
        ag.tutor.start(ag.topic, target_concept_ids=[], intent=intent, mastery_threshold=0.75)
    else:
        plan = resolve_goal(goal, ag.concepts, ag.off)
        if plan["kind"] in ("concept", "induce"):
            list(ag._start_teaching(plan["slug"]))   # run the first teach now
    return sid


@app.get("/tutor/start")
def tutor_start(goal: str = "", intent: str = ""):
    from litnav.intent import INTENTS
    sid = _start_agent(goal, intent if intent in INTENTS else None)
    return RedirectResponse(f"/tutor/{sid}", status_code=303)


@app.get("/tutor/{sid}", response_class=HTMLResponse)
def tutor_page(sid: str):
    ag = _AGENTS.get(sid)
    if ag is None:
        return RedirectResponse("/tutor", status_code=303)
    return _TEMPLATES.get_template("agent.html").render(
        sid=sid, n_papers=_n_papers(_fixture_data()),
        cost=session_cost(ag.conn, sid), **ag.current())


@app.post("/tutor/{sid}/events")
async def tutor_events(sid: str, request: Request):
    ag = _AGENTS.get(sid)
    if ag is None:
        return JSONResponse({"type": "error", "message": "no such session"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = (body.get("answer") or "").strip()

    def gen():
        try:
            stream = ag.handle(message) if message else iter(ag.current_events())
            for ev in stream:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

Add a tiny `current_events()` to `AgentSession` (used by the no-message hydrate) right after
`current()`:

```python
    def current_events(self):
        if self.tutor:
            return self.tutor._terminal_events()
        return [{"type": "reply",
                 "text": "Hi! Tell me what you'd like to learn from the agent papers."},
                {"type": "done", "done": False}]
```

> The old `_start_tutor`, `tutor_answer` GET, and `_TUTORS` may be removed if now unused —
> grep first; if `tutor_answer`/`_TUTORS` are referenced only by removed code, delete them.
> Keep `/tutor/{sid}/answer` only if a no-JS fallback is still wanted; otherwise drop it.

- [ ] **Step 4: Update the unknown-goal handling on the home page**

`tutor_start` now always starts a session (a non-teachable goal lands in conversation, where
the agent greets/guides). The home page's inline out-of-scope decline branch is no longer
reached from `tutor_start`; that's fine — the decline now happens conversationally inside the
session. Leave `tutor_home(message=…)` as-is (still used for `/tutor` with no goal).

- [ ] **Step 5: Update the one test whose behavior changed, then run**

An unknown goal now enters a conversational session (the decline happens on the first chat
turn), instead of re-rendering the home page. Replace `test_unknown_goal_returns_home_with_message`
in `tests/test_tutor_routes.py` with:

```python
def test_unknown_goal_enters_a_conversational_session(client):
    r = client.get("/tutor/start", params={"goal": "teach me quantum chromodynamics"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)                 # a session page, not the home decline
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.post(f"/tutor/{sid}/events", json={"answer": "what can you teach?"})
    assert ev.status_code == 200
    assert '"reply"' in ev.text                    # the agent guides/declines conversationally
```

Then run: `python -m pytest tests/test_tutor_routes.py -q`
Expected: PASS. The other route tests are unaffected — a concept goal still reaches a session
that teaches ReAct, an intent still starts teaching, and the unknown-session 404 still holds.

- [ ] **Step 6: Full suite + gates + commit**

Run: `python -m pytest -q` and `verify_m0..m3` (all green offline).
```bash
git add litnav/ui/server.py tests/test_tutor_routes.py
git commit -m "feat(ui): drive /tutor through AgentSession (conversational turns over SSE)"
```

---

## Task 4: Multi-turn chat front-end

**Files:**
- Modify: `litnav/ui/templates/agent.html`

No unit test (HTML/JS); verified in Task 5. The page already streams via fetch; add handling
for the new `reply` and `dispatch` events and keep the input usable every turn.

- [ ] **Step 1: Add the new event handlers in `agent.html`'s `handleEvent`**

In the `handleEvent(e,steps,inp)` function, add two branches (keep the existing ones):

```javascript
  if(e.type==='dispatch'){steps.length=0;steps.push({label:e.label,detail:'',state:'active'});setFlow(steps);}
  else if(e.type==='reply'){steps.forEach(s=>s.state='done');setFlow(steps);if(e.text)addBubble('ai',e.text,true);}
  else if(e.type==='step'){steps.forEach(s=>s.state='done');steps.push({label:e.label,detail:e.detail,state:'active'});setFlow(steps);}
```

(Place the `dispatch`/`reply` branches before the existing `step` branch; the rest —
`teach`/`question`/`state`/`done`/`error` — stays unchanged.)

- [ ] **Step 2: Ensure the answer box is always present**

In the template, the answer form is currently hidden when `done`. For a conversation it must
always be available. Replace the `{% if not done %}…{% else %}…{% endif %}` block around the
answer form with: always render the form, and show the "session complete" card in addition
when `done`:

```html
    {% if done %}
    <div class="card"><b>This thread is complete.</b> <a href="/sessions/{{ sid }}">full trace &rarr;</a> · <a href="/tutor">new chat</a></div>
    {% endif %}
    <form class="answer" id="answer-form" onsubmit="return submitAnswer(event)">
      <input id="answer-input" autocomplete="off" autofocus placeholder="ask anything, or answer the question…">
      <button type="submit">Send</button>
    </form>
```

- [ ] **Step 3: Offline render check**

```bash
cd "<worktree>" && LITNAV_LLM_PROVIDER=none python -c "
import sqlite3, uuid, json
from litnav.storage.schema import init_db; from litnav.storage.seed import seed_demo_data
from litnav.ui.interactive import AgentSession
from litnav.ui.cost import session_cost
from jinja2 import Environment, FileSystemLoader, select_autoescape
c=sqlite3.connect(':memory:',check_same_thread=False); init_db(c); seed_demo_data(c,'data/seed/agents_m3.json')
ck=sqlite3.connect(':memory:',check_same_thread=False)
data=json.load(open('data/seed/agents_m3.json',encoding='utf-8'))
ag=AgentSession(c,ck,'x',data)
env=Environment(loader=FileSystemLoader('litnav/ui/templates'), autoescape=select_autoescape(['html']))
html=env.get_template('agent.html').render(sid='x', n_papers=25, cost=session_cost(c,'x'), **ag.current())
assert 'ask anything' in html and 'Send' in html
print('render OK', len(html))
"
```
Expected: `render OK …`.

- [ ] **Step 4: Full suite stays green + commit**

Run: `python -m pytest -q` (route tests render the page server-side; must stay green).
```bash
git add litnav/ui/templates/agent.html
git commit -m "feat(ui): multi-turn chat front-end (reply/dispatch events, always-on input)"
```

---

## Task 5: Live preview verification

No code. Verify the conversational agent live (uses the `.env` key); fix CSS/JS only.

- [ ] **Step 1:** free port 8000, `preview_start` `litnav-panel`.
- [ ] **Step 2:** Open `/tutor`, type **"你好"** → confirm a natural greeting reply that names what it can teach (NOT the old rigid decline), and the input stays usable.
- [ ] **Step 3:** Type **"I want to understand ReAct"** → teaching starts (teach bubble + quiz); Glass box shows the `dispatch` step "understood as: set_goal" then the flow.
- [ ] **Step 4:** Mid-quiz, type a side question **"what's chain-of-thought?"** → confirm a brief grounded reply, then the quiz is re-posed; then answer correctly → it grades and advances.
- [ ] **Step 5:** Type **"teach me CRISPR"** → conversational decline (names what it can teach), input still usable.
- [ ] **Step 6:** If issues, edit `agent.html` (CSS/JS) only, reload, re-verify; commit fixes.

---

## Final verification
- [ ] `python -m pytest -q` → all green (≈ 91 + new tests).
- [ ] `verify_m0..m3` → all PASS offline.
- [ ] Live: "你好" greets conversationally; goal teaches (grounded); mid-quiz aside answers then re-poses; out-of-scope declines — all in one chat thread.
- [ ] When the user approves: push + ff local main + verify three refs.
