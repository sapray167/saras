"""Start SARAS with NO demo data: one admin login and one current semester, nothing else.

    python -m app.clean --yes                      # wipes the database, admin / admin123
    python -m app.clean --yes --password MyPass1   # choose the admin password
    python -m app.clean --yes --semester "Fall 2026" --start 2026-08-01 --end 2026-12-31

WARNING: this deletes every table's data. Then sign in as admin and add departments, faculty,
students and courses from the Admin page.
"""
import argparse
from datetime import date

from . import create_app
from .extensions import db
from .models import Semester, User


def default_semester(today=None):
    t = today or date.today()
    if t.month >= 7:
        return f"Fall {t.year}", date(t.year, 8, 1), date(t.year, 12, 31)
    return f"Spring {t.year}", date(t.year, 1, 1), date(t.year, 6, 30)


def run(password="admin123", semester=None, start=None, end=None):
    name, s, e = default_semester()
    name, s, e = semester or name, start or s, end or e
    db.drop_all()
    db.create_all()
    admin = User(username="admin", role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.add(Semester(name=name, term_no=1, start_date=s, end_date=e, is_current=True))
    db.session.commit()
    return name


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="confirm that ALL existing data will be deleted")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--semester")
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    a = ap.parse_args()
    if not a.yes:
        raise SystemExit("This deletes ALL data. Re-run with --yes to confirm.")
    with create_app().app_context():
        n = run(a.password, a.semester, a.start, a.end)
    print(f"Clean database ready. Semester '{n}'. Sign in as admin / {a.password} at /login")
