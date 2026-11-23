from flask import Blueprint, jsonify, request, session

from ..extensions import db
from ..models import User
from ..services import analytics
from . import api_error, faculty_of, login_required, student_of

bp = Blueprint("auth", __name__, url_prefix="/api")
HOME = {"admin": "/admin", "faculty": "/teacher", "student": "/student"}


def display_name(user):
    if user.role == "student":
        s = student_of(user)
        return f"{s.name} - {s.department.code}"
    if user.role == "faculty":
        f = faculty_of(user)
        return f"{f.name} - {f.department.code}"
    return "Administrator"


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip().lower()).first()
    if not user or not user.check_password(data.get("password") or ""):
        return api_error("Invalid username or password.", 401)
    session.clear()
    session["uid"] = user.id
    return jsonify({"role": user.role, "redirect": HOME[user.role], "name": display_name(user)})


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
@login_required()
def me(user):
    return jsonify({"role": user.role, "name": display_name(user), "username": user.username})


@bp.get("/semesters")
@login_required()
def semesters(user):
    return jsonify([{"id": s.id, "name": s.name, "is_current": s.is_current, "term_no": s.term_no}
                    for s in analytics.semesters()])
