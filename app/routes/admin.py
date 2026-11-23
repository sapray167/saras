import re
from datetime import time

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import (Attendance, Course, CourseOffering, Department, Enrollment, Faculty, Semester, Student,
                      TimetableSlot, User)
from ..services import analytics, integrity
from ..services.enrollment import check_enroll
from . import api_error, login_required

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _need(data, *fields):
    missing = [f for f in fields if not str(data.get(f, "")).strip()]
    return f"Missing: {', '.join(missing)}." if missing else None


@bp.get("/overview")
@login_required("admin")
def overview(user):
    return jsonify(analytics.admin_overview())


# ------------------------------------------------------------ departments
@bp.get("/departments")
@login_required("admin")
def departments(user):
    return jsonify([{"id": d.id, "code": d.code, "name": d.name} for d in Department.query.order_by(Department.code)])


@bp.post("/departments")
@login_required("admin")
def department_add(user):
    d = request.get_json(silent=True) or {}
    if (err := _need(d, "code", "name")):
        return api_error(err)
    code = d["code"].strip().upper()[:10]
    if Department.query.filter_by(code=code).first():
        return api_error(f"Department {code} already exists.", 409)
    db.session.add(Department(code=code, name=d["name"].strip()[:120]))
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.delete("/departments/<int:did>")
@login_required("admin")
def department_delete(user, did):
    d = db.session.get(Department, did)
    if not d:
        return api_error("Department not found.", 404)
    if any(m.query.filter_by(department_id=did).first() for m in (Student, Faculty, Course)):
        return api_error("Department still has students, faculty or courses.", 409)
    db.session.delete(d)
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- students
@bp.get("/students")
@login_required("admin")
def students(user):
    q = (request.args.get("q") or "").strip()
    query = Student.query.join(Department)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Student.name.ilike(like), Student.roll_no.ilike(like), Department.code.ilike(like)))
    page, per = request.args.get("page", 1, type=int), 25
    total = query.count()
    rows = query.order_by(Student.roll_no).offset((page - 1) * per).limit(per).all()
    return jsonify({"total": total, "page": page, "per_page": per,
                    "items": [{"id": s.id, "roll_no": s.roll_no, "name": s.name, "email": s.email,
                               "department": s.department.code, "admission_year": s.admission_year} for s in rows]})


@bp.post("/students")
@login_required("admin")
def student_add(user):
    d = request.get_json(silent=True) or {}
    if (err := _need(d, "roll_no", "name", "email", "department_id", "password")):
        return api_error(err)
    if not EMAIL.match(d["email"]):
        return api_error("Enter a valid email address.")
    if len(d["password"]) < 6:
        return api_error("Password must be at least 6 characters.")
    roll = str(d["roll_no"]).strip()
    if Student.query.filter_by(roll_no=roll).first() or User.query.filter_by(username=roll.lower()).first():
        return api_error(f"Roll number {roll} already exists.", 409)
    if Student.query.filter_by(email=d["email"].lower()).first():
        return api_error("That email is already used.", 409)
    if not db.session.get(Department, d["department_id"]):
        return api_error("Please choose a department. If the list is empty, add a department first (Departments tab).")
    u = User(username=roll.lower(), role="student")
    u.set_password(d["password"])
    db.session.add(u)
    db.session.flush()
    db.session.add(Student(user_id=u.id, roll_no=roll, name=d["name"].strip()[:120], email=d["email"].lower(),
                           department_id=d["department_id"], admission_year=int(d.get("admission_year") or 2024)))
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.delete("/students/<int:sid>")
@login_required("admin")
def student_delete(user, sid):
    s = db.session.get(Student, sid)
    if not s:
        return api_error("Student not found.", 404)
    for e in Enrollment.query.filter_by(student_id=sid).all():
        db.session.delete(e)
    uid = s.user_id
    db.session.delete(s)
    db.session.flush()
    if uid:
        db.session.delete(db.session.get(User, uid))
    db.session.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------- faculty
@bp.get("/faculty")
@login_required("admin")
def faculty_list(user):
    return jsonify([{"id": f.id, "name": f.name, "email": f.email, "department": f.department.code,
                     "designation": f.designation, "username": f.user.username if f.user else None}
                    for f in Faculty.query.order_by(Faculty.name)])


@bp.post("/faculty")
@login_required("admin")
def faculty_add(user):
    d = request.get_json(silent=True) or {}
    if (err := _need(d, "name", "email", "username", "department_id", "password")):
        return api_error(err)
    if not EMAIL.match(d["email"]):
        return api_error("Enter a valid email address.")
    if User.query.filter_by(username=d["username"].strip().lower()).first():
        return api_error("That username is taken.", 409)
    if Faculty.query.filter_by(email=d["email"].lower()).first():
        return api_error("That email is already used.", 409)
    if not db.session.get(Department, d["department_id"]):
        return api_error("Please choose a department. If the list is empty, add a department first (Departments tab).")
    u = User(username=d["username"].strip().lower(), role="faculty")
    u.set_password(d["password"])
    db.session.add(u)
    db.session.flush()
    db.session.add(Faculty(user_id=u.id, department_id=d["department_id"], name=d["name"].strip()[:120],
                           email=d["email"].lower(), designation=(d.get("designation") or "Assistant Professor")[:60]))
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.delete("/faculty/<int:fid>")
@login_required("admin")
def faculty_delete(user, fid):
    f = db.session.get(Faculty, fid)
    if not f:
        return api_error("Faculty not found.", 404)
    if CourseOffering.query.filter_by(faculty_id=fid).first():
        return api_error("This faculty member still teaches courses. Reassign them first.", 409)
    uid = f.user_id
    db.session.delete(f)
    db.session.flush()
    if uid:
        db.session.delete(db.session.get(User, uid))
    db.session.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------- courses
@bp.get("/courses")
@login_required("admin")
def courses(user):
    cur = analytics.current_semester()
    rows = []
    for c in Course.query.order_by(Course.code).all():
        o = CourseOffering.query.filter_by(course_id=c.id, semester_id=cur.id).first()
        rows.append({"id": c.id, "code": c.code, "name": c.name, "credits": c.credits, "department": c.department.code,
                     "offering_id": o.id if o else None, "faculty": o.faculty.name if o else None,
                     "enrolled": Enrollment.query.filter_by(offering_id=o.id).count() if o else 0})
    return jsonify({"semester": cur.name, "items": rows})


@bp.post("/courses")
@login_required("admin")
def course_add(user):
    """Create a course and offer it this semester. slots: [{day:0-4,start:'HH:MM',end:'HH:MM',room}]"""
    d = request.get_json(silent=True) or {}
    if (err := _need(d, "code", "name", "department_id", "faculty_id")):
        return api_error(err)
    code = d["code"].strip().upper()
    if Course.query.filter_by(code=code).first():
        return api_error(f"Course {code} already exists.", 409)
    if not db.session.get(Faculty, d["faculty_id"]) or not db.session.get(Department, d["department_id"]):
        return api_error("Please choose a faculty member and a department. If a list is empty, add a faculty member / department first.")
    try:
        credits = int(d.get("credits") or 3)
    except ValueError:
        return api_error("Credits must be a number.")
    if not 1 <= credits <= 6:
        return api_error("Credits must be between 1 and 6.")
    c = Course(code=code, name=d["name"].strip()[:120], credits=credits, department_id=d["department_id"])
    db.session.add(c)
    db.session.flush()
    o = CourseOffering(course_id=c.id, semester_id=analytics.current_semester().id, faculty_id=d["faculty_id"],
                       capacity=int(d.get("capacity") or 60))
    db.session.add(o)
    db.session.flush()
    for s in d.get("slots") or []:
        try:
            sh, sm = map(int, s["start"].split(":"))
            eh, em = map(int, s["end"].split(":"))
            assert 0 <= s["day"] <= 4 and time(sh, sm) < time(eh, em)
        except (KeyError, ValueError, AssertionError, AttributeError):
            db.session.rollback()
            return api_error("Each slot needs a weekday (0-4) and valid start < end times (HH:MM).")
        db.session.add(TimetableSlot(offering_id=o.id, day=s["day"], start_time=time(sh, sm), end_time=time(eh, em),
                                     room=(s.get("room") or "")[:20]))
    db.session.commit()
    return jsonify({"ok": True}), 201


# ------------------------------------------------------------- enrollments
@bp.post("/enrollments")
@login_required("admin")
def enroll(user):
    d = request.get_json(silent=True) or {}
    st, o = db.session.get(Student, d.get("student_id")), db.session.get(CourseOffering, d.get("offering_id"))
    if not st or not o:
        return api_error("Unknown student or course offering.", 404)
    errors, warnings = check_enroll(st, o)
    if errors:
        return api_error(errors[0], 409, errors=errors)
    if warnings and not d.get("allow_clash"):
        return api_error(warnings[0], 409, code="clash", warnings=warnings)
    db.session.add(Enrollment(student_id=st.id, offering_id=o.id))
    db.session.commit()
    return jsonify({"ok": True}), 201


# --------------------------------------------------------------- integrity
@bp.get("/integrity")
@login_required("admin")
def integrity_list(user):
    return jsonify({"alerts": integrity.scan()})


@bp.post("/integrity/<path:alert_id>/resolve")
@login_required("admin")
def integrity_resolve(user, alert_id):
    if not integrity.resolve(alert_id, user.username):
        return api_error("Alert not found.", 404)
    return jsonify({"ok": True})


# ---------------------------------------------------------- database viewer
HIDDEN_COLUMNS = {"password_hash"}


@bp.get("/db/tables")
@login_required("admin")
def db_tables(user):
    """Every table with its columns and row count (read-only)."""
    out = []
    for tbl in db.metadata.sorted_tables:
        n = db.session.execute(db.select(func.count()).select_from(tbl)).scalar()
        out.append({"name": tbl.name, "rows": n, "columns": [c.name for c in tbl.columns if c.name not in HIDDEN_COLUMNS]})
    return jsonify({"tables": sorted(out, key=lambda x: x["name"])})


@bp.get("/db/tables/<name>")
@login_required("admin")
def db_table_rows(user, name):
    tbl = db.metadata.tables.get(name)
    if tbl is None:
        return api_error("No such table.", 404)
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    offset = max(request.args.get("offset", 0, type=int), 0)
    cols = [c for c in tbl.columns if c.name not in HIDDEN_COLUMNS]
    total = db.session.execute(db.select(func.count()).select_from(tbl)).scalar()
    rows = db.session.execute(db.select(*cols).order_by(tbl.c.id).limit(limit).offset(offset)).all()
    return jsonify({"name": name, "total": total, "limit": limit, "offset": offset, "columns": [c.name for c in cols],
                    "rows": [["" if v is None else str(v) for v in r] for r in rows]})
