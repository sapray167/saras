"""Attendance maths for the Bunk-O-Meter. Integer arithmetic only (no float drift)."""
from fractions import Fraction
from math import ceil, floor


def bunk(attended, total, minimum=75):
    """How many classes can be skipped (or must be attended in a row) to stay at/above `minimum` %."""
    p = Fraction(minimum, 100)
    if total == 0:
        return {"percent": None, "status": "new", "safe_to_skip": 0, "need_to_attend": 0}
    percent = round(attended / total * 100, 1)
    if Fraction(attended, total) >= p:
        safe = floor(Fraction(attended) / p - total)
        return {"percent": percent, "status": "safe", "safe_to_skip": max(0, safe), "need_to_attend": 0}
    need = ceil((p * total - attended) / (1 - p))
    return {"percent": percent, "status": "need", "safe_to_skip": 0, "need_to_attend": need}


def pct(attended, total):
    return round(attended / total * 100, 1) if total else None
