import csv
import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import case, func

from ..extensions import db
from ..models import (Attendance, Course, CourseOffering, Enrollment, Feedback, Result, Semester, Student,
                      UploadLog)
from ..services import analytics, grading, integrity
from . import api_error, faculty_of, login_required

bp = Blueprint("teacher", __name__, url_prefix="/api/teacher")


def _own_offering(user, offering_id):
    o = db.session.get(CourseOffering, offering_id)
    fac = faculty_of(user)
    return o if o and fac and o.faculty_id == fac.id else None


def _own_or_404(fn):
    from functools import wraps

    @wraps(fn)
    def w(user, offering_id, *a, **kw):
        o = _own_offering(user, offering_id)
        return fn(user, o, *a, **kw) if o else api_error("Course not found.", 404)
    return w


@bp.get("/dashboard")
@login_required("faculty")
def dashboard(user):
    sid = request.args.get("semester_id", type=int)
    sem = db.session.get(Semester, sid) if sid else analytics.current_semester()
    if not sem:
        return api_error("Semester not found.", 404)
    return jsonify(analytics.teacher_dashboard(faculty_of(user), sem))


def _class_dates(offering):
    """Scheduled class dates up to today (or semester end), newest first."""
    sem, slots = offering.semester, {s.day for s in offering.slots}
    last = min(date.today(), sem.end_date)
    if last < sem.start_date:
        last = sem.end_date
    d, out = last, []
    while d >= sem.start_date and len(out) < 60:
        if d.weekday() in slots:
            out.append(d)
        d -= timedelta(days=1)
    return out


@bp.get("/offerings/<int:offering_id>/roster")
@login_required("faculty")
@_own_or_404
def roster(user, o):
    dates = _class_dates(o)
    try:
        day = date.fromisoformat(request.args["date"]) if request.args.get("date") else (dates[0] if dates else o.semester.end_date)
    except ValueError:
        return api_error("Invalid date.")
    rows = (db.session.query(Enrollment.id, Student.id, Student.roll_no, Student.name)
            .join(Student, Student.id == Enrollment.student_id)
            .filter(Enrollment.offering_id == o.id).order_by(Student.roll_no).all())
    ids = [r[0] for r in rows]
    status = dict(db.session.query(Attendance.enrollment_id, Attendance.status)
                  .filter(Attendance.enrollment_id.in_(ids or [0]), Attendance.class_date == day).all())
    agg = {eid: (int(p or 0), int(t), last) for eid, p, t, last in
           db.session.query(Attendance.enrollment_id, func.sum(case((Attendance.status == "P", 1), else_=0)),
                            func.count(Attendance.id),
                            func.max(case((Attendance.status == "P", Attendance.class_date), else_=None)))
           .filter(Attendance.enrollment_id.in_(ids or [0])).group_by(Attendance.enrollment_id).all()}
    start = o.slots[0].start_time.strftime("%H:%M") if o.slots else "09:00"
    students = []
    for eid, sid, roll, name in rows:
        p, t, last = agg.get(eid, (0, 0, None))
        students.append({"enrollment_id": eid, "student_id": sid, "roll_no": roll, "name": name,
                         "status": status.get(eid), "attendance_pct": round(p / t * 100, 1) if t else None,
                         "last_seen": f"{last.isoformat()} {start}" if last else None})
    marked = sum(1 for s in students if s["status"])
    return jsonify({"course": {"offering_id": o.id, "code": o.course.code, "name": o.course.name},
                    "date": day.isoformat(), "class_dates": [d.isoformat() for d in dates[:12]],
                    "students": students, "marked": marked,
                    "present": sum(1 for s in students if s["status"] == "P")})


@bp.put("/offerings/<int:offering_id>/attendance")
@login_required("faculty")
@_own_or_404
def mark_attendance(user, o):
    """Body: {date, marks:[{enrollment_id, status: 'P'|'A'|null}]}. Idempotent upsert."""
    data = request.get_json(silent=True) or {}
    try:
        day = date.fromisoformat(data.get("date", ""))
    except ValueError:
        return api_error("A valid date (YYYY-MM-DD) is required.")
    if not (o.semester.start_date <= day <= o.semester.end_date):
        return api_error("That date is outside the semester.")
    marks = data.get("marks") or []
    valid = {e.id for e in Enrollment.query.filter_by(offering_id=o.id).all()}
    saved = 0
    for m in marks:
        eid, st = m.get("enrollment_id"), m.get("status")
        if eid not in valid or st not in ("P", "A", None):
            return api_error("Invalid attendance entry.")
        row = Attendance.query.filter_by(enrollment_id=eid, class_date=day).first()
        if st is None:
            if row:
                db.session.delete(row)
        elif row:
            row.status, row.marked_at = st, datetime.utcnow()
        else:
            db.session.add(Attendance(enrollment_id=eid, class_date=day, status=st))
        saved += 1
    db.session.commit()
    return jsonify({"ok": True, "saved": saved})


@bp.get("/offerings/<int:offering_id>/feedback")
@login_required("faculty")
@_own_or_404
def feedback_list(user, o):
    rows = Feedback.query.filter_by(offering_id=o.id).order_by(Feedback.id.desc()).limit(30).all()
    return jsonify([{"id": f.id, "author": f.author_name, "role": f.author_role, "message": f.message,
                     "created_at": f.created_at.isoformat() + "Z"} for f in reversed(rows)])


@bp.post("/offerings/<int:offering_id>/feedback")
@login_required("faculty")
@_own_or_404
def feedback_post(user, o):
    msg = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not msg or len(msg) > 500:
        return api_error("Message must be 1-500 characters.")
    db.session.add(Feedback(offering_id=o.id, author_name=faculty_of(user).name, author_role="faculty", message=msg))
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.get("/offerings/<int:offering_id>/grade-rules")
@login_required("faculty")
@_own_or_404
def rules_get(user, o):
    c = o.course
    return jsonify({"rules": grading.get_rules(c), "internal_max": c.internal_max, "external_max": c.external_max})


@bp.put("/offerings/<int:offering_id>/grade-rules")
@login_required("faculty")
@_own_or_404
def rules_put(user, o):
    import json
    data = request.get_json(silent=True) or {}
    rules, err = grading.validate_rules(data.get("rules"))
    if err:
        return api_error(err)
    try:
        im, em = int(data.get("internal_max", o.course.internal_max)), int(data.get("external_max", o.course.external_max))
    except (TypeError, ValueError):
        return api_error("Maximum marks must be whole numbers.")
    if im < 0 or em < 1 or im + em > 1000:
        return api_error("Maximum marks are out of range.")
    c = o.course
    c.grade_rules, c.internal_max, c.external_max = json.dumps(rules), im, em
    changed = 0
    for r in (Result.query.join(Enrollment).join(CourseOffering).filter(CourseOffering.course_id == c.id).all()):
        before = r.grade
        grading.apply_to_result(r, c, rules)
        changed += before != r.grade
    db.session.commit()
    return jsonify({"ok": True, "regraded": changed, "rules": rules})


@bp.post("/offerings/<int:offering_id>/results")
@login_required("faculty")
@_own_or_404
def upload_results(user, o):
    """Body: {filename, size, rows:[{roll_no, internal, external}]}. Valid rows are saved, bad rows reported."""
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return api_error("No rows found in the file.")
    c = o.course
    rules = grading.get_rules(c)
    roster = {e.student.roll_no: e for e in Enrollment.query.filter_by(offering_id=o.id).all()}
    errors, processed, seen = [], 0, set()
    for i, r in enumerate(rows, start=2):
        roll = str(r.get("roll_no", "")).strip()
        try:
            im, ex = float(r.get("internal")), float(r.get("external"))
        except (TypeError, ValueError):
            errors.append({"row": i, "roll_no": roll, "error": "Internal/external marks must be numbers."})
            continue
        if roll not in roster:
            errors.append({"row": i, "roll_no": roll, "error": "Roll number is not enrolled in this course."})
        elif roll in seen:
            errors.append({"row": i, "roll_no": roll, "error": "Duplicate roll number in file."})
        elif not (0 <= im <= c.internal_max) or not (0 <= ex <= c.external_max):
            errors.append({"row": i, "roll_no": roll,
                           "error": f"Marks out of range (internal 0-{c.internal_max}, external 0-{c.external_max})."})
        else:
            seen.add(roll)
            e = roster[roll]
            res = e.result or Result(enrollment_id=e.id)
            res.internal_marks, res.external_marks = im, ex
            grading.apply_to_result(res, c, rules)
            db.session.add(res)
            processed += 1
    status = "OK" if processed == len(roster) and not errors else "PARTIAL"
    db.session.add(UploadLog(offering_id=o.id, filename=str(data.get("filename") or "upload")[:200],
                             size_bytes=int(data.get("size") or 0), rows_total=len(roster),
                             rows_processed=processed, status=status))
    db.session.commit()
    return jsonify({"ok": True, "processed": processed, "total": len(roster), "status": status, "errors": errors})


@bp.get("/offerings/<int:offering_id>/upload-status")
@login_required("faculty")
@_own_or_404
def upload_status(user, o):
    log = UploadLog.query.filter_by(offering_id=o.id).order_by(UploadLog.id.desc()).first()
    if not log:
        return jsonify(None)
    return jsonify({"filename": log.filename, "size_bytes": log.size_bytes, "processed": log.rows_processed,
                    "total": log.rows_total, "status": log.status, "created_at": log.created_at.isoformat() + "Z"})


@bp.get("/offerings/<int:offering_id>/gradebook")
@login_required("faculty")
@_own_or_404
def gradebook(user, o):
    return jsonify(analytics.gradebook(o))


@bp.get("/offerings/<int:offering_id>/gradebook.csv")
@login_required("faculty")
@_own_or_404
def gradebook_csv(user, o):
    gb = analytics.gradebook(o)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["roll_no", "name", "internal", "external", "total", "grade", "grade_point", "attendance_pct"])
    for r in gb["rows"]:
        w.writerow([r[k] for k in ("roll_no", "name", "internal", "external", "total", "grade", "grade_point",
                                   "attendance_pct")])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={o.course.code}_gradebook.csv"})


@bp.get("/offerings/<int:offering_id>/sample.csv")
@login_required("faculty")
@_own_or_404
def sample_csv(user, o):
    """A ready-to-edit upload template pre-filled with the class roster."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["roll_no", "name", "internal", "external"])
    for e in sorted(Enrollment.query.filter_by(offering_id=o.id).all(), key=lambda e: e.student.roll_no):
        r = e.result
        w.writerow([e.student.roll_no, e.student.name, r.internal_marks if r else "", r.external_marks if r else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={o.course.code}_marks_template.csv"})


@bp.get("/offerings/<int:offering_id>/analytics")
@login_required("faculty")
@_own_or_404
def course_analytics(user, o):
    return jsonify(analytics.course_analytics(o))


def _scope(user):
    sem = analytics.current_semester()
    return [o.id for o in CourseOffering.query.filter_by(faculty_id=faculty_of(user).id, semester_id=sem.id).all()]


@bp.get("/integrity")
@login_required("faculty")
def integrity_list(user):
    return jsonify({"alerts": integrity.scan(_scope(user))})


@bp.post("/integrity/<path:alert_id>/resolve")
@login_required("faculty")
def integrity_resolve(user, alert_id):
    if alert_id not in {a["id"] for a in integrity.scan(_scope(user))}:
        return api_error("Alert not found (it may already be resolved).", 404)
    integrity.resolve(alert_id, user.username)
    return jsonify({"ok": True})


@bp.post("/integrity/resolve-all")
@login_required("faculty")
def integrity_resolve_all(user):
    n = 0
    for a in integrity.scan(_scope(user)):
        n += integrity.resolve(a["id"], user.username)
    return jsonify({"ok": True, "resolved": n})
