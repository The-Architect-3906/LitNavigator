import os

from litnav.llm.client import complete_json


def test_fallback_returned_when_provider_none(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    fallback = {"detected_misconception": None}
    result = complete_json("irrelevant prompt", fallback=fallback)
    assert result == fallback


def test_fallback_makes_no_network_call(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    import socket
    original = socket.create_connection

    def deny(*a, **kw):
        raise AssertionError("Network call attempted in offline mode")

    monkeypatch.setattr(socket, "create_connection", deny)
    result = complete_json("prompt", fallback={"x": 1})
    assert result == {"x": 1}
