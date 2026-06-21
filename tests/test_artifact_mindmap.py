from litnav.artifact.renderers import mindmap

GRAPH = {
    "concepts": [{"slug": "tool_use", "name": "Tool Use"}, {"slug": "react", "name": "ReAct"},
                 {"slug": "reflexion", "name": "Reflexion"}],
    "edges": [{"prereq_slug": "tool_use", "target_slug": "react", "edge_type": "prerequisite"},
              {"prereq_slug": "react", "target_slug": "reflexion", "edge_type": "similarity"}],
}

def test_mindmap_is_mermaid_with_typed_edges():
    out = mindmap.render(GRAPH, citations=["c0", "c1"])
    assert "```mermaid" in out and "graph TD" in out
    assert "tool_use" in out and "Tool Use" in out
    assert "tool_use --> react" in out          # prerequisite = solid arrow
    assert "react -.-> reflexion" in out         # similarity = dashed arrow
    assert "Citations:" in out and "c0" in out
    assert any(w in out.lower() for w in ("recall", "retrieval", "quiz", "test yourself"))  # retrieval prompt

def test_mindmap_handles_empty_graph():
    out = mindmap.render({"concepts": [], "edges": []}, citations=[])
    assert "```mermaid" in out   # still a valid (empty) mermaid block, no crash
