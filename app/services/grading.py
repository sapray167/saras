"""Marks -> total -> grade -> grade point. Rules are per course (JSON) with a 10-point default."""
import json

DEFAULT_RULES = [
    {"grade": "O", "min": 90, "points": 10},
    {"grade": "A+", "min": 80, "points": 9},
    {"grade": "A", "min": 70, "points": 8},
    {"grade": "B+", "min": 60, "points": 7},
    {"grade": "B", "min": 50, "points": 6},
    {"grade": "C", "min": 40, "points": 5},
    {"grade": "F", "min": 0, "points": 0},
]
FAIL_GRADE = "F"


def get_rules(course):
    if course.grade_rules:
        try:
            return json.loads(course.grade_rules)
        except ValueError:
            pass
    return [dict(r) for r in DEFAULT_RULES]


def validate_rules(rules):
    """Return (clean_rules, error). Rules are percentages of the total, highest grade first."""
    if not isinstance(rules, list) or len(rules) < 2:
        return None, "Provide at least two grade bands."
    clean = []
    for r in rules:
        try:
            clean.append({"grade": str(r["grade"]).strip()[:3], "min": float(r["min"]), "points": int(r["points"])})
        except (KeyError, TypeError, ValueError):
            return None, "Each band needs grade, min and points."
        if not clean[-1]["grade"]:
            return None, "Grade names cannot be empty."
    clean.sort(key=lambda r: -r["min"])
    if clean[-1]["min"] != 0:
        return None, "The lowest band must start at 0%."
    mins = [r["min"] for r in clean]
    if len(set(mins)) != len(mins):
        return None, "Two grade bands share the same minimum."
    if any(m < 0 or m > 100 for m in mins):
        return None, "Minimums must be between 0 and 100."
    pts = [r["points"] for r in clean]
    if pts != sorted(pts, reverse=True):
        return None, "Grade points must not increase as minimum marks decrease."
    for r in clean:
        r["min"] = int(r["min"]) if r["min"] == int(r["min"]) else r["min"]
    return clean, None


def grade_for(percent, rules):
    for r in sorted(rules, key=lambda r: -r["min"]):
        if percent >= r["min"]:
            return r["grade"], r["points"]
    return FAIL_GRADE, 0


def compute(internal, external, course, rules=None):
    """Return dict(total, percent, grade, grade_point, passed)."""
    rules = rules or get_rules(course)
    total = round(float(internal) + float(external), 2)
    max_total = course.internal_max + course.external_max
    percent = total / max_total * 100
    grade, points = grade_for(percent, rules)
    return {"total": total, "percent": round(percent, 2), "grade": grade,
            "grade_point": points, "passed": grade != FAIL_GRADE}


def apply_to_result(result, course, rules=None):
    if result.internal_marks is None or result.external_marks is None:
        result.total = result.grade = result.grade_point = None
        return result
    c = compute(result.internal_marks, result.external_marks, course, rules)
    result.total, result.grade, result.grade_point = c["total"], c["grade"], c["grade_point"]
    return result
