"""
Passwords: the everyday way in, with the emailed code kept for the two moments
it is actually needed — a first sign-in, and a forgotten password.

The tests below are written around the ways this could wrongly say yes: a
password checked against a database that stored it readably, a wrong password
tried a thousand times, an old session still working after a reset, a reset
performed by somebody who never proved they own the address.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
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
GOOD = "shortlisting tool 2026"
ALSO_GOOD = "another decent passphrase"


@pytest.fixture
def sent():
    return {}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch, sent):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pw.db")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "_schema_ready", False)
    monkeypatch.setattr(db, "_init_lock", threading.Lock())

    cfg = dataclasses.replace(
        auth_settings,
        admin_emails=[ADMIN],
        allowed_domains=[],
        open_access=False,
        secret="test-secret",
        resend_cooldown_seconds=0,
        password_min_length=10,
        password_max_attempts=5,
        password_lockout_minutes=15,
    )
    monkeypatch.setattr(auth, "cfg", cfg)
    monkeypatch.setattr(main, "auth_settings", cfg)
    monkeypatch.setattr(auth, "send_code", lambda to, code: sent.__setitem__(to, code))

    auth.seed_admins()
    db.upsert_user(HR, name="HR User", role="hr")
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


def first_sign_in(client, sent, password=GOOD, email=HR):
    """The first-time route: one screen, then the code that confirms it."""
    r = client.post("/api/auth/signin", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "code_sent"

    r = client.post("/api/auth/email/verify", json={"email": email, "code": sent[email]})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_the_password_is_not_recoverable_from_what_is_stored():
    auth.set_password(HR, GOOD)
    stored = db.get_user(HR)["password_hash"]
    assert GOOD not in stored
    assert stored.startswith("scrypt$"), "expected a slow, salted hash"


def test_two_people_with_the_same_password_get_different_hashes():
    """Per-password salt: otherwise one cracked hash unlocks every account
    that happens to share the password."""
    auth.set_password(HR, GOOD)
    auth.set_password(ADMIN, GOOD)
    assert db.get_user(HR)["password_hash"] != db.get_user(ADMIN)["password_hash"]


def test_a_hash_verifies_only_its_own_password():
    h = auth.hash_password(GOOD)
    assert auth.check_password(GOOD, h)
    assert not auth.check_password(GOOD + " ", h)
    assert not auth.check_password(ALSO_GOOD, h)


def test_a_damaged_hash_never_verifies():
    """A corrupted row must fail closed, not throw or accidentally pass."""
    for broken in ["", "not-a-hash", "scrypt$only$four$parts", "bcrypt$1$2$3$4$5"]:
        assert auth.check_password(GOOD, broken) is False


# ---------------------------------------------------------------------------
# What counts as an acceptable password
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad, because", [
    ("short", "too short"),
    ("password12", "one of the commonest"),
    ("aaaaaaaaaaaa", "too few distinct characters"),
    ("hr hr hr hr hr hr", "contains the address"),
])
def test_weak_passwords_are_refused(bad, because):
    with pytest.raises(auth.WeakPassword):
        auth.validate_password(bad, email=HR, name="HR User")


def test_a_reasonable_passphrase_is_accepted():
    auth.validate_password(GOOD, email=HR, name="HR User")


def test_the_refusal_says_what_to_do():
    with pytest.raises(auth.WeakPassword) as e:
        auth.validate_password("abc", email=HR)
    assert "10 characters" in str(e.value)


# ---------------------------------------------------------------------------
# Signing in with a password
# ---------------------------------------------------------------------------


def test_the_right_password_signs_in():
    auth.set_password(HR, GOOD)
    assert auth.sign_in_with_password(HR, GOOD)["email"] == HR


def test_the_wrong_password_does_not():
    auth.set_password(HR, GOOD)
    with pytest.raises(auth.BadPassword):
        auth.sign_in_with_password(HR, ALSO_GOOD)


def test_an_account_with_no_password_cannot_be_signed_into_with_one():
    with pytest.raises(auth.BadPassword):
        auth.sign_in_with_password(HR, GOOD)


def test_a_deactivated_account_is_refused_even_with_the_right_password():
    auth.set_password(HR, GOOD)
    db.set_user_active(HR, False)
    with pytest.raises(auth.NotAuthorised):
        auth.sign_in_with_password(HR, GOOD)


def test_guessing_locks_the_account():
    """Five wrong tries and it stops — otherwise the password is guessable at
    whatever rate the network allows."""
    auth.set_password(HR, GOOD)
    for _ in range(4):
        with pytest.raises(auth.BadPassword):
            auth.sign_in_with_password(HR, "wrong guess here")

    with pytest.raises(auth.AccountLocked):
        auth.sign_in_with_password(HR, "wrong guess here")

    # Locked means locked: the correct password does not reopen it early.
    with pytest.raises(auth.AccountLocked):
        auth.sign_in_with_password(HR, GOOD)


def test_a_successful_sign_in_clears_the_count():
    auth.set_password(HR, GOOD)
    for _ in range(3):
        with pytest.raises(auth.BadPassword):
            auth.sign_in_with_password(HR, "wrong guess here")
    auth.sign_in_with_password(HR, GOOD)
    assert db.get_user(HR)["failed_logins"] == 0


def test_a_lockout_expires():
    auth.set_password(HR, GOOD)
    past = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat(timespec="seconds")
    db.record_failed_login(HR, past)
    assert auth.sign_in_with_password(HR, GOOD)["email"] == HR


# ---------------------------------------------------------------------------
# The whole journey, over HTTP
# ---------------------------------------------------------------------------


def test_an_unlisted_address_is_turned_away_before_any_email_is_sent(client, sent):
    r = client.post("/api/auth/signin",
                    json={"email": "stranger@internet.com", "password": GOOD})
    assert r.status_code == 403
    assert sent == {}, "no code should be created for an address nobody authorised"


def test_first_time_the_typed_password_is_kept_until_the_code_confirms_it(client, sent):
    r = client.post("/api/auth/signin", json={"email": HR, "password": GOOD})
    assert r.json()["status"] == "code_sent"

    # Not saved yet. Otherwise anybody could set a password on somebody
    # else's address just by typing one on this screen.
    assert db.get_user(HR)["password_hash"] is None

    r = client.post("/api/auth/email/verify", json={"email": HR, "code": sent[HR]})
    assert r.status_code == 200
    assert db.get_user(HR)["password_hash"] is not None


def test_an_unconfirmed_password_never_takes_effect(client, sent):
    """Somebody types a password for an address that is not theirs and walks
    away. The real owner must still be able to choose their own."""
    client.post("/api/auth/signin", json={"email": HR, "password": GOOD})
    assert db.get_user(HR)["password_hash"] is None

    with pytest.raises(auth.BadPassword):
        auth.sign_in_with_password(HR, GOOD)


def test_after_the_first_time_the_same_screen_signs_you_straight_in(client, sent):
    first_sign_in(client, sent)
    client.post("/api/auth/logout")

    fresh = TestClient(main.app)
    r = fresh.post("/api/auth/signin", json={"email": HR, "password": GOOD})
    assert r.status_code == 200
    assert r.json()["status"] == "signed_in", "no second code once a password exists"
    assert fresh.get("/api/runs").status_code == 200


def test_a_weak_password_is_refused_before_an_email_goes_out(client, sent):
    r = client.post("/api/auth/signin", json={"email": HR, "password": "abc"})
    assert r.status_code == 400
    assert "10 characters" in r.json()["detail"]
    assert sent == {}, "do not make somebody fetch a code only to be told the password is weak"


def test_forgotten_password_is_replaced_through_the_emailed_code(client, sent):
    first_sign_in(client, sent)
    client.post("/api/auth/logout")

    fresh = TestClient(main.app)
    assert fresh.post("/api/auth/reset",
                      json={"email": HR, "password": ALSO_GOOD}).status_code == 200
    # The old password still works until the code confirms the new one.
    assert db.get_user(HR)["password_hash"] is not None
    assert auth.check_password(GOOD, db.get_user(HR)["password_hash"])

    fresh.post("/api/auth/email/verify", json={"email": HR, "code": sent[HR]})

    after = TestClient(main.app)
    assert after.post("/api/auth/signin",
                      json={"email": HR, "password": ALSO_GOOD}).json()["status"] == "signed_in"
    assert after.post("/api/auth/signin",
                      json={"email": HR, "password": GOOD}).status_code == 400


def test_a_locked_account_reports_itself_as_locked(client, sent):
    first_sign_in(client, sent)
    client.post("/api/auth/logout")

    for _ in range(5):
        client.post("/api/auth/signin", json={"email": HR, "password": "wrong guess"})

    r = client.post("/api/auth/signin", json={"email": HR, "password": GOOD})
    assert r.status_code == 423, "a lockout is not the same as a wrong password"
    assert "Forgot password" in r.json()["detail"]


def test_a_locked_account_can_still_be_recovered_by_email(client, sent):
    """Otherwise a locked-out person waits fifteen minutes with no way out."""
    first_sign_in(client, sent)
    client.post("/api/auth/logout")
    for _ in range(5):
        client.post("/api/auth/signin", json={"email": HR, "password": "wrong guess"})

    fresh = TestClient(main.app)
    assert fresh.post("/api/auth/reset",
                      json={"email": HR, "password": ALSO_GOOD}).status_code == 200
    assert fresh.post("/api/auth/email/verify",
                      json={"email": HR, "code": sent[HR]}).status_code == 200
    assert fresh.get("/api/runs").status_code == 200


def test_setting_a_password_is_recorded(client, sent):
    first_sign_in(client, sent)
    assert any(e["action"] == "password_set" for e in db.list_audit(50))


def test_wrong_passwords_are_recorded(client, sent):
    auth.set_password(HR, GOOD)
    client.post("/api/auth/signin", json={"email": HR, "password": "wrong guess"})
    assert any(e["action"] == "password_failed" for e in db.list_audit(50))
