from litnav.artifact.contract import ArtifactInput, ArtifactResult, FORMATS
from litnav.artifact import selector

def test_formats_set():
    assert FORMATS == {"mindmap", "notes", "slides", "worked_example", "combination"}

def test_selector_matrix():
    s = selector.select_format
    assert s({"goal_type": "survey", "content_kind": "structure", "user_request": ""}) == "mindmap"
    assert s({"goal_type": "functional", "content_kind": "procedure", "user_request": "how to build X"}) == "worked_example"
    assert s({"goal_type": "mastery", "content_kind": "reference", "user_request": "quick recall"}) == "combination"
    assert s({"goal_type": None, "content_kind": "reference", "user_request": "crash course"}) == "notes"
    assert s({"goal_type": None, "content_kind": "present", "user_request": "make a deck"}) == "slides"

def test_format_override_wins():
    assert selector.select_format({"goal_type": "survey"}, override="notes") == "notes"

def test_input_output_shapes():
    ai = ArtifactInput(concept_ids=[1, 2], scenario={"goal_type": "survey"}, format=None)
    r = ArtifactResult(artifact_path="/tmp/x.md", format="mindmap", citations=["c0"])
    assert ai.concept_ids == [1, 2] and r.format == "mindmap" and r.citations == ["c0"]
