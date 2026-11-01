import re
import unicodedata
from collections import Counter

from .policy import parse_target

# Bắt các tiêu đề lịch phát hành cụ thể
TITLE_PATTERNS = [
    re.compile(r"(?:lich\s+phat\s+hanh|sach\s+moi|phat\s+hanh\s+du\s+kien)[^.\n\r]{0,35}?thang\s*0?(\d{1,2})(?!\d)"),
    re.compile(r"(?:manga\s*[-–]?\s*comic|comic|don\s+chao|chao\s+don)[^.\n\r]{0,35}?thang\s*0?(\d{1,2})(?!\d)"),
]

# Nhận diện lịch gộp Tết
MERGED_RE = re.compile(r"thang\s*0?1\s*(?:&|\+|va|[-–/])\s*(?:thang\s*)?0?2(?!\d)")

# Tách riêng cụm ngày đăng của FB (chỉ lọc khi có số ngày + chữ tháng rõ ràng như "28 tháng 9")
FB_POST_DATE_RE = re.compile(r"\b(?:ngay\s*)?\d{1,2}\s+thang\s*0?(\d{1,2})(?:\s*,?\s*(20\d\d))?")
MONTH_WORD_RE = re.compile(r"\bthang\s*0?(\d{1,2})(?!\d)")
PAIR_RE = re.compile(r"\bthang\s*0?(\d{1,2})\s*[-–.,/]?\s*(20\d\d)\b")
YEAR_RE = re.compile(r"\b(20\d\d)\b")


def fold(text):
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def is_merged_jan_feb(text, months=()):
    if MERGED_RE.search(text):
        return True
    s = set(months)
    return 1 in s and 2 in s and len(s - {1, 2, 12}) == 0


def find_title_month(text):
    for pattern in TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            m = int(match.group(1))
            if 1 <= m <= 12:
                return m
    return None


def extract_months(text):
    """Trích xuất các tháng thực tế xuất hiện trong văn bản mà không bịa thêm tần suất.
    Đồng thời không nuốt chữ dạng 'thang 9 thang 10' hay 'lich phat hanh 2026 thang 11'."""
    # Bóc tách bằng cách mask ngày đăng để tránh '28 thang 9' biến thành tháng lịch
    masked_text = text
    for match in FB_POST_DATE_RE.finditer(text):
        start, end = match.span()
        # Chỉ mask nếu phía trước là khoảng trắng/đầu dòng (ngày thật)
        prefix = text[:start].strip()
        if not prefix.endswith("thang"):
            masked_text = masked_text[:start] + (" " * (end - start)) + masked_text[end:]

    found = [int(m) for m in MONTH_WORD_RE.findall(masked_text) if 1 <= int(m) <= 12]
    title_m = find_title_month(text)
    if title_m and title_m not in found:
        found.insert(0, title_m)
    return found


def dominant(values):
    return Counter(values).most_common(1)[0][0] if values else None


def identify_photo_month(text, months):
    """Ưu tiên số 1 cho tiêu đề bài viết, nếu không có mới dùng tần suất thống kê."""
    title_m = find_title_month(text)
    if title_m:
        return title_m
    return dominant(months)


def explicit_year(text, month):
    post_dates = [
        (int(m), int(y)) for m, y in FB_POST_DATE_RE.findall(text)
        if y and 1 <= int(m) <= 12
    ]
    if post_dates and month:
        inferred = []
        for post_m, post_y in post_dates:
            if post_m >= 11 and month <= 2:
                inferred.append(post_y + 1)
            elif post_m <= 2 and month >= 11:
                inferred.append(post_y - 1)
            else:
                inferred.append(post_y)
        return dominant(inferred)

    pairs = [(int(m), int(y)) for m, y in PAIR_RE.findall(text) if 1 <= int(m) <= 12]
    exact = [y for m, y in pairs if m == month]
    if exact:
        return dominant(exact)
    if pairs and month:
        inferred = [
            post_y + 1 if post_m >= 11 and month <= 2 else post_y
            for post_m, post_y in pairs
        ]
        return dominant(inferred)

    cleaned = re.sub(r"#\w+", "", text)
    years = [int(y) for y in YEAR_RE.findall(cleaned)]
    return dominant(years)


def nearest_year(month, today):
    now = today.year * 12 + today.month
    candidates = (today.year - 1, today.year, today.year + 1)
    return min(candidates, key=lambda y: abs(y * 12 + month - now))


def schedule_year(text, month, today):
    from .policy import max_available_period
    found = explicit_year(text, month)
    if found:
        return found
    max_y, max_m = max_available_period(today)
    if (today.year + 1, month) <= (max_y, max_m):
        return today.year + 1
    if (today.year, month) <= (max_y, max_m):
        return today.year
    return today.year - 1


YEAR_STRATEGIES = {
    "explicit": lambda t, m, today: explicit_year(t, m) or nearest_year(m, today),
    "nearest": lambda t, m, today: nearest_year(m, today),
    "schedule": schedule_year,
}


def resolve_year(text, month, mode, today):
    strategy = YEAR_STRATEGIES.get(mode, YEAR_STRATEGIES["explicit"])
    return strategy(text, month, today)


def month_matches(found, want):
    return found == want or (want <= 2 and found in (1, 2))


def has_all(text, keys):
    return all(fold(key) in text for key in keys)