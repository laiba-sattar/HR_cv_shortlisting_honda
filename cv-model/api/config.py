"""
Settings for the API layer — access control, sign-in codes, sessions, email.

Kept apart from cv_ranker/config.py on purpose: that file configures the
ranking model, this one configures who is allowed to use it. They change for
completely different reasons and are reviewed by different people.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

log = logging.getLogger("api.config")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    raw = _env(key)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _list(key: str) -> list[str]:
    return [p.strip().lower() for p in _env(key).split(",") if p.strip()]


def _session_secret() -> str:
    """Key for hashing sign-in codes.

    A sign-in code is six digits — a million possibilities, which a plain
    SHA-256 of the code would give up instantly to anyone who read the
    database. Hashing it with a secret the database does not contain means a
    stolen database yields no usable codes.

    If none is configured, a random one is generated for this process. That is
    safe, but every restart invalidates outstanding codes and sessions, so
    production should set one.
    """
    configured = _env("SESSION_SECRET")
    if configured:
        return configured
    log.warning(
        "SESSION_SECRET is not set — using a random key for this process. "
        "Sign-in codes and sessions will not survive a restart. Set "
        "SESSION_SECRET in .env (any long random string) to fix this."
    )
    return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class AuthSettings:
    # --- Who may sign in --------------------------------------------------
    # Emails seeded as admins on startup, so the first person can get in
    # before anyone exists to grant access — otherwise the system locks
    # everyone out permanently the moment it is switched on.
    admin_emails: list[str] = field(default_factory=lambda: _list("ADMIN_EMAILS"))
    # Anyone at these domains is admitted without being listed individually.
    # Empty means the explicit list is the only way in.
    allowed_domains: list[str] = field(default_factory=lambda: _list("ALLOWED_EMAIL_DOMAINS"))
    # Testing escape hatch: admit any address at all. The UI shows a warning
    # banner whenever this is on, because it is the kind of setting that gets
    # switched on for an afternoon and left on for a year.
    open_access: bool = field(default_factory=lambda: _bool("OPEN_ACCESS", False))
    # Tell an unlisted visitor plainly that they are not authorised. Turning
    # this off returns the same answer either way, so nobody can discover who
    # has access by trying addresses.
    reveal_unauthorised: bool = field(
        default_factory=lambda: _bool("REVEAL_UNAUTHORISED", True)
    )

    # --- Sign-in codes ----------------------------------------------------
    secret: str = field(default_factory=_session_secret)
    code_length: int = field(default_factory=lambda: int(_env("OTP_LENGTH", "6")))
    code_ttl_minutes: int = field(default_factory=lambda: int(_env("OTP_TTL_MINUTES", "10")))
    # After this many wrong guesses the code dies. Six digits is only a
    # million combinations; without a cap a script walks through them.
    max_attempts: int = field(default_factory=lambda: int(_env("OTP_MAX_ATTEMPTS", "5")))
    # Minimum gap between codes for one address, so nobody can be used to
    # flood someone else's inbox.
    resend_cooldown_seconds: int = field(
        default_factory=lambda: int(_env("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    )

    # --- Passwords --------------------------------------------------------
    # A length floor rather than a symbol-and-capital rule: the second mostly
    # produces "Password1!", which is on every guessing list.
    password_min_length: int = field(default_factory=lambda: int(_env("PASSWORD_MIN_LENGTH", "10")))
    password_max_attempts: int = field(default_factory=lambda: int(_env("PASSWORD_MAX_ATTEMPTS", "5")))
    password_lockout_minutes: int = field(
        default_factory=lambda: int(_env("PASSWORD_LOCKOUT_MINUTES", "15"))
    )

    # --- Sessions ---------------------------------------------------------
    session_hours: int = field(default_factory=lambda: int(_env("SESSION_HOURS", "8")))
    cookie_name: str = field(default_factory=lambda: _env("SESSION_COOKIE", "cv_session"))
    # Off for local http development; on wherever the site is served over
    # https, which includes every real deployment.
    cookie_secure: bool = field(default_factory=lambda: _bool("SESSION_COOKIE_SECURE", False))

    # --- Email ------------------------------------------------------------
    # console -> print the code to the server log. No account, no setup, and
    #            the whole sign-in flow can be exercised offline.
    # resend  -> https://resend.com, 3000 free emails a month
    # smtp    -> any mail server, including Gmail with an app password
    email_provider: str = field(default_factory=lambda: _env("EMAIL_PROVIDER", "console").lower())
    email_from: str = field(
        default_factory=lambda: _env("EMAIL_FROM", "CV Shortlist <onboarding@resend.dev>")
    )
    resend_api_key: str = field(default_factory=lambda: _env("RESEND_API_KEY"))
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))

    # --- Phone (Firebase) -------------------------------------------------
    # Path to the service account JSON, or the JSON itself. Empty disables
    # phone sign-in, and the login page hides that option rather than
    # offering a button that cannot work.
    firebase_credentials: str = field(default_factory=lambda: _env("FIREBASE_CREDENTIALS"))

    @property
    def phone_enabled(self) -> bool:
        return bool(self.firebase_credentials)

    def warnings(self) -> list[str]:
        """Configuration that is fine locally but wrong in a deployment."""
        out: list[str] = []
        if self.open_access:
            out.append(
                "OPEN_ACCESS is on — anyone who reaches this site can sign in. "
                "Do not process real candidate CVs while it is on."
            )
        if self.email_provider == "console":
            out.append(
                "EMAIL_PROVIDER=console — sign-in codes are printed to the server "
                "log instead of being emailed. Development only."
            )
        if not self.admin_emails and not self.allowed_domains and not self.open_access:
            out.append(
                "No ADMIN_EMAILS, no ALLOWED_EMAIL_DOMAINS and OPEN_ACCESS is off — "
                "nobody can sign in."
            )
        return out


auth_settings = AuthSettings()
