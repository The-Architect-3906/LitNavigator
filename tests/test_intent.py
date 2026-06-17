import sqlite3

from litnav.graph.builder import make_initial_state
from litnav.nodes.planner import planner_node
from litnav.storage.schema import init_db
from litnav.storage.seed import seed_demo_data

CORPUS = "data/seed/agents_corpus.json"


def _conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    seed_demo_data(conn, CORPUS)
    return conn


def _plan(conn, intent):
    state = make_initial_state("s", "agents", target_concept_ids=[], intent=intent)
    out = planner_node(state, conn)
    return state, [step["concept_id"] for step in out["route"]]


def test_intents_produce_different_routes_and_bars():
    conn = _conn()
    sr, route_res = _plan(conn, "researcher")
    sj, route_jou = _plan(conn, "journalist")
    assert len(route_res) == 7 and len(route_jou) == 3       # different breadth
    assert sr["mastery_threshold"] == 0.8 and sj["mastery_threshold"] == 0.6
    assert sr["teach_depth"] == "explain" and sj["teach_depth"] == "recall"
    assert route_res != route_jou


def test_journalist_leads_with_contested_after_its_prereq():
    conn = _conn()
    slug = {r[1]: r[0] for r in conn.execute("SELECT id, slug FROM concepts")}
    _, route_jou = _plan(conn, "journalist")
    pos = {cid: i for i, cid in enumerate(route_jou)}
    # react is a prereq of both, so it comes first; then the contested multi_agent
    # is surfaced before the consensus agent_taxonomy (frontier-first ordering).
    assert pos[slug["react"]] < pos[slug["multi_agent"]]
    assert pos[slug["multi_agent"]] < pos[slug["agent_taxonomy"]]


def test_no_intent_uses_explicit_targets():
    conn = _conn()
    state = make_initial_state("s", "agents", target_concept_ids=[1], intent=None)
    out = planner_node(state, conn)
    assert [s["concept_id"] for s in out["route"]] == [1]
    assert state["mastery_threshold"] == 0.8  # default, untouched
