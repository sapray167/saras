"""Aggregations behind the dashboards. SQL does the heavy lifting (JOIN / GROUP BY)."""
from flask import current_app
from sqlalchemy import case, func

from ..extensions import db
from ..models import (Attendance, Course, CourseOffering, Enrollment, Faculty, Result,
                      Semester, Student)
from . import grading
from .attendance import bunk, pct
from .enrollment import find_clashes

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def semesters():
    return Semester.query.order_by(Semester.term_no).all()


def current_semester():
    return Semester.query.filter_by(is_current=True).first()


# ---------------------------------------------------------------- student
def _sem_gpas(student_id):
    """[(semester, sgpa, credits_earned, n_courses)] for every semester with published results."""
    rows = (db.session.query(Semester, func.sum(Result.grade_point * Course.credits),
                             func.sum(Course.credits),
                             func.sum(case((Result.grade != "F", Course.credits), else_=0)),
                             func.count(Result.id))
            .join(CourseOffering, CourseOffering.semester_id == Semester.id)
            .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Result, Result.enrollment_id == Enrollment.id)
            .filter(Enrollment.student_id == student_id, Result.grade.isnot(None), Semester.is_current.is_(False))
            .group_by(Semester.id).order_by(Semester.term_no).all())
    return [{"semester": s, "points": float(p), "credits": int(c), "earned": int(e), "courses": int(n)}
            for s, p, c, e, n in rows]


def student_gpa(student_id):
    gp = _sem_gpas(student_id)
    cum_p = cum_c = 0
    trend = []
    for g in gp:
        cum_p += g["points"]
        cum_c += g["credits"]
        trend.append({"label": g["semester"].name, "term_no": g["semester"].term_no,
                      "sgpa": round(g["points"] / g["credits"], 2), "cgpa": round(cum_p / cum_c, 2),
                      "credits": g["credits"], "courses": g["courses"]})
    return trend


def student_dashboard(student, semester):
    cfg = current_app.config
    trend = student_gpa(student.id)
    is_current = semester.is_current
    upto = [t for t in trend if t["term_no"] <= semester.term_no]
    cgpa = upto[-1]["cgpa"] if upto else None

    enrolls = (Enrollment.query.join(CourseOffering)
               .filter(Enrollment.student_id == student.id, CourseOffering.semester_id == semester.id).all())
    enrolls.sort(key=lambda e: e.offering.course.code)
    credits = sum(e.offering.course.credits for e in enrolls)

    att = dict(db.session.query(Attendance.enrollment_id, func.sum(case((Attendance.status == "P", 1), else_=0)))
               .filter(Attendance.enrollment_id.in_([e.id for e in enrolls] or [0]))
               .group_by(Attendance.enrollment_id).all())
    tot = dict(db.session.query(Attendance.enrollment_id, func.count(Attendance.id))
               .filter(Attendance.enrollment_id.in_([e.id for e in enrolls] or [0]))
               .group_by(Attendance.enrollment_id).all())

    bunk_rows, results, blocks = [], [], []
    clashes = find_clashes([e.offering for e in enrolls])
    clashing = {c["a"]["offering_id"] for c in clashes} | {c["b"]["offering_id"] for c in clashes}
    for e in enrolls:
        o, c = e.offering, e.offering.course
        a, t = int(att.get(e.id, 0)), int(tot.get(e.id, 0))
        b = bunk(a, t, cfg["MIN_ATTENDANCE"])
        base = {"enrollment_id": e.id, "offering_id": o.id, "code": c.code, "name": c.name,
                "professor": o.faculty.name, "credits": c.credits}
        if is_current:
            bunk_rows.append({**base, "attended": a, "total": t, **b})
        if e.result and e.result.grade:
            results.append({**base, "internal": e.result.internal_marks, "external": e.result.external_marks,
                            "total": e.result.total, "grade": e.result.grade, "grade_point": e.result.grade_point})
        for s in o.slots:
            blocks.append({**base, "day": s.day, "start": s.start_time.strftime("%H:%M"),
                           "end": s.end_time.strftime("%H:%M"), "room": s.room, "clash": o.id in clashing})
    att_total = sum(tot.get(e.id, 0) for e in enrolls)
    att_present = sum(att.get(e.id, 0) for e in enrolls)

    series = {"cgpa": [t["cgpa"] for t in trend], "credits": [t["credits"] for t in trend],
              "courses": [t["courses"] for t in trend]}
    series["credits"].append(credits) if is_current else None
    series["courses"].append(len(enrolls)) if is_current else None
    return {
        "profile": {"name": student.name, "roll_no": student.roll_no, "department": student.department.code,
                    "department_name": student.department.name},
        "semester": {"id": semester.id, "name": semester.name, "is_current": is_current},
        "kpis": {
            "cgpa": cgpa,
            "attendance_pct": pct(att_present, att_total) if is_current else None,
            "credits": credits, "max_credits": cfg["MAX_CREDITS"], "active_courses": len(enrolls),
            "series": series,
        },
        "bunk": bunk_rows, "results": results, "timetable": blocks, "clashes": clashes,
        "gpa_trend": trend, "min_attendance": cfg["MIN_ATTENDANCE"],
    }


# ---------------------------------------------------------------- teacher
def _offering_stats(offering_ids):
    """Per-offering: enrolled, attendance %, avg %, pass %, for a list of offerings."""
    if not offering_ids:
        return {}
    enr = dict(db.session.query(Enrollment.offering_id, func.count(Enrollment.id))
               .filter(Enrollment.offering_id.in_(offering_ids)).group_by(Enrollment.offering_id).all())
    att = {oid: (int(p or 0), int(t or 0)) for oid, p, t in
           db.session.query(Enrollment.offering_id, func.sum(case((Attendance.status == "P", 1), else_=0)),
                            func.count(Attendance.id))
           .join(Attendance, Attendance.enrollment_id == Enrollment.id)
           .filter(Enrollment.offering_id.in_(offering_ids)).group_by(Enrollment.offering_id).all()}
    return {oid: {"enrolled": enr.get(oid, 0), "att_present": att.get(oid, (0, 0))[0],
                  "att_total": att.get(oid, (0, 0))[1]} for oid in offering_ids}


def teacher_dashboard(faculty, semester):
    offs = (CourseOffering.query.filter_by(faculty_id=faculty.id, semester_id=semester.id)
            .join(Course).order_by(Course.code).all())
    stats = _offering_stats([o.id for o in offs])
    courses = [{"offering_id": o.id, "code": o.course.code, "name": o.course.name,
                "enrolled": stats[o.id]["enrolled"], "capacity": o.capacity} for o in offs]
    total_students = sum(c["enrolled"] for c in courses)
    present = sum(s["att_present"] for s in stats.values())
    total = sum(s["att_total"] for s in stats.values())

    # trend: enrolled students per semester across everything this faculty has taught
    trend = [{"label": sem.name, "value": int(n)} for sem, n in
             db.session.query(Semester, func.count(Enrollment.id))
             .join(CourseOffering, CourseOffering.semester_id == Semester.id)
             .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
             .filter(CourseOffering.faculty_id == faculty.id).group_by(Semester.id)
             .order_by(Semester.term_no).all()]
    return {
        "profile": {"name": faculty.name, "department": faculty.department.code, "designation": faculty.designation},
        "semester": {"id": semester.id, "name": semester.name, "is_current": semester.is_current},
        "kpis": {"active_courses": len(courses), "total_students": total_students,
                 "students_trend": trend, "avg_attendance": pct(present, total)},
        "courses": courses,
    }


def _result_stats(offering_ids):
    """avg % / pass % / component averages for a set of offerings."""
    q = (db.session.query(func.count(Result.id),
                          func.avg(Result.total * 100.0 / (Course.internal_max + Course.external_max)),
                          func.sum(case((Result.grade != "F", 1), else_=0)),
                          func.avg(Result.assignment_pct), func.avg(Result.project_score),
                          func.avg(Result.peer_score))
         .join(Enrollment, Enrollment.id == Result.enrollment_id)
         .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
         .join(Course, Course.id == CourseOffering.course_id)
         .filter(Enrollment.offering_id.in_(offering_ids or [0]), Result.grade.isnot(None)))
    n, avg, passed, assg, proj, peer = q.one()
    n = int(n or 0)
    return {"n": n, "avg_marks": round(float(avg or 0), 1),
            "pass_pct": round(float(passed or 0) / n * 100, 1) if n else 0,
            "assignment": round(float(assg or 0), 1), "project": round(float(proj or 0), 1),
            "peer": round(float(peer or 0), 1)}


def _attendance_pct(offering_ids):
    p, t = (db.session.query(func.sum(case((Attendance.status == "P", 1), else_=0)), func.count(Attendance.id))
            .join(Enrollment, Enrollment.id == Attendance.enrollment_id)
            .filter(Enrollment.offering_id.in_(offering_ids or [0])).one())
    return round(float(p or 0) / t * 100, 1) if t else 0


def course_analytics(offering):
    """Radar (course vs department average over the same semester) + grade distribution + per-course pass %."""
    dept_offs = [o.id for o in CourseOffering.query.join(Course)
                 .filter(Course.department_id == offering.course.department_id,
                         CourseOffering.semester_id == offering.semester_id).all()]
    mine, dept = _result_stats([offering.id]), _result_stats(dept_offs)
    axes = [("Average Marks", "avg_marks"), ("Attendance", None), ("Assignment Completion", "assignment"),
            ("Project Quality", "project"), ("Peer Feedback Score", "peer")]
    att_c, att_d = _attendance_pct([offering.id]), _attendance_pct(dept_offs)
    radar = [{"axis": a, "course": att_c if k is None else mine[k], "dept": att_d if k is None else dept[k]}
             for a, k in axes]

    dist = db.session.query(Result.grade, func.count(Result.id)) \
        .join(Enrollment, Enrollment.id == Result.enrollment_id) \
        .filter(Enrollment.offering_id == offering.id, Result.grade.isnot(None)).group_by(Result.grade).all()
    dist = dict(dist)
    dept_dist = dict(db.session.query(Result.grade, func.count(Result.id))
                     .join(Enrollment, Enrollment.id == Result.enrollment_id)
                     .filter(Enrollment.offering_id.in_(dept_offs), Result.grade.isnot(None))
                     .group_by(Result.grade).all())
    rules = grading.get_rules(offering.course)
    order = [r["grade"] for r in rules]
    n_c, n_d = max(sum(dist.values()), 1), max(sum(dept_dist.values()), 1)
    grades = [{"grade": g, "course_pct": round(dist.get(g, 0) / n_c * 100, 1),
               "dept_pct": round(dept_dist.get(g, 0) / n_d * 100, 1), "count": dist.get(g, 0)} for g in order]

    peers = []
    for o in CourseOffering.query.join(Course).filter(Course.department_id == offering.course.department_id,
                                                      CourseOffering.semester_id == offering.semester_id)\
            .order_by(Course.code).all():
        st = _result_stats([o.id])
        if st["n"]:
            peers.append({"code": o.course.code, "pass_pct": st["pass_pct"], "avg_marks": st["avg_marks"],
                          "is_selected": o.id == offering.id})
    return {
        "course": {"code": offering.course.code, "name": offering.course.name},
        "dept": {"code": offering.course.department.code},
        "radar": radar, "pass": {"course": mine["pass_pct"], "dept": dept["pass_pct"]},
        "grades": grades, "peers": peers,
    }


def gradebook(offering):
    rules = grading.get_rules(offering.course)
    rows = (db.session.query(Enrollment, Student, Result).join(Student, Student.id == Enrollment.student_id)
            .outerjoin(Result, Result.enrollment_id == Enrollment.id)
            .filter(Enrollment.offering_id == offering.id).order_by(Student.roll_no).all())
    ids = [e.id for e, _, _ in rows]
    att = {eid: (int(p or 0), int(t or 0)) for eid, p, t in
           db.session.query(Attendance.enrollment_id, func.sum(case((Attendance.status == "P", 1), else_=0)),
                            func.count(Attendance.id)).filter(Attendance.enrollment_id.in_(ids or [0]))
           .group_by(Attendance.enrollment_id).all()}
    out, totals, passed = [], [], 0
    for e, s, r in rows:
        graded = bool(r and r.grade)
        out.append({"roll_no": s.roll_no, "name": s.name, "internal": r.internal_marks if r else None,
                    "external": r.external_marks if r else None, "total": r.total if graded else None,
                    "grade": r.grade if graded else None, "grade_point": r.grade_point if graded else None,
                    "attendance_pct": pct(*att.get(e.id, (0, 0)))})
        if graded:
            totals.append(r.total)
            passed += r.grade != grading.FAIL_GRADE
    mx = offering.course.internal_max + offering.course.external_max
    return {
        "course": {"code": offering.course.code, "name": offering.course.name,
                   "internal_max": offering.course.internal_max, "external_max": offering.course.external_max},
        "rules": rules, "rows": out,
        "summary": {"students": len(out), "graded": len(totals),
                    "average": round(sum(totals) / len(totals), 1) if totals else None,
                    "highest": max(totals) if totals else None, "lowest": min(totals) if totals else None,
                    "pass_pct": round(passed / len(totals) * 100, 1) if totals else None, "max_total": mx},
    }


def admin_overview():
    cur = current_semester()
    depts = []
    from ..models import Department
    for d in Department.query.order_by(Department.code).all():
        offs = [o.id for o in CourseOffering.query.join(Course)
                .filter(Course.department_id == d.id, CourseOffering.semester_id == cur.id).all()]
        rs = _result_stats(offs)
        depts.append({"code": d.code, "name": d.name,
                      "students": Student.query.filter_by(department_id=d.id).count(),
                      "faculty": Faculty.query.filter_by(department_id=d.id).count(),
                      "courses": Course.query.filter_by(department_id=d.id).count(),
                      "avg_marks": rs["avg_marks"] if rs["n"] else None,
                      "pass_pct": rs["pass_pct"] if rs["n"] else None,
                      "attendance": _attendance_pct(offs) if offs else None})
    per_sem = [{"label": s.name, "value": int(n)} for s, n in
               db.session.query(Semester, func.count(Enrollment.id))
               .join(CourseOffering, CourseOffering.semester_id == Semester.id)
               .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
               .group_by(Semester.id).order_by(Semester.term_no).all()]
    low = (db.session.query(Student.roll_no, Student.name, Course.code,
                            func.sum(case((Attendance.status == "P", 1), else_=0)), func.count(Attendance.id))
           .join(Enrollment, Enrollment.student_id == Student.id)
           .join(Attendance, Attendance.enrollment_id == Enrollment.id)
           .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
           .join(Course, Course.id == CourseOffering.course_id)
           .filter(CourseOffering.semester_id == cur.id)
           .group_by(Enrollment.id, Student.roll_no, Student.name, Course.code).all())
    minimum = current_app.config["MIN_ATTENDANCE"]
    short = sorted(({"roll_no": r, "name": n, "course": c, "percent": round(float(p or 0) / t * 100, 1)}
                    for r, n, c, p, t in low if t and float(p or 0) / t * 100 < minimum), key=lambda x: x["percent"])
    return {
        "semester": cur.name,
        "counts": {"students": Student.query.count(), "faculty": Faculty.query.count(),
                   "courses": Course.query.count(), "enrollments": Enrollment.query.join(CourseOffering)
                   .filter(CourseOffering.semester_id == cur.id).count()},
        "departments": depts, "enrollment_trend": per_sem,
        "shortage_count": len(short), "shortage_sample": short[:8], "min_attendance": minimum,
    }
