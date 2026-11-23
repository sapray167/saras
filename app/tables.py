"""Show the database from the terminal (works for SQLite and MySQL).

    python -m app.tables                 # every table with its columns and row count
    python -m app.tables student         # first 20 rows of one table
    python -m app.tables student 100     # first 100 rows
"""
import sys

from sqlalchemy import inspect, text

from . import create_app
from .extensions import db


def _fmt(rows, cols):
    data = [[("" if v is None else str(v))[:28] for v in r] for r in rows]
    w = [max(len(c), *(len(r[i]) for r in data)) if data else len(c) for i, c in enumerate(cols)]
    line = "  ".join(c.ljust(w[i]) for i, c in enumerate(cols))
    print(line + "\n" + "-" * len(line))
    for r in data:
        print("  ".join(v.ljust(w[i]) for i, v in enumerate(r)))


def main(argv):
    with create_app().app_context():
        insp = inspect(db.engine)
        names = sorted(insp.get_table_names())
        if not argv:
            print(f"Database: {db.engine.url.render_as_string(hide_password=True)}\n{len(names)} tables\n")
            for n in names:
                count = db.session.execute(text(f'SELECT COUNT(*) FROM "{n}"' if db.engine.dialect.name == "sqlite" else f"SELECT COUNT(*) FROM `{n}`")).scalar()
                print(f"{n}  ({count} rows)")
                for c in insp.get_columns(n):
                    print(f"    {c['name']:<18} {str(c['type'])}")
                print()
            return
        t = argv[0]
        if t not in names:
            raise SystemExit(f"No table '{t}'. Tables: {', '.join(names)}")
        limit = int(argv[1]) if len(argv) > 1 else 20
        q = f'SELECT * FROM "{t}" LIMIT {limit}' if db.engine.dialect.name == "sqlite" else f"SELECT * FROM `{t}` LIMIT {limit}"
        res = db.session.execute(text(q))
        _fmt(res.fetchall(), list(res.keys()))


if __name__ == "__main__":
    main(sys.argv[1:])
