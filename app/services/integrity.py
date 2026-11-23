"""Data-integrity scanner: duplicate enrollments and look-alike student records."""
from ..extensions import db
from ..models import CourseOffering, Enrollment, IntegrityReview, Semester, Student


def _tokens(name):
    return [t for t in name.lower().replace(".", " ").split() if t]


def names_clash(a, b):
    """True when two names look like the same person (same first+last, compatible middle)."""
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) < 2 or len(tb) < 2 or ta[0] != tb[0] or ta[-1] != tb[-1]:
        return False
    ma, mb = " ".join(ta[1:-1]), " ".join(tb[1:-1])
    if not ma or not mb:
        return True
    return ma.startswith(mb) or mb.startswith(ma)


def scan(offering_ids=None):
    """Return a list of alerts, excluding anything already reviewed.

    offering_ids limits the scan to students enrolled in those offerings (a teacher's scope).
    """
    reviewed = {r.alert_key for r in IntegrityReview.query.all()}
    alerts = []

    # 1) Same student enrolled in the same course more than once (different semesters),
    #    where the earlier attempt was not failed => redundant re-enrollment.
    rows = (db.session.query(Enrollment, CourseOffering, Semester)
            .join(CourseOffering, Enrollment.offering_id == CourseOffering.id)
            .join(Semester, CourseOffering.semester_id == Semester.id).all())
    by_key = {}
    for e, o, s in rows:
        by_key.setdefault((e.student_id, o.course_id), []).append((e, o, s))
    for (sid, _cid), items in by_key.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda t: t[2].term_no)
        earlier, later = items[0], items[-1]
        if earlier[0].result and earlier[0].result.grade == "F":
            continue  # legitimate re-attempt after failing
        if offering_ids is not None and later[1].id not in offering_ids:
            continue
        key = f"dup:{later[0].id}"
        if key in reviewed:
            continue
        st = db.session.get(Student, sid)
        code = later[1].course.code
        alerts.append({
            "id": key, "kind": "duplicate_enrollment", "action": "resolve",
            "student_id": st.id, "roll_no": st.roll_no, "enrollment_id": later[0].id,
            "message": f"Student ID {st.roll_no} (Duplicate Enrollment: {code} in {earlier[2].name} and {later[2].name})",
        })

    # 2) Look-alike names inside one department.
    scope = None
    if offering_ids is not None:
        scope = {sid for (sid,) in db.session.query(Enrollment.student_id)
                 .filter(Enrollment.offering_id.in_(offering_ids)).all()}
    students = Student.query.order_by(Student.roll_no).all()
    by_dept = {}
    for st in students:
        by_dept.setdefault(st.department_id, []).append(st)
    for group in by_dept.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if scope is not None and a.id not in scope and b.id not in scope:
                    continue
                if names_clash(a.name, b.name):
                    key = f"name:{min(a.id, b.id)}-{max(a.id, b.id)}"
                    if key in reviewed:
                        continue
                    alerts.append({
                        "id": key, "kind": "name_clash", "action": "verify",
                        "student_ids": [a.id, b.id],
                        "message": f'Name Clash: "{a.name}" (ID {a.roll_no}) vs ID {b.roll_no} ("{b.name}")',
                    })
    return alerts


def resolve(alert_id, user):
    """Resolve one alert. Duplicate enrollments are removed; name clashes are marked verified."""
    if IntegrityReview.query.filter_by(alert_key=alert_id).first():
        return False
    kind, _, ref = alert_id.partition(":")
    if kind == "dup":
        enr = db.session.get(Enrollment, int(ref))
        if enr is None:
            return False
        db.session.delete(enr)
        action = "resolved"
    elif kind == "name":
        action = "verified"
    else:
        return False
    db.session.add(IntegrityReview(alert_key=alert_id, action=action, reviewed_by=user))
    db.session.commit()
    return True
