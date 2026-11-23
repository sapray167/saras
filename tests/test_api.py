from datetime import date

from conftest import login


def test_pages_require_login(app):
    c = app.test_client()
    assert c.get("/teacher").status_code == 302
    assert c.get("/api/student/dashboard").status_code == 401


def test_bad_password_rejected(app):
    r = app.test_client().post("/api/login", json={"username": "akash", "password": "nope"})
    assert r.status_code == 401


def test_roles_are_enforced(app, student, teacher):
    assert student.get("/api/admin/overview").status_code == 403
    assert student.get("/api/teacher/dashboard").status_code == 403
    assert teacher.get("/api/student/dashboard").status_code == 403


def test_student_dashboard_matches_design(student):
    d = student.get("/api/student/dashboard").get_json()
    assert d["profile"]["name"] == "Akash Singh"
    assert d["kpis"]["cgpa"] == 8.72 and d["kpis"]["active_courses"] == 6
    assert len(d["bunk"]) == 6 and d["clashes"]
    assert {"safe", "need"} <= {b["status"] for b in d["bunk"]}


def test_teacher_dashboard_matches_design(teacher):
    d = teacher.get("/api/teacher/dashboard").get_json()
    assert d["kpis"]["active_courses"] == 4 and d["kpis"]["total_students"] == 218


def test_duplicate_enrollment_blocked(student):
    offs = student.get("/api/student/offerings").get_json()["offerings"]
    mine = next(o for o in offs if o["registered"])
    r = student.post("/api/student/enroll", json={"offering_id": mine["offering_id"]})
    assert r.status_code == 409


def test_attendance_toggle_is_idempotent(teacher):
    d = teacher.get("/api/teacher/dashboard").get_json()
    oid = next(c for c in d["courses"] if c["code"] == "CS301")["offering_id"]
    roster = teacher.get(f"/api/teacher/offerings/{oid}/roster").get_json()
    eid = roster["students"][0]["enrollment_id"]
    day = roster["date"]
    for status in ("A", "A", "P"):
        r = teacher.put(f"/api/teacher/offerings/{oid}/attendance",
                        json={"date": day, "marks": [{"enrollment_id": eid, "status": status}]})
        assert r.status_code == 200
    bad = teacher.put(f"/api/teacher/offerings/{oid}/attendance",
                      json={"date": "1999-01-01", "marks": [{"enrollment_id": eid, "status": "P"}]})
    assert bad.status_code == 400


def test_result_upload_grades_and_rejects_bad_rows(teacher):
    d = teacher.get("/api/teacher/dashboard").get_json()
    oid = next(c for c in d["courses"] if c["code"] == "CS301")["offering_id"]
    roster = teacher.get(f"/api/teacher/offerings/{oid}/roster").get_json()["students"]
    rows = [{"roll_no": roster[0]["roll_no"], "internal": 38, "external": 57},
            {"roll_no": roster[1]["roll_no"], "internal": 99, "external": 10},
            {"roll_no": "NOPE", "internal": 1, "external": 1}]
    r = teacher.post(f"/api/teacher/offerings/{oid}/results", json={"filename": "t.csv", "rows": rows}).get_json()
    assert r["processed"] == 1 and len(r["errors"]) == 2 and r["status"] == "PARTIAL"
    gb = teacher.get(f"/api/teacher/offerings/{oid}/gradebook").get_json()
    row = next(x for x in (gb.get("rows") or gb.get("students")) if x["roll_no"] == roster[0]["roll_no"])
    assert row["total"] == 95 and row["grade"] == "O"


def test_integrity_resolve(teacher):
    alerts = teacher.get("/api/teacher/integrity").get_json()["alerts"]
    assert alerts
    assert teacher.post("/api/teacher/integrity/resolve-all").status_code == 200
    assert teacher.get("/api/teacher/integrity").get_json()["alerts"] == []


def test_admin_crud_and_validation(admin):
    r = admin.post("/api/admin/departments", json={"code": "ZZ", "name": "Test Dept"})
    assert r.status_code in (200, 201)
    dup = admin.post("/api/admin/departments", json={"code": "ZZ", "name": "Again"})
    assert dup.status_code in (400, 409)
    assert admin.get("/api/admin/overview").get_json()


def test_db_viewer_admin_only_and_hides_hashes(app, admin, student):
    assert student.get("/api/admin/db/tables").status_code == 403
    t = admin.get("/api/admin/db/tables").get_json()["tables"]
    assert len(t) == 14 and next(x for x in t if x["name"] == "student")["rows"] > 0
    u = admin.get("/api/admin/db/tables/app_user").get_json()
    assert "password_hash" not in u["columns"] and u["rows"]
    assert admin.get("/api/admin/db/tables/nope").status_code == 404
