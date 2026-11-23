import os

from flask import Flask, jsonify, redirect, send_from_directory, session

from .config import Config
from .extensions import db

WEB = os.path.join(os.path.dirname(__file__), "web")
PAGES = {"student": "student", "faculty": "teacher", "admin": "admin"}


def create_app(config=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)
    os.makedirs(app.instance_path, exist_ok=True)
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////") and ":memory:" not in uri:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, uri[len("sqlite:///"):])
    db.init_app(app)

    from .routes import admin, auth, student, teacher
    for m in (auth, student, teacher, admin):
        app.register_blueprint(m.bp)

    from .models import User

    def current_role():
        uid = session.get("uid")
        u = db.session.get(User, uid) if uid else None
        return u.role if u else None

    @app.get("/")
    def index():
        role = current_role()
        return redirect("/" + PAGES[role]) if role else redirect("/login")

    @app.get("/login")
    def login_page():
        return send_from_directory(WEB, "login.html")

    for role, page in PAGES.items():
        def view(role=role, page=page):
            if current_role() != role:
                return redirect("/login")
            return send_from_directory(WEB, f"{page}.html")
        app.add_url_rule(f"/{page}", f"page_{page}", view)

    @app.errorhandler(404)
    def nf(e):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(413)
    def too_big(e):
        return jsonify({"error": "Upload too large."}), 413

    @app.errorhandler(500)
    def boom(e):
        return jsonify({"error": "Something went wrong on the server."}), 500

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if resp.mimetype == "text/html":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app
