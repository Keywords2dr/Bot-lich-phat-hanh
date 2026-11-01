import re
import unicodedata
from collections import Counter

# Bắt chữ "tháng X" nhưng KHÔNG đứng sau một con số (loại trừ ngày đăng "28 tháng 9", "27 tháng 8, 2025")
MONTH_RE = re.compile(r"(?<![0-9])(?<![0-9]\s)thang\s*0?(\d{1,2})(?!\d)")
# Bắt cụm tiêu đề chuẩn của các NXB (Kim Đồng, IPM, Trẻ)
TITLE_MONTH_RE = re.compile(
    r"(?:lich\s+phat\s+hanh|sach\s+moi|phat\s+hanh\s+du\s+kien|manga\s*[-–]?\s*comic|comic|don\s+chao|chao\s+don)"
    r"[^.\n]{0,30}?thang\s*0?(\d{1,2})(?!\d)"
)
# Nhận diện lịch gộp Tết: "tháng 1 & 2", "tháng 1 - 2", "tháng 01 + 02", "tháng 1 và tháng 2"
MERGED_JAN_FEB_RE = re.compile(
    r"thang\s*0?1\s*(?:&|\+|va|[-–/])\s*(?:thang\s*)?0?2(?!\d)"
)
PAIR_RE = re.compile(r"thang\s*0?(\d{1,2})\s*[-–.,/]?\s*(20\d\d)")
POST_DATE_YEAR_RE = re.compile(r"\b\d{1,2}\s+thang\s*0?(\d{1,2})\s*(?:,|nam)?\s*(20\d\d)")
POST_DATE_ANY_RE = re.compile(r"\b\d{1,2}\s+thang\s*0?\d{1,2}(?!\d)(?:\s*,?\s*20\d\d)?")
YEAR_RE = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def fold(text):
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def is_merged_jan_feb(text, months=()):
    if MERGED_JAN_FEB_RE.search(text):
        return True
    s = set(months)
    return 1 in s and 2 in s and len(s - {1, 2, 12}) == 0


def extract_months(text):
    cleaned = POST_DATE_ANY_RE.sub(" ", text)
    months = [int(m) for m in MONTH_RE.findall(cleaned) if 1 <= int(m) <= 12]
    titled = [int(m) for m in TITLE_MONTH_RE.findall(cleaned) if 1 <= int(m) <= 12]
    if titled and months:
        target_m = titled[0]
        # Đảm bảo tháng nằm trong tiêu đề ("Lịch phát hành... tháng X") luôn đứng đầu khi gọi dominant()
        top_m, top_count = Counter(months).most_common(1)[0]
        if top_m != target_m:
            need = top_count - months.count(target_m) + 1
            return [target_m] * need + months
    return months


def dominant(values):
    return Counter(values).most_common(1)[0][0] if values else None


def explicit_year(text, month):
    post_dates = [(int(m), int(y)) for m, y in POST_DATE_YEAR_RE.findall(text) if 1 <= int(m) <= 12]
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
        inferred = []
        for post_m, post_y in pairs:
            if post_m >= 11 and month <= 2:
                inferred.append(post_y + 1)
            else:
                inferred.append(post_y)
        return dominant(inferred)

    cleaned = re.sub(r"#\w+", "", text)
    years = [int(y) for y in YEAR_RE.findall(cleaned)]
    return dominant(years)


def nearest_year(month, today):
    now = today.year * 12 + today.month
    candidates = (today.year - 1, today.year, today.year + 1)
    return min(candidates, key=lambda y: abs(y * 12 + month - now))


def schedule_year(text, month, today):
    found = explicit_year(text, month)
    if found:
        return found
    max_future = 1 if today.day >= 20 else 0
    if today.month == 12 and month == 1 and max_future:
        return today.year + 1
    if month <= today.month + max_future:
        return today.year
    return today.year - 1


def resolve_year(text, month, mode, today):
    if mode == "nearest":
        return nearest_year(month, today)
    if mode == "schedule":
        return schedule_year(text, month, today)
    return explicit_year(text, month) or nearest_year(month, today)


def month_matches(found, want):
    return found == want or (want <= 2 and found in (1, 2))


def has_all(text, keys):
    return all(fold(key) in text for key in keys)


def parse_target(target):
    if not target:
        return None
    year, month = re.split(r"[-/]", target.strip())
    return int(year), int(month)