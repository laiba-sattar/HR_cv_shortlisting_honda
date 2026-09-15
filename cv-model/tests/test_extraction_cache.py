"""
The extraction cache has to be right about three things, or it is worse than
having no cache at all:

  1. A repeat read of an unchanged CV must not call the LLM.
  2. It must return the *same* answer — that is the point; a cache that drifts
     buys speed and gives up the reproducibility it was added for.
  3. An edited CV, a different model, or an edited prompt must NOT be served
     from the cache. Serving a stale reading of a candidate's CV is the one
     failure mode that would silently corrupt a shortlist.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ["LLM_PROVIDER"] = "stub"

import dataclasses  # noqa: E402

from cv_ranker import cache  # noqa: E402
from cv_ranker.config import settings  # noqa: E402


def _use_settings(monkeypatch, **overrides):
    """Settings is a frozen dataclass on purpose — swap in a modified copy."""
    monkeypatch.setattr(cache, "settings", dataclasses.replace(settings, **overrides))


@pytest.fixture
def cv(tmp_path, monkeypatch):
    _use_settings(monkeypatch,
                  extraction_cache_dir=str(tmp_path / "cache"),
                  extraction_cache_enabled=True)
    p = tmp_path / "candidate.txt"
    p.write_text(_CV.format(years=4), encoding="utf-8")
    return p


_CV = """Ayesha Khan
ayesha.khan@example.com | Lahore, Pakistan

EDUCATION
B.Com (Accounting & Finance), University of the Punjab, 2018

EXPERIENCE
Accounts Payable Officer, Example Textiles (2019 - present), {years} years.
Invoice processing, vendor reconciliation, monthly closing, SAP entry.

SKILLS
SAP, MS Excel, reconciliation, accounts payable, GST filing
"""

PROMPT = "read this cv: {cv_text}"
MODEL = "test-model"


def test_repeat_read_is_served_from_cache(cv):
    key = cache.cache_key(cv, MODEL, PROMPT)
    assert cache.load(key) is None, "nothing stored yet"

    cache.store(key, {"candidate": {"name": "Ayesha Khan"}}, cv.name)
    assert cache.load(key) == {"candidate": {"name": "Ayesha Khan"}}


def test_same_key_for_unchanged_inputs(cv):
    assert cache.cache_key(cv, MODEL, PROMPT) == cache.cache_key(cv, MODEL, PROMPT)


def test_edited_cv_gets_a_new_key(cv):
    before = cache.cache_key(cv, MODEL, PROMPT)
    cv.write_text(_CV.format(years=6), encoding="utf-8")
    assert cache.cache_key(cv, MODEL, PROMPT) != before, (
        "an edited CV must be re-read, not served from the old reading"
    )


def test_different_model_gets_a_new_key(cv):
    assert cache.cache_key(cv, "other-model", PROMPT) != cache.cache_key(cv, MODEL, PROMPT)


def test_edited_prompt_gets_a_new_key(cv):
    assert cache.cache_key(cv, MODEL, PROMPT + " be strict") != cache.cache_key(cv, MODEL, PROMPT)


def test_corrupt_entry_falls_back_to_a_fresh_read(cv, tmp_path):
    key = cache.cache_key(cv, MODEL, PROMPT)
    cache.store(key, {"ok": True}, cv.name)
    entry = next((tmp_path / "cache").rglob("*.json"))
    entry.write_text("{ this is not json", encoding="utf-8")
    assert cache.load(key) is None, "a damaged entry must not break the CV"


def test_disabled_cache_stores_and_returns_nothing(cv, tmp_path, monkeypatch):
    _use_settings(monkeypatch,
                  extraction_cache_dir=str(tmp_path / "cache"),
                  extraction_cache_enabled=False)
    key = cache.cache_key(cv, MODEL, PROMPT)
    cache.store(key, {"ok": True}, cv.name)
    assert cache.load(key) is None


def test_clear_removes_entries(cv):
    cache.store(cache.cache_key(cv, MODEL, PROMPT), {"ok": True}, cv.name)
    assert cache.clear() == 1
    assert cache.load(cache.cache_key(cv, MODEL, PROMPT)) is None


def test_extract_cv_calls_the_llm_only_once(cv, monkeypatch):
    """The end-to-end promise: two extractions, one LLM call."""
    from cv_ranker import extract as extract_mod, llm as llm_mod

    # Pin the backend for this test. get_llm() memoises one client for the
    # whole process, so whichever test ran first would otherwise decide which
    # backend this one gets — and the cache key includes the model name.
    monkeypatch.setattr(llm_mod, "_client", llm_mod.StubLLM())

    calls = {"n": 0}
    real = extract_mod.complete_json

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(extract_mod, "complete_json", counting)

    first = extract_mod.extract_cv(str(cv))
    assert calls["n"] == 1
    second = extract_mod.extract_cv(str(cv))
    assert calls["n"] == 1, "second read should have come from the cache"

    # And it must be the same reading, not merely a fast one.
    assert first.name == second.name
    assert [q.degree_title for q in first.qualifications] == \
           [q.degree_title for q in second.qualifications]
