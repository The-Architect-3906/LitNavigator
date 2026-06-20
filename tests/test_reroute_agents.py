import json, sqlite3, uuid
from litnav.graph.builder import build_graph, make_initial_state
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

FIXTURE = "data/seed/agents_reroute.json"


def test_prereq_auto_included_in_route():
    """topo-sort includes tool_use (prereq of reflection) in the initial route.
    No replan is needed: the prerequisite is present from the start, and the
    session completes in route_version 1."""
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
    concepts_in_route = [r[0] for r in conn.execute(
        "SELECT DISTINCT concept_id FROM route_steps WHERE session_id=?", (sid,)).fetchall()]
    # Both tool_use (prereq) and reflection (target) are in the route from the start
    assert slug_to_id["tool_use"] in concepts_in_route
    assert slug_to_id["reflection"] in concepts_in_route
    # No replan needed because the prereq was already included by topo-sort
    assert max(versions) == 1, "expanded route needs no replan"
