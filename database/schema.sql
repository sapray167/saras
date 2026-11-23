-- SARAS schema for MySQL 8+ (generated from app/models.py)
-- mysql -u root -p -e "CREATE DATABASE saras CHARACTER SET utf8mb4"; mysql -u root -p saras < database/schema.sql
-- Or just run `python -m app.seed` which creates the tables and the demo data itself.

CREATE TABLE app_user (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(60) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` ENUM('admin','faculty','student') NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);

CREATE TABLE department (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE integrity_review (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	alert_key VARCHAR(120) NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	reviewed_by VARCHAR(60), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (alert_key)
);

CREATE TABLE semester (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(30) NOT NULL, 
	term_no INTEGER NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	is_current BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE course (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	credits INTEGER NOT NULL, 
	department_id INTEGER NOT NULL, 
	internal_max INTEGER NOT NULL, 
	external_max INTEGER NOT NULL, 
	grade_rules TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(department_id) REFERENCES department (id)
);

CREATE TABLE faculty (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	department_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	designation VARCHAR(60), 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES app_user (id), 
	FOREIGN KEY(department_id) REFERENCES department (id), 
	UNIQUE (email)
);

CREATE TABLE student (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	department_id INTEGER NOT NULL, 
	roll_no VARCHAR(20) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	admission_year INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES app_user (id), 
	FOREIGN KEY(department_id) REFERENCES department (id), 
	UNIQUE (roll_no), 
	UNIQUE (email)
);

CREATE TABLE course_offering (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	course_id INTEGER NOT NULL, 
	semester_id INTEGER NOT NULL, 
	faculty_id INTEGER NOT NULL, 
	capacity INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_offering UNIQUE (course_id, semester_id), 
	FOREIGN KEY(course_id) REFERENCES course (id), 
	FOREIGN KEY(semester_id) REFERENCES semester (id), 
	FOREIGN KEY(faculty_id) REFERENCES faculty (id)
);

CREATE TABLE enrollment (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	student_id INTEGER NOT NULL, 
	offering_id INTEGER NOT NULL, 
	enrolled_on DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_enrollment UNIQUE (student_id, offering_id), 
	FOREIGN KEY(student_id) REFERENCES student (id), 
	FOREIGN KEY(offering_id) REFERENCES course_offering (id)
);

CREATE TABLE feedback (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	offering_id INTEGER NOT NULL, 
	author_name VARCHAR(120) NOT NULL, 
	author_role VARCHAR(10) NOT NULL, 
	message VARCHAR(500) NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(offering_id) REFERENCES course_offering (id)
);

CREATE TABLE timetable_slot (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	offering_id INTEGER NOT NULL, 
	day INTEGER NOT NULL, 
	start_time TIME NOT NULL, 
	end_time TIME NOT NULL, 
	room VARCHAR(20), 
	PRIMARY KEY (id), 
	FOREIGN KEY(offering_id) REFERENCES course_offering (id)
);

CREATE TABLE upload_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	offering_id INTEGER NOT NULL, 
	filename VARCHAR(200) NOT NULL, 
	size_bytes INTEGER, 
	rows_total INTEGER, 
	rows_processed INTEGER, 
	status VARCHAR(10), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(offering_id) REFERENCES course_offering (id)
);

CREATE TABLE attendance (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	enrollment_id INTEGER NOT NULL, 
	class_date DATE NOT NULL, 
	status VARCHAR(1) NOT NULL, 
	marked_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_attendance UNIQUE (enrollment_id, class_date), 
	FOREIGN KEY(enrollment_id) REFERENCES enrollment (id)
);

CREATE TABLE result (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	enrollment_id INTEGER NOT NULL, 
	internal_marks FLOAT, 
	external_marks FLOAT, 
	total FLOAT, 
	grade VARCHAR(3), 
	grade_point INTEGER, 
	assignment_pct FLOAT, 
	project_score FLOAT, 
	peer_score FLOAT, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (enrollment_id), 
	FOREIGN KEY(enrollment_id) REFERENCES enrollment (id)
);
