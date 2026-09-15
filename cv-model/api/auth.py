"""
Access control: who may sign in, and proving they did.

Two ways in — a code emailed to an address, or a phone number verified by
Firebase — and both end at the same question, asked here and nowhere else:
*is this person on the list?* Verifying that an address or a number belongs to
somebody is not the same as deciding they may see candidates' CVs, and keeping
those two ideas apart is what stops "anyone who can receive an SMS" from
becoming "anyone who can read the shortlist".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import secrets
from typing import Any, Optional

from fastapi import Cookie, Depends, HTTPException, Response

from . import db
from .firebase import (
    BadEmailToken,
    BadPhoneToken,
    FirebaseUnavailable,
    verified_email,
    verified_phone_number,
)
from .config import auth_settings as cfg
from .mailer import MailError, send_code

log = logging.getLogger("api.auth")

SESSION_COOKIE = cfg.cookie_name


def _now() -> dt.datetime:
    return dt.datetime.now()


def _iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


# Kept re-exported here because callers reach for it alongside
# normalise_email; the definition lives with the column it canonicalises.
normalise_phone = db.normalise_phone


# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------


def seed_admins() -> None:
    """Put the bootstrap admins in the list at startup.

    Without this the system is unusable the moment it is switched on: the
    allowlist is empty, so nobody can sign in, and adding somebody requires
    being signed in.
    """
    for email in cfg.admin_emails:
        email = normalise_email(email)
        if not email:
            continue
        existing = db.get_user(email)
        if existing is None:
            db.upsert_user(email, name=email.split("@")[0], role="admin",
                           added_by="ADMIN_EMAILS")
            log.info("Seeded admin from ADMIN_EMAILS: %s", email)
        elif not existing["active"]:
            # Listed in the environment but switched off in the database. The
            # environment is the operator's stated intent, so it wins.
            db.set_user_active(email, True)
            log.info("Re-enabled admin from ADMIN_EMAILS: %s", email)


class NotAuthorised(Exception):
    """The address or number is genuine but has no access."""


def resolve_user(email: str) -> dict[str, Any]:
    """Return the user record for an address, or raise NotAuthorised.

    Order matters: the explicit list is consulted first, so a person who has
    been switched off stays out even if their domain is allowed.
    """
    email = normalise_email(email)
    if "@" not in email:
        raise NotAuthorised("That does not look like an email address.")

    user = db.get_user(email)
    if user is not None:
        if not user["active"]:
            raise NotAuthorised("This account has been deactivated.")
        return user

    domain = email.split("@")[-1]
    if cfg.open_access or domain in cfg.allowed_domains:
        db.upsert_user(email, name=email.split("@")[0], role="hr",
                       added_by="open_access" if cfg.open_access else "domain_rule")
        log.info("Admitted %s via %s", email,
                 "OPEN_ACCESS" if cfg.open_access else "domain rule")
        return db.get_user(email)

    raise NotAuthorised("This email address is not authorised to use this system.")


# ---------------------------------------------------------------------------
# Sign-in codes
# ---------------------------------------------------------------------------


def _hash_code(email: str, code: str) -> str:
    """Keyed hash, not a plain one.

    A six-digit code has a million possibilities: a plain SHA-256 in a stolen
    database is reversed by trying all of them in under a second. Keying it
    with a secret the database does not hold makes that useless. The address is
    mixed in so a hash cannot be replayed against a different account.
    """
    msg = f"{normalise_email(email)}:{code}".encode()
    return hmac.new(cfg.secret.encode(), msg, hashlib.sha256).hexdigest()


def _new_code() -> str:
    # secrets, not random: the ordinary generator is predictable from a few
    # outputs, which is exactly the guarantee a sign-in code has to make.
    upper = 10 ** cfg.code_length
    return str(secrets.randbelow(upper)).zfill(cfg.code_length)


class TooSoon(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Please wait {seconds}s before requesting another code.")


def request_code(email: str, pending_password: str | None = None) -> dict[str, Any]:
    """Check the allowlist, then send a code. Raises NotAuthorised / TooSoon.

    `pending_password` is the password typed on the sign-in screen. It is
    hashed and parked with the code rather than written to the account, and
    only takes effect when the code comes back verified — otherwise anyone
    could set a password on somebody else's address simply by typing one.
    """
    user = resolve_user(email)
    email = user["email"]

    last = db.latest_code(email)
    if last and not last["used"]:
        age = (_now() - dt.datetime.fromisoformat(last["created_at"])).total_seconds()
        if age < cfg.resend_cooldown_seconds:
            # Not politeness: without this, anybody can use this endpoint to
            # flood somebody else's inbox until their provider blocks us.
            raise TooSoon(int(cfg.resend_cooldown_seconds - age))

    pending_hash = None
    if pending_password is not None:
        # Checked before the email goes out. Finding out the password is too
        # weak only after fetching a code from your inbox is a poor way to
        # learn it.
        validate_password(pending_password, email=email, name=user["name"])
        pending_hash = hash_password(pending_password)

    code = _new_code()
    now = _now()
    expires = now + dt.timedelta(minutes=cfg.code_ttl_minutes)
    db.insert_code(email, _hash_code(email, code), _iso(now), _iso(expires),
                   pending_password_hash=pending_hash)

    send_code(email, code)          # MailError propagates: a code nobody
                                    # received must not look like success.
    db.log_audit(email, "login_code_sent")
    return {"email": email, "expires_in_minutes": cfg.code_ttl_minutes}


class BadCode(Exception):
    pass


def verify_code(email: str, code: str) -> dict[str, Any]:
    """Check a submitted code and return the user. Raises BadCode."""
    user = resolve_user(email)          # re-checked: access can be withdrawn
    email = user["email"]               # between requesting and submitting

    record = db.latest_code(email)
    if record is None or record["used"]:
        raise BadCode("That code is not valid. Request a new one.")

    if _now() > dt.datetime.fromisoformat(record["expires_at"]):
        raise BadCode("That code has expired. Request a new one.")

    if record["attempts"] >= cfg.max_attempts:
        raise BadCode("Too many incorrect attempts. Request a new code.")

    supplied = "".join(ch for ch in (code or "") if ch.isdigit())
    # compare_digest, not ==: a plain comparison stops at the first wrong
    # character, and the time it takes leaks how much of the code was right.
    if not hmac.compare_digest(_hash_code(email, supplied), record["code_hash"]):
        db.bump_code_attempts(record["id"])
        left = cfg.max_attempts - record["attempts"] - 1
        raise BadCode(
            f"That code is not correct. {left} attempt{'' if left == 1 else 's'} left."
            if left > 0 else "That code is not correct. Request a new one."
        )

    db.mark_code_used(record["id"])

    pending = record["pending_password_hash"]
    if pending:
        # Ownership of the address is now proven, so the password chosen on
        # the sign-in screen can take effect.
        db.set_password_hash(email, pending, _iso(_now()))
        db.log_audit(email, "password_set")
        user = db.get_user(email)

    return user


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
#
# A new account has none. The first sign-in uses an emailed code, the person
# chooses a password, and that is what they use from then on. Forgetting it
# sends them back through the same emailed code. So the code machinery above
# serves both jobs and there is no second way in to secure.


class WeakPassword(Exception):
    pass


class AccountLocked(Exception):
    def __init__(self, minutes: int):
        self.minutes = minutes
        super().__init__(
            f"Too many incorrect attempts. Try again in {minutes} minute"
            f"{'' if minutes == 1 else 's'}, or use 'Forgot password'."
        )


# scrypt, from the standard library — no extra dependency, and unlike a plain
# SHA-256 it is deliberately slow and memory-hungry, so a stolen database
# cannot be run through a password list at speed.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, pp, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(pp), dklen=len(bytes.fromhex(digest_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# Long and unguessable beats short and full of punctuation: a length floor plus
# a check against the obvious choices catches far more real-world bad passwords
# than a rule demanding a capital and a symbol, which mostly produces
# "Password1!".
_OBVIOUS = {
    "12345678", "123456789", "1234567890", "qwertyuiop", "qwerty123",
    "abc12345", "iloveyou", "passw0rd",
}

# Checked after trailing digits and punctuation are stripped, because a length
# rule mostly makes people pad a familiar word: "password" fails, so they type
# "password12", which is no harder to guess. Comparing the stem catches the
# whole family — password1, password123, honda2026, welcome!! — instead of
# only the exact strings someone remembered to list.
_COMMON_STEMS = {
    "password", "pass", "welcome", "letmein", "login", "admin", "administrator",
    "qwerty", "abcdef", "changeme", "secret", "master", "monkey", "dragon",
    "sunshine", "princess", "superman", "trustno", "football", "iloveyou",
    "honda", "hondaatlas", "atlas", "shortlist", "cvshortlist", "cv", "hr",
}


def validate_password(password: str, email: str = "", name: str = "") -> None:
    """Raise WeakPassword with a message the person can act on."""
    pw = (password or "").strip()
    if len(pw) < cfg.password_min_length:
        raise WeakPassword(
            f"Use at least {cfg.password_min_length} characters. "
            "A short phrase you will remember works well."
        )
    if len(pw) > 200:
        raise WeakPassword("That password is too long — 200 characters is the limit.")

    flat = pw.lower().replace(" ", "")
    if flat in _OBVIOUS:
        raise WeakPassword("That is one of the most commonly used passwords. Pick another.")

    stem = flat.rstrip("0123456789!@#$%^&*._-")
    if stem in _COMMON_STEMS:
        raise WeakPassword(
            "That is a very common password with numbers on the end. "
            "A short phrase of a few unrelated words is far harder to guess."
        )

    if flat.isdigit():
        # Ten digits looks long but is usually a phone number or a date.
        raise WeakPassword("Use more than just numbers.")

    if len(set(flat)) < 4:
        raise WeakPassword("That password repeats too few different characters.")

    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in flat:
        raise WeakPassword("Do not use your email address in your password.")
    for part in (name or "").lower().split():
        if len(part) >= 4 and part in flat:
            raise WeakPassword("Do not use your name in your password.")


def set_password(email: str, password: str) -> None:
    user = resolve_user(email)
    validate_password(password, email=user["email"], name=user["name"])
    db.set_password_hash(user["email"], hash_password(password), _iso(_now()))
    db.log_audit(user["email"], "password_set")


def has_password(email: str) -> bool:
    user = db.get_user(normalise_email(email))
    return bool(user and user["password_hash"])


def _lock_remaining(user: dict[str, Any]) -> int:
    """Minutes left on a lockout, 0 if not locked."""
    until = user.get("locked_until")
    if not until:
        return 0
    left = (dt.datetime.fromisoformat(until) - _now()).total_seconds()
    return max(0, int(left // 60) + (1 if left % 60 else 0))


class BadPassword(Exception):
    pass


def begin_sign_in(email: str, password: str) -> dict[str, Any]:
    """One screen, one button: an address and a password.

    What happens next depends on the account, not on the person guessing which
    form to use. Somebody who has signed in before is let straight in.
    Somebody who has not is emailed a code, and the password they just typed
    becomes theirs once that code comes back.
    """
    user = resolve_user(email)

    locked = _lock_remaining(user)
    if locked:
        raise AccountLocked(locked)

    if user["password_hash"]:
        return {"status": "signed_in", "user": sign_in_with_password(email, password)}

    request_code(user["email"], pending_password=password)
    return {"status": "code_sent", "email": user["email"],
            "expires_in_minutes": cfg.code_ttl_minutes}


def begin_reset(email: str, password: str) -> dict[str, Any]:
    """Forgotten password: choose the new one, then prove the address."""
    user = resolve_user(email)
    request_code(user["email"], pending_password=password)
    return {"status": "code_sent", "email": user["email"],
            "expires_in_minutes": cfg.code_ttl_minutes}


def sign_in_with_password(email: str, password: str) -> dict[str, Any]:
    """Check a password. Raises NotAuthorised / AccountLocked / BadPassword."""
    user = resolve_user(email)

    locked = _lock_remaining(user)
    if locked:
        raise AccountLocked(locked)

    if not user["password_hash"]:
        # No password yet — the caller should be sending them through the
        # emailed-code route, not asking for one they never chose.
        raise BadPassword("This account has no password yet. Use the emailed code to set one.")

    if not check_password(password or "", user["password_hash"]):
        until = None
        if user["failed_logins"] + 1 >= cfg.password_max_attempts:
            until = _iso(_now() + dt.timedelta(minutes=cfg.password_lockout_minutes))
        count = db.record_failed_login(user["email"], until)
        db.log_audit(user["email"], "password_failed", detail=f"attempt {count}")
        if until:
            raise AccountLocked(cfg.password_lockout_minutes)
        left = cfg.password_max_attempts - count
        raise BadPassword(
            f"That password is not correct. {left} attempt{'' if left == 1 else 's'} "
            "left before the account is locked."
        )

    db.clear_failed_logins(user["email"])
    return user


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    # A session token is 32 random bytes, so guessing it is hopeless and a
    # plain hash is enough — unlike the six-digit code above.
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(user: dict[str, Any], response: Response) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + dt.timedelta(hours=cfg.session_hours)
    db.create_session(_hash_token(token), user["email"], _iso(now), _iso(expires))

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=cfg.session_hours * 3600,
        httponly=True,      # script on the page cannot read it, so an
                            # injected script cannot steal the session
        samesite="lax",     # not sent on cross-site requests
        secure=cfg.cookie_secure,
        path="/",
    )
    db.log_audit(user["email"], "signed_in")
    db.purge_expired(_iso(now))
    return token


def end_session(token: Optional[str], response: Response) -> None:
    if token:
        db.delete_session(_hash_token(token))
    response.delete_cookie(SESSION_COOKIE, path="/")


def user_for_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    session = db.get_session(_hash_token(token))
    if session is None:
        return None

    now = _now()
    if now > dt.datetime.fromisoformat(session["expires_at"]):
        db.delete_session(session["token_hash"])
        return None

    user = db.get_user(session["email"])
    if user is None or not user["active"]:
        # Access withdrawn while signed in. The session dies now rather than
        # running until it expires.
        db.delete_session(session["token_hash"])
        return None

    db.touch_session(session["token_hash"], _iso(now))
    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def current_user(session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)) -> dict[str, Any]:
    """Require a signed-in user. Use on every endpoint that touches CV data."""
    user = user_for_token(session)
    if user is None:
        raise HTTPException(401, "Not signed in.")
    return user


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(403, "This action needs an administrator account.")
    return user


def optional_user(session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)):
    """For endpoints that behave differently when signed in but do not require it."""
    return user_for_token(session)


# ---------------------------------------------------------------------------
# Phone sign-in
# ---------------------------------------------------------------------------
def sign_in_with_phone(id_token: str) -> dict[str, Any]:
    """Turn a Firebase phone token into one of our users, or refuse.

    Firebase proves that the person holding the browser controls that number.
    It does not, and must not, decide whether they may see candidates' CVs —
    otherwise anybody in the world who can receive an SMS is inside. The number
    still has to be on the same list an email address is checked against.

    There is no auto-creation here even when `open_access` or a domain rule is
    on: those rules are written in terms of email addresses, and a phone number
    carries no domain to match. An unlisted number is refused, full stop.
    """
    number = normalise_phone(verified_phone_number(id_token))
    if not number:
        raise NotAuthorised("That sign-in did not include a usable phone number.")

    user = db.get_user_by_phone(number)
    if user is None:
        raise NotAuthorised(
            "This phone number is not authorised to use this system. "
            "An administrator has to add it to your account first."
        )
    if not user["active"]:
        raise NotAuthorised("This account has been deactivated.")

    db.log_audit(user["email"], "signed_in_by_phone")
    return user


__all__ = [
    "AccountLocked", "BadCode", "BadPassword", "MailError", "NotAuthorised",
    "TooSoon", "WeakPassword", "BadPhoneToken", "BadEmailToken", "FirebaseUnavailable",
    "check_password", "hash_password", "has_password", "set_password",
    "begin_reset", "begin_sign_in", "sign_in_with_password", "validate_password",
    "sign_in_with_phone",
    "SESSION_COOKIE",
    "current_user", "require_admin", "optional_user",
    "request_code", "verify_code", "resolve_user", "seed_admins",
    "start_session", "end_session", "user_for_token",
    "normalise_email", "normalise_phone",
]


def sign_in_with_firebase_email(id_token: str) -> dict[str, Any]:
    """Turn a Firebase token carrying a verified address into one of our users.

    One function for every Firebase route that proves an EMAIL — the one-time
    link and Google are the two switched on today. They are not separate doors:
    each answers "does this person control this mailbox", and the answer is
    then put to the same allowlist. Writing one per provider would mean the
    rule about who may come in lived in several places, and rules that live in
    several places drift apart.

    Unlike the phone route, `open_access` and the domain rule DO apply here.
    Those rules are written in terms of email addresses, so an address that
    satisfies one is admitted exactly as it would be on the password route —
    `resolve_user` is the single place that decision lives.
    """
    address, provider = verified_email(id_token)
    address = normalise_email(address)
    if not address:
        raise NotAuthorised("That sign-in did not include a usable email address.")

    user = resolve_user(address)          # raises NotAuthorised when unlisted
    # Named per provider: "signed in" that cannot say how is a weaker record.
    action = {
        "google.com": "signed_in_with_google",
        "emailLink": "signed_in_by_email_link",
        # Its own name. This used to be filed under "email link", which was
        # wrong in the way that matters: the log exists to answer "how did
        # this person get in", and a password sign-in and a one-time link
        # fail in completely different ways. A stolen password is reusable
        # until it is changed; a link is not.
        "password": "signed_in_with_password",
    }.get(provider, "signed_in_by_firebase")
    db.log_audit(user["email"], action, detail=provider)
    return user
