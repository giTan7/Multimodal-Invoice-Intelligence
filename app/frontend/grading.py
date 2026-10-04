"""
Tiny, deterministic checker used ONLY by the UI to colour results for the built-in samples.
(It is not an LLM judge. It just compares each value with the known answer.)

grade_field() returns one of:
  "ok"      correct (ignoring case / spaces / punctuation). A correct null counts as ok.
  "format"  the right value, but not in the app's required format
            (e.g. "Rs. 18,880.00" instead of 18880.00, or "15-Sep-2026" instead of 2026-09-15)
  "wrong"   a different value, or a value where the answer is null (an invented value)
  "missing" the model returned null but a value was expected
"""
import re
from datetime import datetime

DATE_FORMATS = ["%Y-%m-%d", "%d-%b-%Y", "%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                "%d/%m/%y", "%d-%m-%y", "%B %d, %Y", "%b %d, %Y"]   # all day-first, as in India


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _number(text: str):
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _date(text: str):
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def grade_field(key: str, value, expected) -> str:
    v = (str(value).strip() if value is not None else "") or None
    if expected is None:
        return "ok" if v is None else "wrong"
    if v is None:
        return "missing"
    if _norm(v) == _norm(expected):
        return "ok"
    if key == "total_amount":
        a, b = _number(v), _number(expected)
        if a is not None and b is not None and abs(a - b) < 0.005:
            return "format"
    if key == "invoice_date":
        a, b = _date(v), _date(expected)
        if a and b and a == b:
            return "format"
    return "wrong"


def score(fields: dict, expected: dict, keys, present=None) -> dict:
    """
    `present` = the keys the model actually returned. A key it never returned is graded "missing",
    even when the right answer is null (a non-answer must not earn credit).
    """
    grades = {}
    for k in keys:
        if present is not None and k not in present:
            grades[k] = "missing"
        else:
            grades[k] = grade_field(k, fields.get(k), expected.get(k))
    return {"grades": grades,
            "ok": sum(g == "ok" for g in grades.values()),
            "format": sum(g == "format" for g in grades.values()),
            "total": len(grades)}
