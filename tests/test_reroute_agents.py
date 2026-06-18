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
