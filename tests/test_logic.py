from app.services import grading
from app.services.attendance import bunk


class C:
    grade_rules = None


def test_default_grade_bands():
    rules = grading.get_rules(C())
    assert rules[0] == {"grade": "O", "min": 90, "points": 10}


def test_bunk_safe_and_need():
    safe = bunk(28, 31, 75)           # 90.3% -> can skip some classes
    assert safe["status"] == "safe" and safe["safe_to_skip"] >= 1
    need = bunk(20, 30, 75)           # 66.7% -> must attend more
    assert need["status"] == "need" and need["need_to_attend"] >= 1
    assert bunk(0, 0)["status"] == "new"


def test_bunk_boundary_is_exact():
    # 3 of 4 = exactly 75% -> safe, nothing extra to skip
    b = bunk(3, 4, 75)
    assert b["status"] == "safe" and b["safe_to_skip"] == 0


def test_rules_validation():
    ok, err = grading.validate_rules([{"grade": "P", "min": 40, "points": 5}, {"grade": "F", "min": 0, "points": 0}])
    assert err is None and ok[0]["grade"] == "P"
    _, err = grading.validate_rules([{"grade": "P", "min": 40, "points": 5}])
    assert err
    _, err = grading.validate_rules([{"grade": "P", "min": 40, "points": 5}, {"grade": "F", "min": 10, "points": 0}])
    assert "start at 0" in err
