import re
import unicodedata
from collections import Counter

MONTH_RE = re.compile(r"thang\s*0?(\d{1,2})(?!\d)")
PAIR_RE = re.compile(r"thang\s*0?(\d{1,2})\s*[-–./]?\s*(20\d\d)")
YEAR_RE = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def fold(text):
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def extract_months(text):
    return [int(m) for m in MONTH_RE.findall(text) if 1 <= int(m) <= 12]


def dominant(values):
    return Counter(values).most_common(1)[0][0] if values else None


def explicit_year(text, month):
    pairs = [(int(m), int(y)) for m, y in PAIR_RE.findall(text) if 1 <= int(m) <= 12]
    years = [y for m, y in pairs if m == month] or [y for m, y in pairs]
    if not years:
        years = [int(y) for y in YEAR_RE.findall(text)]
    return dominant(years)


def nearest_year(month, today):
    now = today.year * 12 + today.month
    candidates = (today.year - 1, today.year, today.year + 1)
    return min(candidates, key=lambda y: abs(y * 12 + month - now))


def resolve_year(text, month, mode, today):
    if mode == "nearest":
        return nearest_year(month, today)
    return explicit_year(text, month) or nearest_year(month, today)


def month_matches(found, want):
    return found == want or (want <= 2 and found in (1, 2))


def has_all(text, keys):
    return all(fold(key) in text for key in keys)


def parse_target(target):
    if not target:
        return None
    year, month = target.split("-")
    return int(year), int(month)
