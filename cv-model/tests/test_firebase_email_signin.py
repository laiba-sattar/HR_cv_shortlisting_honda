"""
Email-link sign-in: Firebase proves the mailbox, this system decides access.

This route exists for a mundane reason with a serious consequence. Our own mail
provider, on its free tier and without a verified domain, refuses to deliver to
any address except the account holder's — so the emailed code reached exactly
one person and nobody else could ever finish signing up. Firebase sends the
link from its own infrastructure, to anyone, at no cost.

What must NOT come with that convenience is a second, weaker front door.
Firebase will confirm any mailbox in the world; that is its job. If a valid
Firebase token were treated as permission, everyone with an email address would
be inside a system holding candidates' CVs. Every test here is a version of the
same question: does a genuine token, for an address nobody listed, still get
turned away?
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import sys
import threading
import types

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ.setdefault("LLM_PROVIDER", "fixture")

from fastapi.testclient import TestClient  # noqa: E402

from api import auth, db, main  # noqa: E402
from api.config import auth_settings  # noqa: E402
from api.firebase import BadEmailToken  # noqa: E402

ADMIN = "boss@hondaatlas.com.pk"
HR = "hr@hondaatlas.com.pk"

VERIFY = "/api/auth/firebase/verify"


@pytest.fixture
def tokens():
    """token -> the address Firebase would report for it."""
    return {"good-token": HR}


@pytest.fixture
def make_client(tmp_path, monkeypatch, tokens):
    """Build the app with a stand-in Firebase and a chosen access policy."""

    def build(**overrides):
        monkeypatch.setattr(db, "DB_PATH", tmp_path / "api.db")
        monkeypatch.setattr(db, "_local", threading.local())
        monkeypatch.setattr(db, "_schema_ready", False)
        monkeypatch.setattr(db, "_init_lock", threading.Lock())

        policy = {
            "admin_emails": [ADMIN],
            "allowed_domains": [],
            "open_access": False,
            "secret": "test-secret",
        }
        policy.update(overrides)
        cfg = dataclasses.replace(auth_settings, **policy)
        monkeypatch.setattr(auth, "cfg", cfg)
        monkeypatch.setattr(main, "auth_settings", cfg)

        # Stand in for Firebase. The real one checks Google's signing keys;
        # what matters here is what it returns and that a rejection propagates.
        def fake_verify(id_token: str) -> tuple[str, str]:
            if id_token not in tokens:
                raise BadEmailToken("That sign-in could not be verified.")
            address = tokens[id_token]
            for prefix, provider in (("google:", "google.com"), ("password:", "password")):
                if address.startswith(prefix):
                    return address.removeprefix(prefix), provider
            return address, "emailLink"

        monkeypatch.setattr(auth, "verified_email", fake_verify)

        auth.seed_admins()
        db.upsert_user(HR, name="HR User", role="hr")
        return TestClient(main.app)

    return build


@pytest.fixture
def client(make_client):
    return make_client()


# ---------------------------------------------------------------------------


def test_a_listed_address_signs_in(client):
    r = client.post(VERIFY, json={"id_token": "good-token"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == HR
    # And the session actually works, rather than merely being reported.
    assert client.get("/api/runs").status_code == 200


def test_a_genuine_token_for_an_unlisted_address_is_refused(client, tokens):
    """The case the whole design exists for.

    Firebase really did confirm this mailbox. That is not the question.
    """
    tokens["stranger-token"] = "someone@internet.com"
    r = client.post(VERIFY, json={"id_token": "stranger-token"})
    assert r.status_code == 403
    assert client.get("/api/runs").status_code == 401


def test_an_unverifiable_token_is_refused(client):
    r = client.post(VERIFY, json={"id_token": "forged"})
    assert r.status_code == 400
    assert client.get("/api/runs").status_code == 401


def test_a_deactivated_user_cannot_come_back_in_by_link(client):
    """Switching somebody off has to close every door, not just the old ones."""
    db.set_user_active(HR, False)
    r = client.post(VERIFY, json={"id_token": "good-token"})
    assert r.status_code == 403
    assert client.get("/api/runs").status_code == 401


def test_the_address_is_matched_however_it_was_typed(client, tokens, monkeypatch):
    """Firebase may report a different case than the row was stored in."""
    tokens["shouty-token"] = HR.upper()
    r = client.post(VERIFY, json={"id_token": "shouty-token"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == HR


@contextlib.contextmanager
def fake_firebase(claims):
    """Stand in for the firebase_admin SDK, which need not be installed.

    `from firebase_admin import auth` resolves the PARENT package first, so
    registering only firebase_admin.auth is not enough — that was this test
    failing for a reason unrelated to what it is testing.
    """
    from api import firebase

    parent = types.ModuleType("firebase_admin")
    child = types.ModuleType("firebase_admin.auth")
    child.verify_id_token = lambda _token, app=None: claims
    parent.auth = child
    sys.modules["firebase_admin"] = parent
    sys.modules["firebase_admin.auth"] = child
    firebase._app = object()          # skip credential loading
    try:
        yield firebase
    finally:
        firebase._app = None
        sys.modules.pop("firebase_admin.auth", None)
        sys.modules.pop("firebase_admin", None)


def test_an_unconfirmed_address_never_reaches_our_allowlist():
    """`email_verified` is checked in the Firebase layer, not left to callers.

    A Firebase project can hold email/password accounts whose address was never
    proved. Admitting one would let somebody register any address they liked in
    the console and walk in as that person, so the claim is required before the
    address is returned at all.
    """
    with fake_firebase({"email": HR, "email_verified": False}) as firebase:
        with pytest.raises(BadEmailToken):
            firebase.verified_email("anything")


def test_a_token_with_no_address_is_refused():
    """A phone or anonymous Firebase login also produces a valid token."""
    with fake_firebase({"phone_number": "+923001234567"}) as firebase:
        with pytest.raises(BadEmailToken):
            firebase.verified_email("anything")


def test_open_access_admits_a_new_address_by_link(make_client, tokens):
    """The domain and open-access rules are written about email addresses.

    Unlike the phone route, they genuinely apply here — and they have to give
    the SAME answer as the password route, or "who is allowed in" has two
    different definitions depending on which button was pressed.
    """
    client = make_client(open_access=True)
    tokens["newcomer"] = "newcomer@anywhere.com"
    r = client.post(VERIFY, json={"id_token": "newcomer"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "newcomer@anywhere.com"


def test_signing_in_by_link_is_recorded(client):
    """A shortlist has to be explainable months later, whichever door was used."""
    client.post(VERIFY, json={"id_token": "good-token"})
    actions = [e["action"] for e in db.list_audit(20)]
    assert "signed_in_by_email_link" in actions


def test_a_google_sign_in_uses_the_same_allowlist(client, tokens):
    """Google is a second way to prove a mailbox, not a second way in.

    An address Google confirms is still put to the same list. If this ever
    passed for an unlisted address, anyone with a Google account would be
    inside a system holding candidates' CVs.
    """
    tokens["google-listed"] = f"google:{HR}"
    r = client.post(VERIFY, json={"id_token": "google-listed"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == HR

    tokens["google-stranger"] = "google:someone@internet.com"
    assert client.post(VERIFY, json={"id_token": "google-stranger"}).status_code == 403


def test_the_record_says_which_route_was_used(client, tokens):
    """"Signed in" that cannot say how is a weaker record than it looks."""
    tokens["google-listed"] = f"google:{HR}"
    client.post(VERIFY, json={"id_token": "google-listed"})
    client.post(VERIFY, json={"id_token": "good-token"})

    actions = [e["action"] for e in db.list_audit(20)]
    assert "signed_in_with_google" in actions
    assert "signed_in_by_email_link" in actions


def test_a_password_sign_in_is_not_filed_as_a_link(client, tokens):
    """These two fail in different ways, so the log must not merge them.

    A password is reusable by whoever learns it until it is changed; a one-time
    link is not. An investigation that reads "signed in by email link" for what
    was really a password would look for the wrong thing — and Firebase now
    holds the passwords, so this is the ordinary route, not a rare one.
    """
    tokens["password-listed"] = f"password:{HR}"
    assert client.post(VERIFY, json={"id_token": "password-listed"}).status_code == 200

    actions = [e["action"] for e in db.list_audit(20)]
    assert "signed_in_with_password" in actions
    assert "signed_in_by_email_link" not in actions


def test_the_provider_is_read_from_the_token(client):
    """The provider comes out of Firebase's own claims, not from the caller."""
    claims = {
        "email": HR,
        "email_verified": True,
        "firebase": {"sign_in_provider": "google.com"},
    }
    with fake_firebase(claims) as firebase:
        assert firebase.verified_email("anything") == (HR, "google.com")
