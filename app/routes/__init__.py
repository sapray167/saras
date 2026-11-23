from functools import wraps

from flask import jsonify, session

from ..extensions import db
from ..models import Faculty, Student, User


def api_error(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            uid = session.get("uid")
            user = db.session.get(User, uid) if uid else None
            if not user:
                return api_error("Please sign in.", 401)
            if roles and user.role not in roles:
                return api_error("You do not have access to this resource.", 403)
            return fn(user, *a, **kw)
        return wrapper
    return deco


def student_of(user):
    return Student.query.filter_by(user_id=user.id).first()


def faculty_of(user):
    return Faculty.query.filter_by(user_id=user.id).first()
