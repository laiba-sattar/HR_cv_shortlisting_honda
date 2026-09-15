"""
Manage who may sign in.

    python users.py list
    python users.py add ahmed@hondaatlas.com.pk "Ahmed Raza" hr
    python users.py add sara@hondaatlas.com.pk  "Sara Khan"  admin  +923001234567
    python users.py disable ahmed@hondaatlas.com.pk
    python users.py enable  ahmed@hondaatlas.com.pk

Roles
    hr     upload a job advert, rank CVs, read the results
    admin  all of that, plus managing this list and reading the audit log

Access is switched off, never deleted: past rankings record who ran them, and
removing the row would break that record.
"""

from __future__ import annotations

import sys

from api import auth, db


def _print_users() -> None:
    users = db.list_users()
    if not users:
        print("\n  Nobody is on the list yet.")
        print("  Add the first administrator with ADMIN_EMAILS in .env, or:")
        print('      python users.py add you@example.com "Your Name" admin\n')
        return

    print(f"\n  {'':2} {'EMAIL':34} {'NAME':20} {'ROLE':6} PHONE")
    print("  " + "-" * 78)
    for u in users:
        mark = "  " if u["active"] else "✗ "
        print(f"  {mark} {u['email']:34} {u['name'][:20]:20} {u['role']:6} {u['phone'] or ''}")
    off = sum(1 for u in users if not u["active"])
    print(f"\n  {len(users)} listed, {off} switched off\n")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    command, *args = argv

    if command == "list":
        _print_users()
        return 0

    if command == "add":
        if len(args) < 2:
            print('Usage: python users.py add EMAIL "NAME" [hr|admin] [PHONE]')
            return 1
        email = auth.normalise_email(args[0])
        if "@" not in email:
            print(f"  {args[0]!r} does not look like an email address.")
            return 1

        name = args[1]
        role = args[2] if len(args) > 2 else "hr"
        if role not in ("hr", "admin"):
            print(f"  Role must be 'hr' or 'admin', not {role!r}.")
            return 1
        phone = auth.normalise_phone(args[3]) if len(args) > 3 else None

        existing = db.get_user(email)
        db.upsert_user(email, name=name, role=role, phone=phone,
                       active=True, added_by="users.py")
        db.log_audit("users.py", "user_added" if existing is None else "user_updated",
                     detail=f"{email} as {role}")
        print(f"  {'Updated' if existing else 'Added'} {email} ({role})"
              + (f", phone {phone}" if phone else ""))
        return 0

    if command in ("disable", "enable"):
        if not args:
            print(f"Usage: python users.py {command} EMAIL")
            return 1
        email = auth.normalise_email(args[0])
        if db.get_user(email) is None:
            print(f"  {email} is not on the list.")
            return 1

        active = command == "enable"
        db.set_user_active(email, active)
        if not active:
            # An open session must stop working now, not when it expires.
            db.delete_sessions_for(email)
        db.log_audit("users.py", "user_activated" if active else "user_deactivated",
                     detail=email)
        print(f"  {email} is now {'active' if active else 'switched off'}.")
        return 0

    print(f"  Unknown command {command!r}. Try: list, add, disable, enable")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
