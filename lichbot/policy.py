import re
from datetime import date

TARGET_RE = re.compile(r"^(20\d{2})[-/](0?[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^(20\d{2})$")
RANGE_RE = re.compile(r"^(0?[1-9]|1[0-2])\s*[-–]\s*(0?[1-9]|1[0-2])$")


def parse_target(target):
    if not target:
        return None
    m = TARGET_RE.match(str(target).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def normalize_target(text):
    parsed = parse_target(text)
    if not parsed:
        return None
    return f"{parsed[0]:04d}-{parsed[1]:02d}"


def max_available_period(today=None):
    """Quy tắc đồng nhất:
    - Nếu trước ngày 20 (chưa qua 2/3 tháng): Tối đa chỉ có lịch của tháng hiện tại.
    - Từ ngày 20 trở đi: Bắt đầu có thể có lịch của tháng kế tiếp."""
    today = today or date.today()
    if today.day >= 20:
        if today.month == 12:
            return today.year + 1, 1
        return today.year, today.month + 1
    return today.year, today.month


def is_period_allowed(year, month, today=None):
    return (year, month) <= max_available_period(today)


def expand_year_targets(year_str, start_m=1, end_m=12, today=None):
    year = int(year_str)
    today = today or date.today()
    max_y, max_m = max_available_period(today)

    valid = []
    skipped = []
    # Quét từ tháng lớn về tháng nhỏ để tối ưu duyệt Facebook
    for m in range(end_m, start_m - 1, -1):
        if (year, m) > (max_y, max_m):
            skipped.append(f"{year:04d}-{m:02d}")
        else:
            valid.append(f"{year:04d}-{m:02d}")
    return valid, skipped