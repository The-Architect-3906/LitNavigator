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
    assert "Reads the literature" in r.text  # hero headline (replaces old corpus scope line)


def test_concept_goal_starts_session(client):
    r = client.get("/tutor/start", params={"goal": "I want to understand ReAct"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)         # redirected to a session page
    assert "ReAct" in r.text               # teaching the matched concept
    assert "route" in r.text.lower()       # right-hand glass box rendered


def test_unknown_goal_enters_a_conversational_session(client):
    r = client.get("/tutor/start", params={"goal": "teach me quantum chromodynamics"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)                 # a session page, not the home decline
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.post(f"/tutor/{sid}/events", json={"answer": "what can you teach?"})
    assert ev.status_code == 200
    assert '"reply"' in ev.text                    # the agent guides/declines conversationally


def test_induce_goal_starts_session(client):
    r = client.get("/tutor/start", params={"goal": "I keep seeing multi-agent debate"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)


def test_intent_mode_starts_session(client):
    r = client.get("/tutor/start", params={"intent": "journalist"})
    assert r.status_code == 200
    assert "/tutor/" in str(r.url)             # started a session page
    assert "journalist" in r.text              # header shows the re-scoped mode


def test_events_endpoint_streams_answer_turn(client):
    r = client.get("/tutor/start", params={"goal": "I want to understand ReAct"})
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.post(f"/tutor/{sid}/events",
                     json={"answer": "the agent takes actions and observations"})
    assert ev.status_code == 200
    assert "text/event-stream" in ev.headers["content-type"]
    assert "data:" in ev.text
    assert '"done"' in ev.text          # the terminal done event was streamed


def test_events_endpoint_unknown_session_404(client):
    ev = client.post("/tutor/does-not-exist/events", json={})
    assert ev.status_code == 404


def test_events_handles_a_chat_turn(client):
    # Start a session with a greeting goal -> conversational, no teaching yet.
    r = client.get("/tutor/start", params={"goal": "你好"})
    sid = str(r.url).rstrip("/").split("/tutor/")[-1]
    ev = client.post(f"/tutor/{sid}/events", json={"answer": "what can you teach me?"})
    assert ev.status_code == 200
    assert "text/event-stream" in ev.headers["content-type"]
    assert '"reply"' in ev.text or '"dispatch"' in ev.text
    assert '"done"' in ev.text
