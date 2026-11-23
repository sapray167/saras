"""Deterministic demo data: 5 semesters, 150 students, 12 faculty, ~540 live enrollments, attendance & results.

Run:  python -m app.seed         (creates tables if needed, then loads demo data into an EMPTY database)
"""
import json
import random
from datetime import date, datetime, time, timedelta

from werkzeug.security import generate_password_hash

from . import create_app
from .extensions import db
from .models import (Attendance, Course, CourseOffering, Department, Enrollment, Faculty, Feedback, Result,
                     Semester, Student, TimetableSlot, UploadLog, User)
from .services import grading

SEED_UNTIL = date(2026, 11, 19)  # attendance recorded up to the day before "today" in the demo scenario
HOLIDAYS = {date(2026, 10, 2), date(2026, 10, 20), date(2026, 11, 9)}

DEPTS = [("CS", "Computer Science"), ("IT", "Information Technology"), ("EC", "Electronics & Communication"),
         ("MA", "Mathematics"), ("GE", "General Engineering")]

SEMESTERS = [("Fall 2024", 1, date(2024, 8, 5), date(2024, 12, 13)),
             ("Spring 2025", 2, date(2025, 1, 13), date(2025, 5, 16)),
             ("Fall 2025", 3, date(2025, 8, 4), date(2025, 12, 12)),
             ("Spring 2026", 4, date(2026, 1, 12), date(2026, 5, 15)),
             ("Fall 2026", 5, date(2026, 8, 3), date(2026, 12, 11))]

# key, name, department, email-local-part, designation
FACULTY = [("khan", "Professor A. Khan", "CS", "Professor"), ("iyer", "Dr. S. Iyer", "CS", "Associate Professor"),
           ("nair", "Dr. P. Nair", "CS", "Assistant Professor"), ("verma", "Dr. N. Verma", "IT", "Associate Professor"),
           ("mehta", "Prof. R. Mehta", "IT", "Professor"), ("rao", "Dr. K. Rao", "MA", "Professor"),
           ("sharma", "Dr. L. Sharma", "EC", "Associate Professor"), ("das", "Prof. T. Das", "EC", "Professor"),
           ("pillai", "Dr. M. Pillai", "GE", "Associate Professor"), ("bose", "Prof. S. Bose", "GE", "Assistant Professor")]

# Completed semesters: (term, code, name, dept, faculty)
PAST = [
    (1, "MA101", "Engineering Mathematics I", "MA", "rao"), (1, "PH101", "Engineering Physics", "GE", "pillai"),
    (1, "CS101", "Programming in C", "CS", "khan"), (1, "EE101", "Basic Electrical Engineering", "EC", "sharma"),
    (1, "HS101", "Communication Skills", "GE", "bose"), (1, "ME101", "Engineering Graphics", "GE", "bose"),
    (1, "CH101", "Environmental Studies", "GE", "pillai"),
    (2, "MA102", "Engineering Mathematics II", "MA", "rao"), (2, "CS102", "Problem Solving with Python", "CS", "nair"),
    (2, "EC102", "Basic Electronics", "EC", "das"), (2, "HS102", "Professional Ethics", "GE", "bose"),
    (2, "CS103", "Digital Logic Design", "CS", "iyer"), (2, "PH102", "Applied Physics", "GE", "pillai"),
    (3, "MA201", "Probability & Statistics", "MA", "rao"), (3, "CS201", "Object Oriented Programming", "CS", "nair"),
    (3, "CS202", "Computer Organization", "CS", "iyer"), (3, "CS203", "Data Structures", "CS", "khan"),
    (3, "IT201", "Web Fundamentals", "IT", "verma"), (3, "HS201", "Economics for Engineers", "GE", "bose"),
    (4, "MA202", "Linear Algebra", "MA", "rao"), (4, "CS204", "Design & Analysis of Algorithms", "CS", "khan"),
    (4, "CS206", "Theory of Computation", "CS", "iyer"), (4, "IT202", "Object Oriented Analysis", "IT", "verma"),
    (4, "CS207", "Python for Data Science", "CS", "nair"), (4, "HS202", "Technical Writing", "GE", "bose"),
]

# Fall 2026 offerings: code, name, dept, faculty, capacity, slots[(day,start,end,room)], bias, quota, pool
D = lambda d, s, e, r: (d, s, e, r)
CURRENT = [
    ("CS301", "Database Management Systems", "CS", "khan", 40, [D(0, "11:00", "12:30", "R-301"), D(3, "11:00", "12:30", "R-301")], 10, 36, "cs+it"),
    ("CS305", "Operating Systems", "CS", "khan", 70, [D(0, "14:00", "15:30", "R-302"), D(2, "09:30", "11:00", "R-302")], -16, 62, "cs+it"),
    ("CS310", "Computer Networks", "CS", "khan", 70, [D(1, "09:30", "11:00", "R-303"), D(4, "14:00", "15:30", "R-303")], -14, 60, "cs+it"),
    ("CS315", "Software Engineering", "CS", "khan", 70, [D(1, "12:00", "13:30", "R-204"), D(4, "11:00", "12:30", "R-204")], -8, 60, "cs+it"),
    ("CS330", "Machine Learning", "CS", "iyer", 60, [D(2, "11:30", "13:00", "R-401"), D(0, "09:30", "11:00", "R-401")], -6, 55, "cs+it"),
    ("CS340", "Web Technologies", "CS", "nair", 50, [D(2, "14:00", "15:30", "Lab-2"), D(3, "14:00", "15:30", "Lab-2")], -4, 45, "cs"),
    ("IT301", "Information Security", "IT", "verma", 50, [D(2, "09:30", "11:00", "R-105"), D(3, "09:30", "11:00", "R-105")], -3, 45, "it+cs"),
    ("IT320", "Cloud Computing", "IT", "mehta", 45, [D(1, "12:00", "13:30", "R-106"), D(4, "09:30", "11:00", "R-106")], 0, 40, "it+cs"),
    ("MA301", "Discrete Mathematics", "MA", "rao", 80, [D(0, "15:30", "17:00", "R-110"), D(2, "15:30", "17:00", "R-110")], -12, 70, "cs+it"),
    ("EC301", "Signals & Systems", "EC", "sharma", 30, [D(0, "09:30", "11:00", "R-501"), D(3, "15:30", "17:00", "R-501")], -4, 25, "ec"),
    ("EC305", "VLSI Design", "EC", "das", 30, [D(1, "11:00", "12:30", "R-502"), D(4, "15:30", "17:00", "R-502")], -2, 25, "ec"),
    ("EC310", "Embedded Systems", "EC", "sharma", 30, [D(2, "11:00", "12:30", "R-503"), D(3, "09:30", "11:00", "R-503")], 0, 25, "ec"),
]

FIRST = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Reyansh", "Ishaan", "Rohan", "Kabir", "Dhruv", "Yash", "Rahul",
         "Karan", "Nikhil", "Siddharth", "Pranav", "Harsh", "Manish", "Tanmay", "Varun", "Ananya", "Diya", "Isha", "Kavya",
         "Meera", "Neha", "Priya", "Riya", "Saanvi", "Shreya", "Tanvi", "Aditi", "Pooja", "Sneha", "Anjali", "Divya",
         "Nidhi", "Simran", "Zoya", "Fatima", "Imran", "Sameer", "Rizwan", "Ayesha", "Gurpreet", "Harleen", "Jasleen", "Mohit"]
LAST = ["Sharma", "Verma", "Gupta", "Mehta", "Reddy", "Iyer", "Nair", "Patel", "Joshi", "Kapoor", "Malhotra", "Chopra",
        "Bansal", "Agarwal", "Mishra", "Pandey", "Yadav", "Chauhan", "Tiwari", "Saxena", "Bhatia", "Kulkarni", "Desai",
        "Menon", "Pillai", "Rao", "Das", "Ghosh", "Banerjee", "Sen", "Bose", "Ansari", "Qureshi", "Bhatt", "Thakur", "Rawat"]

SPECIAL = {188: "Akash Singh", 166: "Akash Singh Khan", 171: "Akash S. Khan"}
AKASH_ROLL, DUP_ROLL = 188, 160
AKASH_GP = {1: [8, 8, 8, 8, 9, 9, 7], 2: [8, 9, 8, 9, 9, 6], 3: [9, 9, 10, 9, 8, 9], 4: [10, 10, 9, 10, 9, 10]}
AKASH_ATT = {"CS301": 90, "CS315": 88, "CS330": 92, "IT301": 79, "IT320": 74, "MA301": 81}
GP_TO_TOTAL = {10: 93, 9: 84, 8: 74, 7: 64, 6: 54, 5: 44, 0: 30}
CS_RULE_PW = {"student": generate_password_hash("student123"), "faculty": generate_password_hash("faculty123")}


def _t(s):
    h, m = map(int, s.split(":"))
    return time(h, m)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _marks(total, course):
    """Split a total into internal/external marks consistent with the course maxima."""
    total = _clamp(round(total), 0, course.internal_max + course.external_max)
    internal = _clamp(round(total * course.internal_max / (course.internal_max + course.external_max)), 0, course.internal_max)
    external = _clamp(total - internal, 0, course.external_max)
    return float(internal), float(external)


def _overlap(a, b):
    return a[0] == b[0] and _t(a[1]) < _t(b[2]) and _t(b[1]) < _t(a[2])


def run(app=None, verbose=True):
    rng = random.Random(2026)
    log = print if verbose else (lambda *a, **k: None)
    db.create_all()
    if Department.query.first():
        log("Database already has data - skipping seed.")
        return
    dept = {c: Department(code=c, name=n) for c, n in DEPTS}
    db.session.add_all(dept.values())
    sems = {t: Semester(name=n, term_no=t, start_date=s, end_date=e, is_current=(t == 5)) for n, t, s, e in SEMESTERS}
    db.session.add_all(sems.values())

    admin = User(username="admin", role="admin")
    admin.set_password("admin123")
    db.session.add(admin)
    fac = {}
    for key, name, d, desig in FACULTY:
        u = User(username=key, role="faculty", password_hash=CS_RULE_PW["faculty"])
        if key == "khan":
            u.set_password("khan123")
        db.session.add(u)
        db.session.flush()
        fac[key] = Faculty(user_id=u.id, department_id=dept[d].id, name=name, designation=desig,
                           email=f"{key}@saras.edu")
        db.session.add(fac[key])

    # ------------------------------------------------------------ students
    used, students = set(), {}
    for i in range(150):
        roll = 101 + i
        if roll in SPECIAL:
            name = SPECIAL[roll]
        else:
            while True:
                f, l = rng.choice(FIRST), rng.choice(LAST)
                if (f, l) not in used:
                    used.add((f, l))
                    break
            name = f"{f} {l}"
        d = "CS" if roll <= 175 else "IT" if roll <= 225 else "EC"
        lateral = roll % 4 == 0 and roll not in (DUP_ROLL, AKASH_ROLL)
        uname = "akash" if roll == AKASH_ROLL else str(roll)
        u = User(username=uname, role="student", password_hash=CS_RULE_PW["student"])
        if roll == AKASH_ROLL:
            u.set_password("akash123")
        db.session.add(u)
        db.session.flush()
        slug = name.lower().replace(".", "").replace(" ", ".")
        st = Student(user_id=u.id, department_id=dept[d].id, roll_no=str(roll), name=name,
                     email=f"{slug}{roll}@saras.edu", admission_year=2025 if lateral else 2024)
        st.lateral, st.ability, st.propensity = lateral, _clamp(rng.gauss(68, 13), 38, 95), _clamp(rng.gauss(0.795, 0.09), 0.5, 0.99)
        students[roll] = st
        db.session.add(st)
    db.session.flush()

    # ------------------------------------------------------- past semesters
    courses, past_off = {}, {}
    for term, code, name, d, fk in PAST:
        c = courses.get(code) or Course(code=code, name=name, credits=3, department_id=dept[d].id)
        courses[code] = c
        db.session.add(c)
        db.session.flush()
        o = CourseOffering(course_id=c.id, semester_id=sems[term].id, faculty_id=fac[fk].id, capacity=200)
        db.session.add(o)
        past_off.setdefault(term, []).append((o, c))
    db.session.flush()

    akash_queue = {t: list(g) for t, g in AKASH_GP.items()}
    for term, offs in past_off.items():
        akash_gps = list(AKASH_GP[term])
        for o, c in offs:
            gp_for_akash = akash_gps.pop(0)
            for roll, st in students.items():
                if st.lateral and term < 3:
                    continue
                if roll == AKASH_ROLL:
                    total = GP_TO_TOTAL[gp_for_akash]
                else:
                    total = _clamp(rng.gauss(st.ability, 8), 22, 99)
                im, ex = _marks(total, c)
                r = Result(internal_marks=im, external_marks=ex)
                grading.apply_to_result(r, c)
                db.session.add(Enrollment(student_id=st.id, offering_id=o.id, result=r))
    db.session.flush()

    # --- the duplicate-enrollment scenario: roll 160 already passed CS301 in Spring 2026
    # (created after CURRENT courses exist, below)

    # ------------------------------------------------------ current semester
    cur_off, slots_of, bias = {}, {}, {}
    for code, name, d, fk, cap, slots, b, quota, pool in CURRENT:
        c = Course(code=code, name=name, credits=3, department_id=dept[d].id)
        db.session.add(c)
        db.session.flush()
        o = CourseOffering(course_id=c.id, semester_id=sems[5].id, faculty_id=fac[fk].id, capacity=cap)
        db.session.add(o)
        db.session.flush()
        for day, s, e, room in slots:
            db.session.add(TimetableSlot(offering_id=o.id, day=day, start_time=_t(s), end_time=_t(e), room=room))
        cur_off[code], slots_of[code], bias[code] = o, slots, b
        courses[code] = c

    by_dept = {"cs": [r for r in students if r <= 175], "it": [r for r in students if 176 <= r <= 225],
               "ec": [r for r in students if r >= 226]}
    forced = {"CS301": [AKASH_ROLL, 166, 171, DUP_ROLL], "CS315": [AKASH_ROLL], "CS330": [AKASH_ROLL],
              "IT301": [AKASH_ROLL], "IT320": [AKASH_ROLL], "MA301": [AKASH_ROLL]}
    taken = {r: [] for r in students}  # roll -> slots already assigned (clash avoidance for random picks)
    chosen = {}
    for code, name, d, fk, cap, slots, b, quota, pool in CURRENT:
        members = list(dict.fromkeys(forced.get(code, [])))
        for r in members:
            taken[r] += slots
        candidates = [r for p in pool.split("+") for r in by_dept[p] if r != AKASH_ROLL and r not in members]
        rng.shuffle(candidates)
        for r in candidates:
            if len(members) >= quota:
                break
            if any(_overlap(a, b2) for a in taken[r] for b2 in slots):
                continue
            members.append(r)
            taken[r] += slots
        assert len(members) == quota, (code, len(members), quota)
        chosen[code] = members

    enrolls = {}
    for code, members in chosen.items():
        for r in members:
            e = Enrollment(student_id=students[r].id, offering_id=cur_off[code].id)
            db.session.add(e)
            enrolls[(code, r)] = e
    db.session.flush()

    # duplicate scenario: student 160 passed CS301 last semester with grade B+
    c301 = courses["CS301"]
    old = CourseOffering(course_id=c301.id, semester_id=sems[4].id, faculty_id=fac["khan"].id, capacity=10)
    db.session.add(old)
    db.session.flush()
    rr = Result(internal_marks=25.0, external_marks=38.0)
    grading.apply_to_result(rr, c301)
    db.session.add(Enrollment(student_id=students[DUP_ROLL].id, offering_id=old.id, result=rr))

    # results (provisional) + attendance for the current semester
    att_rows = []
    for (code, r), e in enrolls.items():
        c, st, b = courses[code], students[r], bias[code]
        total = _clamp(rng.gauss(st.ability + b - 2, 9), 20, 99)
        im, ex = _marks(total, c)
        res = Result(enrollment_id=e.id, internal_marks=im, external_marks=ex,
                     assignment_pct=round(_clamp(rng.gauss(76 + b * 0.5, 11), 20, 100), 1),
                     project_score=round(_clamp(rng.gauss(70 + b * 0.6, 10), 20, 100), 1),
                     peer_score=round(_clamp(rng.gauss(69 + b * 0.4, 9), 20, 100), 1))
        grading.apply_to_result(res, c)
        db.session.add(res)
    db.session.flush()

    for code, o in cur_off.items():
        days = {s[0] for s in slots_of[code]}
        sessions, d = [], o.semester.start_date
        while d <= SEED_UNTIL:
            if d.weekday() in days and d not in HOLIDAYS:
                sessions.append(d)
            d += timedelta(days=1)
        for r in chosen[code]:
            e, st = enrolls[(code, r)], students[r]
            if r == AKASH_ROLL:
                absences = set(rng.sample(range(len(sessions)), len(sessions) - round(AKASH_ATT[code] / 100 * len(sessions))))
                present = [i not in absences for i in range(len(sessions))]
            else:
                p = _clamp(st.propensity + rng.uniform(-0.04, 0.04), 0.4, 0.99)
                present = [rng.random() < p for _ in sessions]
            for sd, pr in zip(sessions, present):
                att_rows.append({"enrollment_id": e.id, "class_date": sd, "status": "P" if pr else "A",
                                 "marked_at": datetime.combine(sd, time(12, 0))})
    db.session.execute(Attendance.__table__.insert(), att_rows)

    # ----------------------------------------------------- feedback & upload log
    now = datetime.utcnow()
    c301 = cur_off["CS301"]
    msgs = [("Akash Singh Khan", "student", "Could you share the ER-diagram notes from Thursday?", 52),
            ("Professor A. Khan", "faculty", "Uploaded to the course drive. Normalisation quiz is next Monday.", 47),
            ("Akash S. Khan", "student", "Is BCNF with an example on the quiz syllabus?", 31),
            ("Riya Chopra", "student", "The SQL lab server was slow today, could we get 15 extra minutes?", 12),
            ("Professor A. Khan", "faculty", "Yes - the lab will stay open until 4:30 on Thursday.", 8)]
    ids = [r for r in chosen["CS301"] if students[r].name not in ("Akash S. Khan", "Akash Singh Khan")]
    for who, role, text, mins in msgs:
        db.session.add(Feedback(offering_id=c301.id, author_name=who, author_role=role, message=text,
                                created_at=now - timedelta(minutes=mins)))
    db.session.add(UploadLog(offering_id=c301.id, filename="CS301_Finals_v2.xlsx", size_bytes=2202009,
                             rows_total=36, rows_processed=36, status="OK", created_at=now - timedelta(minutes=2)))
    db.session.commit()
    log(f"Seeded: {Student.query.count()} students, {Faculty.query.count()} faculty, {Course.query.count()} courses, "
        f"{Enrollment.query.count()} enrollments, {Attendance.query.count()} attendance rows.")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        run()
