"""
The HTTP layer has to enforce access, not just display it.

Hiding the workspace behind a login screen protects nothing on its own — the
API is reachable directly, and a request that skips the page entirely is the
one an attacker sends. These tests go straight at the endpoints.
"""

from __future__ import annotations

import dataclasses
import os
import threading

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ.setdefault("LLM_PROVIDER", "fixture")

from fastapi.testclient import TestClient  # noqa: E402

from api import auth, db, main  # noqa: E402
from api.config import auth_settings  # noqa: E402

ADMIN = "boss@hondaatlas.com.pk"
HR = "hr@hondaatlas.com.pk"
OUTSIDER = "stranger@internet.com"

PROTECTED = [
    ("GET", "/api/runs"),
    ("GET", "/api/runs/run-does-not-exist"),
    ("DELETE", "/api/runs/run-does-not-exist"),
    ("GET", "/api/audit"),
    ("GET", "/api/auth/users"),
    ("POST", "/api/jd/analyze"),
    ("POST", "/api/runs"),
]


@pytest.fixture
def sent():
    return {}


@pytest.fixture
def client(tmp_path, monkeypatch, sent):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "_schema_ready", False)
    monkeypatch.setattr(db, "_init_lock", threading.Lock())

    cfg = dataclasses.replace(
        auth_settings,
        admin_emails=[ADMIN],
        allowed_domains=[],
        open_access=False,
        secret="test-secret",
        resend_cooldown_seconds=0,      # several sign-ins per test
    )
    monkeypatch.setattr(auth, "cfg", cfg)
    monkeypatch.setattr(main, "auth_settings", cfg)
    monkeypatch.setattr(auth, "send_code", lambda to, code: sent.__setitem__(to, code))

    auth.seed_admins()
    db.upsert_user(HR, name="HR User", role="hr")
    return TestClient(main.app)


def sign_in(client, sent, email):
    assert client.post("/api/auth/email/request", json={"email": email}).status_code == 200
    r = client.post("/api/auth/email/verify", json={"email": email, "code": sent[email]})
    assert r.status_code == 200, r.text
    return r


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_data_endpoint_refuses_an_anonymous_request(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_stays_open(client):
    """The sign-in page checks this before anyone has signed in."""
    assert client.get("/api/health").status_code == 200


def test_sign_in_options_do_not_leak_configuration(client):
    body = client.get("/api/auth/options").json()
    assert set(body) == {"email", "phone", "firebase_email", "open_access", "warnings"}


def test_an_unlisted_address_gets_no_code(client, sent):
    r = client.post("/api/auth/email/request", json={"email": OUTSIDER})
    assert r.status_code == 403
    assert sent == {}


def test_signing_in_grants_access(client, sent):
    assert client.get("/api/runs").status_code == 401
    sign_in(client, sent, HR)
    assert client.get("/api/runs").status_code == 200


def test_the_session_cookie_cannot_be_read_by_scripts(client, sent):
    sign_in(client, sent, HR)
    cookie = next(c for c in client.cookies.jar if c.name == auth.SESSION_COOKIE)
    assert cookie.has_nonstandard_attr("HttpOnly"), \
        "a session a page script can read is a session an injected script can steal"


def test_who_am_i(client, sent):
    sign_in(client, sent, HR)
    body = client.get("/api/auth/me").json()
    # Exactly these three fields, and no more. This is an equality check on
    # purpose: /api/auth/me is what the whole site trusts about who is signed
    # in, and a stray field here once put every user into a redirect loop.
    assert body == {"email": HR, "name": "HR User", "role": "hr"}


def test_signing_out_revokes_access(client, sent):
    sign_in(client, sent, HR)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/runs").status_code == 401


def test_a_wrong_code_does_not_sign_anyone_in(client, sent):
    client.post("/api/auth/email/request", json={"email": HR})
    r = client.post("/api/auth/email/verify", json={"email": HR, "code": "000000"})
    assert r.status_code == 400
    assert client.get("/api/runs").status_code == 401


# --- roles -----------------------------------------------------------------


def test_an_ordinary_user_cannot_read_the_audit_log(client, sent):
    sign_in(client, sent, HR)
    assert client.get("/api/audit").status_code == 403


def test_an_ordinary_user_cannot_grant_access(client, sent):
    sign_in(client, sent, HR)
    r = client.post("/api/auth/users",
                    json={"email": "friend@example.com", "name": "Friend", "role": "admin"})
    assert r.status_code == 403
    assert db.get_user("friend@example.com") is None


def test_an_administrator_can_grant_and_withdraw_access(client, sent):
    sign_in(client, sent, ADMIN)

    assert client.post("/api/auth/users",
                       json={"email": "intern@hondaatlas.com.pk",
                             "name": "Intern", "role": "hr"}).status_code == 200
    assert db.get_user("intern@hondaatlas.com.pk")["active"] == 1

    assert client.post(
        "/api/auth/users/intern@hondaatlas.com.pk/active?active=false"
    ).status_code == 200
    assert db.get_user("intern@hondaatlas.com.pk")["active"] == 0


def test_an_administrator_cannot_lock_themselves_out(client, sent):
    """Otherwise the last admin can remove the only account able to restore access."""
    sign_in(client, sent, ADMIN)
    r = client.post(f"/api/auth/users/{ADMIN}/active?active=false")
    assert r.status_code == 400
    assert db.get_user(ADMIN)["active"] == 1


def test_withdrawing_access_ends_a_session_already_in_progress(client, sent):
    hr_client = TestClient(main.app)
    sign_in(hr_client, sent, HR)
    assert hr_client.get("/api/runs").status_code == 200

    admin_client = TestClient(main.app)
    sign_in(admin_client, sent, ADMIN)
    admin_client.post(f"/api/auth/users/{HR}/active?active=false")

    assert hr_client.get("/api/runs").status_code == 401, \
        "a withdrawn account must stop working immediately"


def test_a_bad_role_is_refused(client, sent):
    sign_in(client, sent, ADMIN)
    r = client.post("/api/auth/users",
                    json={"email": "x@y.com", "name": "X", "role": "superuser"})
    assert r.status_code == 400


# --- the audit trail names the real person ---------------------------------


def test_actions_are_recorded_against_the_signed_in_user(client, sent):
    sign_in(client, sent, HR)
    client.get("/api/runs")

    entries = db.list_audit(50)
    actors = {e["actor"] for e in entries}
    assert HR in actors
    assert "Laiba Sattar" not in actors, "the hard-coded name must be gone"


# --- the audit log reports its own size ------------------------------------
#
# A page of the record and the whole record look identical if the response
# never says how many entries exist. An administrator reading the newest two
# hundred lines and concluding "that is everything" is precisely the mistake
# this log is kept to prevent, so the count is part of the contract.


def test_audit_reports_the_total_not_just_the_page(client, sent):
    sign_in(client, sent, ADMIN)

    for i in range(12):
        db.log_audit(ADMIN, "start_ranking", f"run-{i}", detail=f"role {i}")

    body = client.get("/api/audit?limit=5").json()

    assert len(body["entries"]) == 5, "the page must honour the limit"
    assert body["total"] >= 12, "the total must count every entry, not the page"
    assert body["total"] > len(body["entries"]), "this fixture must exercise truncation"
    assert body["limit"] == 5


def test_audit_limit_is_bounded(client, sent):
    """A caller cannot ask for an unbounded read of the whole table."""
    sign_in(client, sent, ADMIN)

    assert client.get("/api/audit?limit=999999").json()["limit"] == 1000
    assert client.get("/api/audit?limit=0").json()["limit"] == 1


def test_deleting_a_run_records_which_run(client, sent):
    """The one audit line that most needs to name a run used to name none.

    The id was written to the run_id column all along; nothing read it back,
    so "Deleted a ranking" was indistinguishable from any other deletion.
    """
    sign_in(client, sent, ADMIN)

    db.log_audit(ADMIN, "delete_run", "run-deadbeef")

    entry = next(
        e for e in client.get("/api/audit").json()["entries"]
        if e["action"] == "delete_run"
    )
    assert entry["run_id"] == "run-deadbeef"
