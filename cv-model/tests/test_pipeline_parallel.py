"""
The ranking pipeline processes CVs on several threads at once.

That is a real speed win — each candidate spends most of its time waiting on
the LLM — but concurrency is exactly where a ranking system can quietly go
wrong: if the output depends on which thread finished first, the same batch of
CVs can produce two different shortlists, and neither the reviewer nor the
audit trail would ever show why. These tests pin that down.

Run offline:  EMBED_PROVIDER=hash LLM_PROVIDER=fixture python -m pytest tests/
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ.setdefault("LLM_PROVIDER", "fixture")

from cv_ranker.pipeline import collect_cv_paths, prepare_job, run_ranking  # noqa: E402

JD = "data/jds/mech_design_engineer.txt"
CVS = "data/sample_cvs"


@pytest.fixture(scope="module")
def paths() -> list[str]:
    found = collect_cv_paths(CVS)
    if len(found) < 2:
        pytest.skip("sample CVs not available")
    return found


def _run(paths: list[str], workers: int):
    job = prepare_job(jd_path=JD)
    return run_ranking(job, paths, use_llm_transferability=False, max_workers=workers)


def _fingerprint(run) -> list[tuple[str, float]]:
    return [(s.candidate_name, s.source_file, round(s.final, 6)) for s in run.top()]


def test_parallel_matches_sequential(paths):
    """Eight threads must produce exactly the ranking one thread produces.

    If this ever fails, the scores depend on timing — the ranking would not be
    reproducible, and a candidate could not be told why they placed where they
    did.
    """
    assert _fingerprint(_run(paths, 8)) == _fingerprint(_run(paths, 1))


def test_repeated_parallel_runs_are_identical(paths):
    """Same input, same output — twice, both times on many threads."""
    assert _fingerprint(_run(paths, 8)) == _fingerprint(_run(paths, 8))


def test_every_cv_is_accounted_for(paths):
    """Scored plus failed must equal the number of files submitted.

    A dropped future would silently shrink the shortlist: the CV would vanish
    without appearing in the failure list, so nobody would know to look at it.
    """
    run = _run(paths, 8)
    assert len(run.scores) + len(run.failures) == len(paths)
