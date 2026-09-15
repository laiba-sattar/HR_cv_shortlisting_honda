"""
Sending the sign-in code.

Three backends behind one function, so the choice of mail service is a
setting rather than a rewrite — and so the whole sign-in flow can be built and
tested before any mail account exists.

  console  the code is printed to the server log. Nothing is sent anywhere.
  resend   https://resend.com — 3000 emails a month at no cost
  smtp     any mail server, including Gmail with an app password, or a
           company mail server once IT provides one
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import auth_settings as cfg

log = logging.getLogger("api.mail")


class MailError(RuntimeError):
    pass


SUBJECT = "Your sign-in code: {code}"

BODY_TEXT = """Your sign-in code is: {code}

It expires in {minutes} minutes.

If you did not try to sign in to the CV Shortlisting System, ignore this
email — somebody may have typed your address by mistake.
"""

BODY_HTML = """\
<div style="font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;
            max-width:480px;margin:0 auto;padding:32px 24px;color:#16110f">
  <p style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;
            color:#c21b2c;margin:0 0 20px">HR CV Shortlisting System</p>
  <p style="margin:0 0 8px;font-size:15px">Your sign-in code is</p>
  <p style="font-family:ui-monospace,Consolas,monospace;font-size:34px;
            font-weight:600;letter-spacing:.18em;margin:0 0 20px">{code}</p>
  <p style="margin:0 0 24px;font-size:14px;color:#5b514e">
    It expires in {minutes} minutes.</p>
  <p style="margin:0;font-size:13px;color:#8b807d;border-top:1px solid #e6dedc;
            padding-top:18px">
    If you did not try to sign in, ignore this email — somebody may have typed
    your address by mistake.</p>
</div>
"""


def _send_console(to: str, code: str, minutes: int) -> None:
    # Deliberately loud: this is how you read the code during development, and
    # it must be impossible to mistake a printed code for a delivered one.
    log.warning(
        "\n"
        "  ┌─────────────────────────────────────────────┐\n"
        "  │  SIGN-IN CODE (not emailed — console mode)  │\n"
        "  ├─────────────────────────────────────────────┤\n"
        "  │  %-18s  code: %-6s   │\n"
        "  └─────────────────────────────────────────────┘",
        to[:18], code,
    )


def _send_resend(to: str, code: str, minutes: int) -> None:
    if not cfg.resend_api_key:
        raise MailError("EMAIL_PROVIDER=resend but RESEND_API_KEY is not set.")
    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise MailError("pip install httpx") from e

    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {cfg.resend_api_key}"},
        json={
            "from": cfg.email_from,
            "to": [to],
            "subject": SUBJECT.format(code=code),
            "text": BODY_TEXT.format(code=code, minutes=minutes),
            "html": BODY_HTML.format(code=code, minutes=minutes),
        },
        timeout=15,
    )
    if r.status_code >= 300:
        # The response body says exactly what is wrong — an unverified sending
        # domain, a malformed From address — and hiding it turns a two-minute
        # fix into an afternoon.
        raise MailError(f"Resend refused the message ({r.status_code}): {r.text}")


def _send_smtp(to: str, code: str, minutes: int) -> None:
    if not cfg.smtp_host:
        raise MailError("EMAIL_PROVIDER=smtp but SMTP_HOST is not set.")

    msg = EmailMessage()
    msg["Subject"] = SUBJECT.format(code=code)
    msg["From"] = cfg.email_from
    msg["To"] = to
    msg.set_content(BODY_TEXT.format(code=code, minutes=minutes))
    msg.add_alternative(BODY_HTML.format(code=code, minutes=minutes), subtype="html")

    try:
        if cfg.smtp_port == 465:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
                if cfg.smtp_user:
                    s.login(cfg.smtp_user, cfg.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
                s.starttls()
                if cfg.smtp_user:
                    s.login(cfg.smtp_user, cfg.smtp_password)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise MailError(
            "The mail server rejected the login. For Gmail this usually means "
            "an ordinary password was used — an App Password is required."
        ) from e
    except OSError as e:
        raise MailError(f"Could not reach the mail server: {e}") from e


_BACKENDS = {
    "console": _send_console,
    "resend": _send_resend,
    "smtp": _send_smtp,
}


def send_code(to: str, code: str) -> None:
    """Deliver a sign-in code. Raises MailError if it could not be sent."""
    backend = _BACKENDS.get(cfg.email_provider)
    if backend is None:
        raise MailError(
            f"Unknown EMAIL_PROVIDER {cfg.email_provider!r}. "
            f"Options: {', '.join(_BACKENDS)}"
        )
    backend(to, code, cfg.code_ttl_minutes)
