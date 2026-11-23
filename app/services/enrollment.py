"""Registration rules shared by the student and admin flows."""
from flask import current_app

from ..extensions import db
from ..models import CourseOffering, Enrollment, Result, Semester


def _overlap(a, b):
    return a.day == b.day and a.start_time < b.end_time and b.start_time < a.end_time


def find_clashes(offerings):
    """Return [{a, b, day, start, end}] for overlapping timetable slots between offerings."""
    out = []
    for i, oa in enumerate(offerings):
        for ob in offerings[i + 1:]:
            for sa in oa.slots:
                for sb in ob.slots:
                    if _overlap(sa, sb):
                        out.append({
                            "a": {"offering_id": oa.id, "code": oa.course.code, "name": oa.course.name},
                            "b": {"offering_id": ob.id, "code": ob.course.code, "name": ob.course.name},
                            "day": sa.day,
                            "start": max(sa.start_time, sb.start_time).strftime("%H:%M"),
                            "end": min(sa.end_time, sb.end_time).strftime("%H:%M"),
                        })
    return out


def current_enrollments(student_id, semester_id):
    return (Enrollment.query.join(CourseOffering)
            .filter(Enrollment.student_id == student_id, CourseOffering.semester_id == semester_id).all())


def check_enroll(student, offering):
    """Return (errors, warnings). Errors block registration; warnings need confirmation."""
    errors, warnings = [], []
    sem = db.session.get(Semester, offering.semester_id)
    if not sem.is_current:
        errors.append(f"Registration is closed for {sem.name}.")
        return errors, warnings
    if Enrollment.query.filter_by(student_id=student.id, offering_id=offering.id).first():
        errors.append("You are already registered for this course.")
        return errors, warnings

    # Already passed this course in an earlier semester?
    prior = (db.session.query(Result.grade).join(Enrollment).join(CourseOffering)
             .filter(Enrollment.student_id == student.id, CourseOffering.course_id == offering.course_id,
                     CourseOffering.semester_id != offering.semester_id, Result.grade.isnot(None),
                     Result.grade != "F").first())
    if prior:
        errors.append(f"{offering.course.code} was already completed (grade {prior[0]}).")

    taken = Enrollment.query.filter_by(offering_id=offering.id).count()
    if taken >= offering.capacity:
        errors.append(f"{offering.course.code} is full ({offering.capacity}/{offering.capacity} seats).")

    mine = current_enrollments(student.id, offering.semester_id)
    credits = sum(e.offering.course.credits for e in mine) + offering.course.credits
    cap = current_app.config["MAX_CREDITS"]
    if credits > cap:
        errors.append(f"Credit limit exceeded: {credits}/{cap}.")

    for c in find_clashes([e.offering for e in mine] + [offering]):
        if offering.id in (c["a"]["offering_id"], c["b"]["offering_id"]):
            other = c["b"] if c["a"]["offering_id"] == offering.id else c["a"]
            warnings.append(f"Timetable clash with {other['code']} on {['Mon','Tue','Wed','Thu','Fri'][c['day']]} "
                            f"{c['start']}-{c['end']}.")
    return errors, warnings
