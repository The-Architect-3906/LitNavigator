"""Fix A.5: the extract prompt must nudge toward general field concepts, not one system's jargon."""
import inspect
from litnav.digest import extract


def test_prompt_nudges_general_concepts():
    src = inspect.getsource(extract.extract_concepts)
    low = src.lower()
    assert "proprietary" in low or "general, field-level" in low or "field-level concepts" in low
