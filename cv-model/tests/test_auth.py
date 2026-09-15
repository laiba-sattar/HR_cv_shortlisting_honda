"""
Access control.

This is the code that decides who may read candidates' CVs, so the tests are
written around the ways it could wrongly say yes — an address nobody listed, a
person whose access was withdrawn, a guessed code, a reused code, a request
that skips the login page and calls the API directly.

The happy path matters too, but a login that lets the wrong person in is worse
than one that lets nobody in.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import threading

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ.setdefault("LLM_PROVIDER", "fixture")

from api import auth, db  # noqa: E402
from api.config import auth_settings  # noqa: E402

BOSS = "boss@hondaatlas.com.pk"
HR = "hr@hondaatlas.com.pk"
OUTSIDER = "stranger@internet.com"


@pytest.fixture
def sent():
    """Captures the code that would have been emailed."""
    return {}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch, sent):
    # A fresh database per test, and a fresh connection registry to go with it.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "_schema_ready", False)
    monkeypatch.setattr(db, "_init_lock", threading.Lock())

    monkeypatch.setattr(auth, "cfg", dataclasses.replace(
        auth_settings,
        admin_emails=[BOSS],
        allowed_domains=[],
        open_access=False,
        secret="test-secret-not-a-real-one",
        code_ttl_minutes=10,
        max_attempts=5,
        resend_cooldown_seconds=60,
    ))

    def capture(to, code):
        sent[to] = code

    monkeypatch.setattr(auth, "send_code", capture)
    auth.seed_admins()
    db.upsert_user(HR, name="HR User", role="hr")
    yield


def _use(monkeypatch, **overrides):
    monkeypatch.setattr(auth, "cfg", dataclasses.replace(auth.cfg, **overrides))


# ---------------------------------------------------------------------------
# Who is let in at all
# ---------------------------------------------------------------------------


def test_unlisted_address_is_refused(sent):
    with pytest.raises(auth.NotAuthorised):
        auth.request_code(OUTSIDER)
    assert sent == {}, "no code should be sent to an address nobody authorised"


def test_deactivated_user_is_refused(sent):
    db.set_user_active(HR, False)
    with pytest.raises(auth.NotAuthorised):
        auth.request_code(HR)
    assert sent == {}


def test_explicit_deactivation_beats_an_allowed_domain(monkeypatch, sent):
    """A person switched off stays off, even if their whole domain is allowed.

    Checking the domain first would silently re-admit everyone who had been
    removed — the removal would look like it worked and quietly do nothing.
    """
    _use(monkeypatch, allowed_domains=["hondaatlas.com.pk"])
    db.set_user_active(HR, False)
    with pytest.raises(auth.NotAuthorised):
        auth.request_code(HR)


def test_domain_rule_admits_a_new_colleague(monkeypatch, sent):
    _use(monkeypatch, allowed_domains=["hondaatlas.com.pk"])
    auth.request_code("newjoiner@hondaatlas.com.pk")
    assert "newjoiner@hondaatlas.com.pk" in sent
    assert db.get_user("newjoiner@hondaatlas.com.pk")["role"] == "hr", \
        "someone admitted by a domain rule must not arrive as an administrator"


def test_open_access_admits_anyone(monkeypatch, sent):
    _use(monkeypatch, open_access=True)
    auth.request_code(OUTSIDER)
    assert OUTSIDER in sent


def test_address_case_and_spacing_do_not_matter(sent):
    auth.request_code(f"  {HR.upper()}  ")
    assert HR in sent


# ---------------------------------------------------------------------------
# The code itself
# ---------------------------------------------------------------------------


def test_sign_in_succeeds_with_the_right_code(sent):
    auth.request_code(HR)
    user = auth.verify_code(HR, sent[HR])
    assert user["email"] == HR
    assert user["role"] == "hr"


def test_the_code_is_never_stored_in_readable_form(sent):
    """A stolen database must not hand over working codes."""
    auth.request_code(HR)
    code = sent[HR]
    stored = db.latest_code(HR)["code_hash"]
    assert code not in stored
    assert len(stored) == 64, "expected a hash, not the code"


def test_a_wrong_code_is_rejected_and_counted(sent):
    auth.request_code(HR)
    with pytest.raises(auth.BadCode):
        auth.verify_code(HR, "000000")
    assert db.latest_code(HR)["attempts"] == 1


def test_guessing_is_cut_off_after_the_attempt_limit(sent):
    auth.request_code(HR)
    real = sent[HR]
    for _ in range(5):
        with pytest.raises(auth.BadCode):
            auth.verify_code(HR, "000000")

    # Even the correct code is now refused — the code is spent, not the guesser.
    with pytest.raises(auth.BadCode):
        auth.verify_code(HR, real)


def test_an_expired_code_is_refused(sent, monkeypatch):
    auth.request_code(HR)
    record = db.latest_code(HR)
    past = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat(timespec="seconds")
    db.get_db().execute("UPDATE login_codes SET expires_at=? WHERE id=?", (past, record["id"]))
    db.get_db().commit()

    with pytest.raises(auth.BadCode):
        auth.verify_code(HR, sent[HR])


def test_a_code_cannot_be_used_twice(sent):
    auth.request_code(HR)
    code = sent[HR]
    auth.verify_code(HR, code)
    with pytest.raises(auth.BadCode):
        auth.verify_code(HR, code)


def test_a_code_for_one_person_does_not_work_for_another(sent):
    """The address is mixed into the hash, so codes are not interchangeable."""
    auth.request_code(HR)
    auth.request_code(BOSS)
    with pytest.raises(auth.BadCode):
        auth.verify_code(BOSS, sent[HR])


def test_resend_is_throttled(sent):
    auth.request_code(HR)
    with pytest.raises(auth.TooSoon):
        auth.request_code(HR)


def test_access_withdrawn_between_request_and_verify(sent):
    """The list is checked again at the last moment, not only at the start."""
    auth.request_code(HR)
    db.set_user_active(HR, False)
    with pytest.raises(auth.NotAuthorised):
        auth.verify_code(HR, sent[HR])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, key, value, **kw):
        self.cookies[key] = value

    def delete_cookie(self, key, **kw):
        self.cookies.pop(key, None)


def _signed_in(sent, email=HR):
    auth.request_code(email)
    user = auth.verify_code(email, sent[email])
    resp = FakeResponse()
    return auth.start_session(user, resp)


def test_a_session_identifies_the_user(sent):
    token = _signed_in(sent)
    assert auth.user_for_token(token)["email"] == HR


def test_no_token_is_nobody():
    assert auth.user_for_token(None) is None
    assert auth.user_for_token("made-up-token") is None


def test_signing_out_ends_the_session(sent):
    token = _signed_in(sent)
    auth.end_session(token, FakeResponse())
    assert auth.user_for_token(token) is None


def test_deactivating_a_user_kills_their_live_session(sent):
    """Withdrawing access has to take effect now, not when the session lapses."""
    token = _signed_in(sent)
    assert auth.user_for_token(token) is not None

    db.set_user_active(HR, False)
    assert auth.user_for_token(token) is None


def test_an_expired_session_stops_working(sent):
    token = _signed_in(sent)
    past = (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(timespec="seconds")
    db.get_db().execute("UPDATE sessions SET expires_at=?", (past,))
    db.get_db().commit()
    assert auth.user_for_token(token) is None


def test_the_session_token_is_not_stored_as_given(sent):
    token = _signed_in(sent)
    rows = db.get_db().execute("SELECT token_hash FROM sessions").fetchall()
    assert all(token not in r["token_hash"] for r in rows)


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("written, expected", [
    ("03001234567",      "+923001234567"),
    ("0300 1234567",     "+923001234567"),
    ("+92 300 1234567",  "+923001234567"),
    ("+92-300-1234567",  "+923001234567"),
    ("00923001234567",   "+923001234567"),
    ("923001234567",     "+923001234567"),
])
def test_the_same_number_written_differently_is_one_number(written, expected):
    """Otherwise a listed user is told their own number is not authorised."""
    assert auth.normalise_phone(written) == expected


def test_a_listed_number_is_found_however_it_was_typed():
    db.upsert_user(HR, name="HR User", role="hr",
                   phone=auth.normalise_phone("0300 1234567"))
    found = db.get_user_by_phone(auth.normalise_phone("+92-300-1234567"))
    assert found is not None and found["email"] == HR
