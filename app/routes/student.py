from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Course, CourseOffering, Enrollment, Feedback, Semester
from ..services import analytics
from ..services.enrollment import check_enroll, current_enrollments
from . import api_error, login_required, student_of

bp = Blueprint("student", __name__, url_prefix="/api/student")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def _semester_from_request():
    sid = request.args.get("semester_id", type=int)
    return (db.session.get(Semester, sid) if sid else analytics.current_semester())


@bp.get("/dashboard")
@login_required("student")
def dashboard(user):
    sem = _semester_from_request()
    if not sem:
        return api_error("Semester not found.", 404)
    return jsonify(analytics.student_dashboard(student_of(user), sem))


def _offering_json(o, taken, registered):
    return {"offering_id": o.id, "code": o.course.code, "name": o.course.name, "credits": o.course.credits,
            "professor": o.faculty.name, "department": o.course.department.code, "seats_left": o.capacity - taken,
            "capacity": o.capacity, "registered": registered,
            "slots": [{"day": s.day, "start": s.start_time.strftime("%H:%M"),
                       "end": s.end_time.strftime("%H:%M"), "room": s.room} for s in o.slots]}


@bp.get("/offerings")
@login_required("student")
def offerings(user):
    """Everything open for registration this semester, with live eligibility messages."""
    st, sem = student_of(user), analytics.current_semester()
    mine = {e.offering_id: e for e in current_enrollments(st.id, sem.id)}
    out = []
    for o in CourseOffering.query.filter_by(semester_id=sem.id).join(Course).order_by(Course.code).all():
        taken = Enrollment.query.filter_by(offering_id=o.id).count()
        item = _offering_json(o, taken, o.id in mine)
        if o.id in mine:
            item["enrollment_id"] = mine[o.id].id
        else:
            item["errors"], item["warnings"] = check_enroll(st, o)
        out.append(item)
    credits = sum(e.offering.course.credits for e in mine.values())
    return jsonify({"semester": sem.name, "credits": credits, "max_credits": 24, "offerings": out})


@bp.post("/enroll")
@login_required("student")
def enroll(user):
    data = request.get_json(silent=True) or {}
    o = db.session.get(CourseOffering, data.get("offering_id"))
    if not o:
        return api_error("Course offering not found.", 404)
    st = student_of(user)
    errors, warnings = check_enroll(st, o)
    if errors:
        return api_error(errors[0], 409, errors=errors)
    if warnings and not data.get("allow_clash"):
        return api_error(warnings[0], 409, code="clash", warnings=warnings)
    e = Enrollment(student_id=st.id, offering_id=o.id)
    db.session.add(e)
    db.session.commit()
    return jsonify({"ok": True, "enrollment_id": e.id, "warnings": warnings}), 201


@bp.delete("/enroll/<int:enrollment_id>")
@login_required("student")
def drop(user, enrollment_id):
    e = db.session.get(Enrollment, enrollment_id)
    if not e or e.student_id != student_of(user).id:
        return api_error("Enrollment not found.", 404)
    if not e.offering.semester.is_current:
        return api_error("Past semesters are locked.", 409)
    if e.result and e.result.grade:
        return api_error("Results are already published for this course.", 409)
    db.session.delete(e)
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/offerings/<int:offering_id>/feedback")
@login_required("student")
def feedback(user, offering_id):
    st = student_of(user)
    if not Enrollment.query.filter_by(student_id=st.id, offering_id=offering_id).first():
        return api_error("You are not enrolled in this course.", 403)
    msg = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not msg or len(msg) > 500:
        return api_error("Feedback must be 1-500 characters.")
    db.session.add(Feedback(offering_id=offering_id, author_name=st.name, author_role="student", message=msg))
    db.session.commit()
    return jsonify({"ok": True}), 201
