"""Tests for litnav/llm/lang.py — language detector."""
import os
import sqlite3
import pytest
from litnav.llm import lang, router
from litnav.storage.schema import init_db


# ── Offline heuristic tests ──────────────────────────────────────────────────

def test_offline_chinese(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert lang.detect_language("给我一个关于 CRISPR 的概览") == "Chinese"


def test_offline_english(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert lang.detect_language("hello world") == "English"


def test_offline_russian(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert lang.detect_language("Привет мир") == "Russian"


def test_offline_japanese(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    # Use pure katakana (no CJK kanji) to avoid Chinese range match coming first
    assert lang.detect_language("コンピュータサイエンス") == "Japanese"


def test_offline_arabic(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert lang.detect_language("مرحبا بالعالم") == "Arabic"


def test_offline_korean(monkeypatch):
    monkeypatch.setenv("LITNAV_LLM_PROVIDER", "none")
    assert lang.detect_language("안녕하세요") == "Korean"


# ── Live path: monkeypatched router ─────────────────────────────────────────

def test_live_router_result_returned(monkeypatch):
    """When provider is NOT none/offline, the LLM result should be used."""
    captured = {}

    def fake_complete_json(prompt, *, tier, stage, fallback, **kwargs):
        captured["called"] = True
        captured["prompt"] = prompt
        return {"language": "Spanish"}

    monkeypatch.delenv("LITNAV_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(router, "complete_json", fake_complete_json)

    c = sqlite3.connect(":memory:")
    init_db(c)
    result = lang.detect_language("Quiero aprender sobre CRISPR", conn=c, session_id="s")

    assert captured.get("called"), "router.complete_json was not called"
    assert result == "Spanish"


def test_live_router_fallback_on_bad_response(monkeypatch):
    """If router returns something without a valid 'language' key, fall back to heuristic."""
    monkeypatch.delenv("LITNAV_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(router, "complete_json", lambda *a, **k: {"language": ""})

    result = lang.detect_language("hello world")
    assert result == "English"   # heuristic fallback
