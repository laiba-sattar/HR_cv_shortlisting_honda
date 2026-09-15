"""
Phone sign-in: Firebase proves the number, this system decides access.

The distinction these tests defend is the whole point of the feature. Firebase
will happily confirm any number in the world — that is its job. If a valid
Firebase token were treated as permission, everyone who owns a phone would be
inside a system holding candidates' CVs. So every test here is some version of
the same question: does a genuine token, for a number nobody listed, still get
turned away?
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
from api.firebase import BadPhoneToken, FirebaseUnavailable  # noqa: E402

ADMIN = "boss@hondaatlas.com.pk"
HR = "hr@hondaatlas.com.pk"
HR_PHONE = "+923001234567"

VERIFY = "/api/auth/phone/verify"


@pytest.fixture
def tokens():
    """token -> the phone number Firebase would report for it."""
    return {"good-token": HR_PHONE}


@pytest.fixture
def client(tmp_path, monkeypatch, tokens):
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
        # Pinned, not inherited. Without this the suite reads whatever
        # FIREBASE_CREDENTIALS happens to be in the developer's own .env, so
        # `test_the_phone_option_is_hidden_until_firebase_is_configured`
        # passed on a machine with no Firebase set up and failed on one with
        # it — the same code, two answers. A test whose result depends on who
        # runs it is worse than no test: it teaches people to ignore red.
        firebase_credentials="",
    )
    monkeypatch.setattr(auth, "cfg", cfg)
    monkeypatch.setattr(main, "auth_settings", cfg)

    # Stand in for Firebase. The real one checks Google's signing keys; what
    # matters here is only what it returns, and that a rejection propagates.
    def fake_verify(id_token: str) -> str:
        if id_token not in tokens:
            raise BadPhoneToken("That sign-in could not be verified.")
        return tokens[id_token]

    monkeypatch.setattr(auth, "verified_phone_number", fake_verify)

    auth.seed_admins()
    db.upsert_user(HR, name="HR User", role="hr", phone=HR_PHONE)
    return TestClient(main.app)


# ---------------------------------------------------------------------------


def test_a_listed_number_signs_in(client):
    r = client.post(VERIFY, json={"id_token": "good-token"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == HR
    # And the session actually works, rather than merely being reported.
    assert client.get("/api/runs").status_code == 200


def test_a_genuine_token_for_an_unlisted_number_is_refused(client, tokens):
    """The case the whole design exists for."""
    tokens["stranger-token"] = "+923339999999"
    r = client.post(VERIFY, json={"id_token": "stranger-token"})
    assert r.status_code == 403
    assert client.get("/api/runs").status_code == 401


def test_an_unverifiable_token_is_refused(client):
    r = client.post(VERIFY, json={"id_token": "forged"})
    assert r.status_code == 400
    assert client.get("/api/runs").status_code == 401


def test_a_deactivated_user_cannot_come_back_in_by_phone(client):
    """Switching somebody off has to close every door, not just the email one."""
    db.set_user_active(HR, False)
    assert client.post(VERIFY, json={"id_token": "good-token"}).status_code == 403


def test_the_number_is_matched_however_it_was_typed(client, tokens, monkeypatch):
    """0300…, +92300… and 92300… are one number; storing one form is enough."""
    db.upsert_user("local@hondaatlas.com.pk", name="Local", phone="0301 2345678")
    tokens["local-token"] = "+923012345678"
    r = client.post(VERIFY, json={"id_token": "local-token"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "local@hondaatlas.com.pk"


def test_open_access_does_not_admit_an_unlisted_number(client, monkeypatch, tokens):
    """`open_access` is written in terms of email domains.

    A phone number has no domain to match, so the rule cannot apply to it. If
    it silently did, turning on a testing switch would open SMS sign-in to the
    entire world.
    """
    cfg = dataclasses.replace(auth.cfg, open_access=True)
    monkeypatch.setattr(auth, "cfg", cfg)
    tokens["anyone"] = "+14155550000"
    assert client.post(VERIFY, json={"id_token": "anyone"}).status_code == 403


def test_an_unconfigured_server_says_so_rather_than_failing_oddly(client, monkeypatch):
    def unavailable(id_token: str) -> str:
        raise FirebaseUnavailable("Phone sign-in is not configured.")

    monkeypatch.setattr(auth, "verified_phone_number", unavailable)
    r = client.post(VERIFY, json={"id_token": "good-token"})
    assert r.status_code == 503


def test_a_token_with_no_phone_number_is_refused(client, tokens):
    """A Google or anonymous Firebase login also produces a valid token."""
    tokens["email-login"] = ""
    assert client.post(VERIFY, json={"id_token": "email-login"}).status_code == 403


def test_signing_in_by_phone_is_written_to_the_audit_log(client):
    client.post(VERIFY, json={"id_token": "good-token"})
    actions = [e["action"] for e in db.list_audit(20)]
    assert "signed_in_by_phone" in actions


def test_the_phone_option_is_hidden_until_firebase_is_configured(client, monkeypatch):
    """Offering a sign-in route the server cannot serve is worse than hiding it."""
    assert client.get("/api/auth/options").json()["phone"] is False

    cfg = dataclasses.replace(auth.cfg, firebase_credentials="firebase-key.json")
    monkeypatch.setattr(main, "auth_settings", cfg)
    assert client.get("/api/auth/options").json()["phone"] is True
