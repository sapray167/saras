"""Database schema (works on MySQL and SQLite).

Core tables from the project brief: Department, Faculty, Student, Course,
Enrollment, Attendance, Result. Supporting tables: Semester, CourseOffering
(a course taught in a semester), TimetableSlot, Feedback, UploadLog,
IntegrityReview, and User (login).
"""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Department(db.Model):
    __tablename__ = "department"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)


class User(db.Model):
    __tablename__ = "app_user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "faculty", "student", name="user_role"), nullable=False)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Faculty(db.Model):
    __tablename__ = "faculty"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_user.id"), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    designation = db.Column(db.String(60), default="Assistant Professor")
    department = db.relationship("Department")
    user = db.relationship("User")


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_user.id"), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    roll_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    admission_year = db.Column(db.Integer, default=2024)
    department = db.relationship("Department")
    user = db.relationship("User")


class Semester(db.Model):
    __tablename__ = "semester"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)  # e.g. "Fall 2026"
    term_no = db.Column(db.Integer, nullable=False)  # 1..n, used for ordering
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False, nullable=False)


class Course(db.Model):
    __tablename__ = "course"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    credits = db.Column(db.Integer, nullable=False, default=3)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    internal_max = db.Column(db.Integer, nullable=False, default=40)
    external_max = db.Column(db.Integer, nullable=False, default=60)
    grade_rules = db.Column(db.Text)  # JSON; NULL = default 10-point scale
    department = db.relationship("Department")


class CourseOffering(db.Model):
    __tablename__ = "course_offering"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey("semester.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=70)
    __table_args__ = (db.UniqueConstraint("course_id", "semester_id", name="uq_offering"),)
    course = db.relationship("Course")
    semester = db.relationship("Semester")
    faculty = db.relationship("Faculty")
    slots = db.relationship("TimetableSlot", cascade="all, delete-orphan", order_by="TimetableSlot.day")


class TimetableSlot(db.Model):
    __tablename__ = "timetable_slot"
    id = db.Column(db.Integer, primary_key=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("course_offering.id"), nullable=False)
    day = db.Column(db.Integer, nullable=False)  # 0 = Monday .. 4 = Friday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(20))


class Enrollment(db.Model):
    __tablename__ = "enrollment"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("course_offering.id"), nullable=False, index=True)
    enrolled_on = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("student_id", "offering_id", name="uq_enrollment"),)
    student = db.relationship("Student")
    offering = db.relationship("CourseOffering")
    result = db.relationship("Result", uselist=False, cascade="all, delete-orphan")
    attendance = db.relationship("Attendance", cascade="all, delete-orphan")


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), nullable=False, index=True)
    class_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(1), nullable=False)  # 'P' or 'A'
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("enrollment_id", "class_date", name="uq_attendance"),)


class Result(db.Model):
    __tablename__ = "result"
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), unique=True, nullable=False)
    internal_marks = db.Column(db.Float)
    external_marks = db.Column(db.Float)
    total = db.Column(db.Float)
    grade = db.Column(db.String(3))
    grade_point = db.Column(db.Integer)
    assignment_pct = db.Column(db.Float)
    project_score = db.Column(db.Float)
    peer_score = db.Column(db.Float)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("course_offering.id"), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    author_role = db.Column(db.String(10), nullable=False)  # student | faculty
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UploadLog(db.Model):
    __tablename__ = "upload_log"
    id = db.Column(db.Integer, primary_key=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("course_offering.id"), nullable=False, index=True)
    filename = db.Column(db.String(200), nullable=False)
    size_bytes = db.Column(db.Integer, default=0)
    rows_total = db.Column(db.Integer, default=0)
    rows_processed = db.Column(db.Integer, default=0)
    status = db.Column(db.String(10), default="OK")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IntegrityReview(db.Model):
    __tablename__ = "integrity_review"
    id = db.Column(db.Integer, primary_key=True)
    alert_key = db.Column(db.String(120), unique=True, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # resolved | verified
    reviewed_by = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
