"""
A ranking run is written from a background thread while the browser polls for
it from a request thread. That is the exact shape that produced "Run not
found" on a run created moments earlier: a read landing in the middle of
another thread's write came back empty, and the UI reported the ranking as
failed.

These tests reproduce that overlap deliberately. They are slow-ish by design —
a single read/write pair proves nothing about a race.
"""

from __future__ import annotations

import threading
import time

import pytest

from api import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "_schema_ready", False)
    monkeypatch.setattr(db, "_init_lock", threading.Lock())
    yield


def _run(run_id: str, status: str = "processing") -> dict:
    return {
        "id": run_id, "title": "Accounts Payable", "status": status,
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        "created_by": "tester", "version": 1, "top_n": 10,
        "jd_text": "x", "jd_filename": None, "jd_profile_json": None,
        "manual_json": "{}", "skills_json": "[]",
        "progress_done": 0, "progress_total": 5, "progress_current": None,
        "results_json": None, "failures_json": "[]", "versions_json": None,
        "error": None,
    }


def test_a_run_written_on_one_thread_is_visible_on_another():
    """The minimum promise: create a run, then find it from a different thread.

    Connections are per-thread, so this also proves they see each other's
    committed data rather than each thread getting a private database.
    """
    db.upsert_run(_run("run-visible"))

    seen: list[object] = []
    t = threading.Thread(target=lambda: seen.append(db.get_run("run-visible")))
    t.start()
    t.join()

    assert seen[0] is not None, "a committed run must be visible from other threads"
    assert seen[0]["title"] == "Accounts Payable"


def test_polling_never_loses_a_run_while_it_is_being_updated():
    """The actual bug: poll a run while a background thread updates its progress.

    Before the per-thread-connection fix, some of these reads returned None and
    the API answered 404 for a run that plainly existed.
    """
    db.upsert_run(_run("run-polled"))

    stop = threading.Event()
    write_errors: list[Exception] = []

    def writer():
        i = 0
        while not stop.is_set():
            i += 1
            try:
                db.update_run("run-polled", progress_done=i % 6,
                              progress_current=f"cv_{i % 6}.pdf")
            except Exception as e:  # noqa: BLE001
                write_errors.append(e)
                return
            time.sleep(0.001)  # keep the overlap realistic, not a spin loop

    w = threading.Thread(target=writer, daemon=True)
    w.start()
    try:
        misses = sum(1 for _ in range(400) if db.get_run("run-polled") is None)
    finally:
        stop.set()
        w.join(timeout=5)

    assert not write_errors, f"writer failed: {write_errors[0]}"
    assert misses == 0, f"{misses}/400 polls could not see an existing run"


def test_concurrent_writers_all_land():
    """Several runs created at once must all be stored, none silently lost."""
    ids = [f"run-{i:03d}" for i in range(20)]
    threads = [threading.Thread(target=db.upsert_run, args=(_run(i),)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stored = {r["id"] for r in db.list_runs(limit=100)}
    assert set(ids) <= stored, f"missing: {sorted(set(ids) - stored)}"
