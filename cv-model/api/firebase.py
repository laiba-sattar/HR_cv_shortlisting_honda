"""
Phone sign-in, verified through Firebase.

Firebase sends the SMS and checks the code, which is worth having: sending SMS
to Pakistani networks otherwise means a gateway account, a registered sender ID
and a business relationship nobody has yet.

What Firebase does NOT do is decide who may use this system. It answers one
question — does this phone number belong to the person holding the browser —
and the answer is a signed token. Whether that number is allowed anywhere near
a candidate's CV is decided in api/auth.py, against the same list the email
route uses. Treating a valid Firebase token as permission would admit anybody
in the world who can receive an SMS.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from .config import auth_settings as cfg

log = logging.getLogger("api.firebase")

_app: Any = None
_lock = threading.Lock()


class FirebaseUnavailable(RuntimeError):
    """Phone sign-in is not configured, or the library is not installed."""


class BadPhoneToken(RuntimeError):
    """The token was not accepted, or carries no verified phone number."""


class BadEmailToken(RuntimeError):
    """The token was not accepted, or carries no verified email address."""


def _credentials() -> Any:
    """Read the service account, from a file path or from the JSON itself.

    A deployment usually cannot mount a file, so the whole JSON arrives in an
    environment variable; a laptop usually has the downloaded file. Supporting
    both means the same setting works in both places.
    """
    from firebase_admin import credentials

    raw = cfg.firebase_credentials.strip()
    if not raw:
        raise FirebaseUnavailable("FIREBASE_CREDENTIALS is not set.")

    if raw.startswith("{"):
        try:
            return credentials.Certificate(json.loads(raw))
        except json.JSONDecodeError as e:
            raise FirebaseUnavailable(
                f"FIREBASE_CREDENTIALS looks like JSON but could not be parsed: {e}"
            ) from e

    path = Path(raw)
    if not path.is_file():
        raise FirebaseUnavailable(
            f"FIREBASE_CREDENTIALS points at {raw!r}, which is not a file. "
            "Give the path to the service account JSON, or paste the JSON itself."
        )
    return credentials.Certificate(str(path))


def _get_app() -> Any:
    global _app
    if _app is not None:
        return _app
    with _lock:
        if _app is not None:
            return _app
        try:
            import firebase_admin
        except ImportError as e:
            raise FirebaseUnavailable(
                "Phone sign-in needs the firebase-admin package: pip install firebase-admin"
            ) from e

        _app = firebase_admin.initialize_app(_credentials(), name="cv-shortlist")
        log.info("Firebase phone sign-in is active.")
        return _app


def verified_phone_number(id_token: str) -> str:
    """Return the phone number Firebase confirmed, or raise.

    The token is checked against Google's signing keys — it cannot be forged by
    the browser, which is the whole reason the check happens here rather than
    trusting a number the page sends us.
    """
    from firebase_admin import auth as fb_auth

    app = _get_app()
    try:
        claims = fb_auth.verify_id_token(id_token, app=app)
    except Exception as e:  # noqa: BLE001 — the SDK raises several types
        raise BadPhoneToken(f"That sign-in could not be verified: {e}") from e

    number = (claims.get("phone_number") or "").strip()
    if not number:
        # An email or anonymous Firebase login would also produce a valid
        # token. Accepting one here would let somebody sign in with a Google
        # account and be treated as a verified phone.
        raise BadPhoneToken("That sign-in did not include a verified phone number.")
    return number


def verified_email(id_token: str) -> tuple[str, str]:
    """Return (email address, which provider proved it), or raise.

    This exists because our own mail route cannot reach anybody. Sending a
    one-time code ourselves needs a mail provider that will deliver to an
    arbitrary recipient, and the free tier of the one configured refuses every
    address except the account holder's until a domain is verified — which
    needs a domain nobody here owns. Firebase sends the sign-in link from its
    own infrastructure, to anyone, at no cost.

    `email_verified` is checked, not just `email`. A Firebase project can also
    hold email/password accounts whose address was never confirmed; accepting
    one would let somebody register any address they liked in the Firebase
    console and walk in as that person. The claim is only true after Firebase
    itself has proved the address, which is exactly what the link does.

    The provider is returned as well as the address because the audit trail
    should say HOW somebody got in, not merely that they did. A Google sign-in
    and a one-time emailed link are different events with different failure
    modes, and a log that flattens them into "signed in" cannot answer the
    question it exists for.

    Any Firebase provider that proves an address is accepted — a link, Google,
    whatever is enabled in the console. That is deliberate: they all answer the
    same one question, and the answer to a DIFFERENT question, may this person
    see a CV, is still decided in auth.py against the allowed-users list. A
    verified mailbox has never been permission here and must not become it.
    """
    from firebase_admin import auth as fb_auth

    app = _get_app()
    try:
        claims = fb_auth.verify_id_token(id_token, app=app)
    except Exception as e:  # noqa: BLE001 — the SDK raises several types
        raise BadEmailToken(f"That sign-in could not be verified: {e}") from e

    address = (claims.get("email") or "").strip()
    if not address:
        raise BadEmailToken("That sign-in did not include an email address.")
    if not claims.get("email_verified"):
        raise BadEmailToken("That email address has not been confirmed.")

    provider = str((claims.get("firebase") or {}).get("sign_in_provider") or "firebase")
    return address, provider
