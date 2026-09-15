"""
Send one test email, and say plainly what went wrong if it fails.

    python mailtest.py you@example.com

Worth doing before touching the sign-in page: if mail is misconfigured, the
sign-in page says only "the code could not be emailed", which is true but
tells you nothing. This prints the provider's own complaint.

Nothing here prints your API key or password.
"""

from __future__ import annotations

import sys

from api.config import auth_settings as cfg
from api.mailer import MailError, send_code


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    to = argv[0].strip()
    if "@" not in to:
        print(f"  {to!r} does not look like an email address.")
        return 1

    print()
    print(f"  provider : {cfg.email_provider}")
    print(f"  from     : {cfg.email_from}")
    if cfg.email_provider == "smtp":
        print(f"  server   : {cfg.smtp_host}:{cfg.smtp_port}")
        print(f"  username : {cfg.smtp_user or '(none)'}")
        print(f"  password : {'set' if cfg.smtp_password else 'NOT SET'}")
    elif cfg.email_provider == "resend":
        print(f"  api key  : {'set' if cfg.resend_api_key else 'NOT SET'}")
    print(f"  to       : {to}")
    print()

    if cfg.email_provider == "console":
        print("  EMAIL_PROVIDER is still 'console' — nothing will be emailed.")
        print("  Set EMAIL_PROVIDER=smtp or resend in .env first.")
        return 1

    try:
        send_code(to, "123456")
    except MailError as e:
        print("  FAILED\n")
        print(f"  {e}\n")
        _hint(str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED — unexpected error: {e}")
        return 1

    print("  Sent. Check that inbox — the test code is 123456.")
    print("  Nothing in a few minutes? Look in spam.")
    print()
    return 0


def _hint(message: str) -> None:
    m = message.lower()
    if "app password" in m or "authenticationerror" in m or "username and password" in m:
        print("  Gmail needs an App Password, not your normal password.")
        print("  Turn on 2-Step Verification, then create one at:")
        print("      https://myaccount.google.com/apppasswords")
    elif "testing emails" in m or "own email" in m:
        print("  Resend only delivers to your own account's address until you")
        print("  verify a sending domain. Either test with that address, or add")
        print("  a domain under Domains in the Resend dashboard.")
    elif "domain is not verified" in m or "from" in m and "not" in m:
        print("  The From address is not one this provider will send as.")
        print("  On Resend before verifying a domain, use exactly:")
        print("      EMAIL_FROM=CV Shortlist <onboarding@resend.dev>")
    elif "could not reach" in m or "timed out" in m:
        print("  The mail server was unreachable. Check SMTP_HOST and SMTP_PORT,")
        print("  and whether the network blocks outgoing mail (many office")
        print("  networks block port 587).")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
