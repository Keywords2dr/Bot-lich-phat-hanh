import io
import re
import unicodedata
from collections import Counter

from .policy import parse_target

TITLE_PATTERNS = [
    re.compile(r"(?:lich\s+phat\s+hanh|sach\s+moi|phat\s+hanh\s+du\s+kien)[^.\n\r]{0,35}?thang\s*0?(\d{1,2})(?!\d)"),
    re.compile(r"(?:manga\s*[-–]?\s*comic|comic|don\s+chao|chao\s+don|chao|tieu\s+diem)[^.\n\r]{0,35}?thang\s*0?(\d{1,2})(?!\d)"),
]

COMMENT_SPLIT_RE = re.compile(
    r"\b(?:phu\s+hop\s+nhat|tat\s+ca\s+binh\s+luan|binh\s+luan\s+lien\s+quan|viet\s+binh\s+luan|most\s+relevant)\b"
)
PROMO_RE = re.compile(
    r"\b(?:dai\s+tiec|freeship|flash\s*sale|giam\s+gia|gio\s+vang|mua\s+\d+\s+tang\s+\d+|hoi\s+sach|voucher|uu\s+dai|khuyen\s+mai|chao\s+he)\b"
)
MERGED_RE = re.compile(r"thang\s*0?1\s*(?:&|\+|va|[-–/])\s*(?:thang\s*)?0?2(?!\d)")
FB_POST_DATE_RE = re.compile(r"\b(?:ngay\s*)?\d{1,2}\s+thang\s*0?(\d{1,2})(?:\s*,?\s*(20\d\d))?")
FB_FULL_DATE_RE = re.compile(r"\b(?:ngay\s*)?(\d{1,2})\s+thang\s*0?(\d{1,2})(?:\s*,?\s*(20\d\d))?")
RELATIVE_TIME_RE = re.compile(r"\b\d+\s*(?:gio|phut|ngay)\b")
MONTH_WORD_RE = re.compile(r"\bthang\s*0?(\d{1,2})(?!\d)")
PAIR_RE = re.compile(r"\bthang\s*0?(\d{1,2})\s*[-–.,/]?\s*(20\d\d)\b")
YEAR_RE = re.compile(r"\b(20\d\d)\b")


def fold(text):
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def strip_comments(text):
    parts = COMMENT_SPLIT_RE.split(text, maxsplit=1)
    return parts[0] if parts else text


def is_merged_jan_feb(text, months=()):
    caption = strip_comments(text)
    if MERGED_RE.search(caption):
        return True
    s = set(months)
    return 1 in s and 2 in s and len(s - {1, 2, 12}) == 0


def find_title_month(text):
    caption = strip_comments(text)
    for pattern in TITLE_PATTERNS:
        match = pattern.search(caption)
        if match:
            m = int(match.group(1))
            if 1 <= m <= 12:
                return m
    return None


def ocr_image_month(img_bytes):
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        crop_box = img.crop((0, 0, int(w * 0.75), int(h * 0.65)))
        text = fold(pytesseract.image_to_string(crop_box, lang="vie+eng"))
        if PROMO_RE.search(text):
            return None
        m = find_title_month(text)
        if m:
            return m
        extracted = [int(x) for x in MONTH_WORD_RE.findall(text) if 1 <= int(x) <= 12]
        if extracted:
            return extracted[0]
    except Exception:
        pass
    return None


def infer_month_from_post_date(text, today=None):
    caption = strip_comments(text)
    if PROMO_RE.search(caption):
        return None
    for d_str, m_str, _ in FB_FULL_DATE_RE.findall(caption):
        day, month = int(d_str), int(m_str)
        if 1 <= day <= 31 and 1 <= month <= 12:
            if day <= 21:
                return month
            if day >= 25:
                return 1 if month == 12 else month + 1
            return None
    if today and RELATIVE_TIME_RE.search(caption):
        if today.day <= 21:
            return today.month
        if today.day >= 25:
            return 1 if today.month == 12 else today.month + 1
    return None


def extract_months(text):
    caption = strip_comments(text)
    masked_text = caption
    for match in FB_POST_DATE_RE.finditer(caption):
        start, end = match.span()
        prefix = caption[:start].strip()
        if not prefix.endswith("thang"):
            masked_text = masked_text[:start] + (" " * (end - start)) + masked_text[end:]

    found = [int(m) for m in MONTH_WORD_RE.findall(masked_text) if 1 <= int(m) <= 12]
    title_m = find_title_month(caption)
    if title_m and title_m not in found:
        found.insert(0, title_m)
    return found


def dominant(values):
    return Counter(values).most_common(1)[0][0] if values else None


def identify_photo_month(text, months, img_bytes=None, today=None):
    caption = strip_comments(text)
    title_m = find_title_month(caption)
    if title_m:
        return title_m
    if PROMO_RE.search(caption):
        return None
    m = dominant(months)
    if m:
        return m
    if img_bytes:
        ocr_m = ocr_image_month(img_bytes)
        if ocr_m:
            return ocr_m
    return infer_month_from_post_date(caption, today=today)


def explicit_year(text, month):
    caption = strip_comments(text)
    post_dates = [
        (int(m), int(y)) for m, y in FB_POST_DATE_RE.findall(caption)
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

    pairs = [(int(m), int(y)) for m, y in PAIR_RE.findall(caption) if 1 <= int(m) <= 12]
    exact = [y for m, y in pairs if m == month]
    if exact:
        return dominant(exact)
    if pairs and month:
        inferred = [
            post_y + 1 if post_m >= 11 and month <= 2 else post_y
            for post_m, post_y in pairs
        ]
        return dominant(inferred)

    cleaned = re.sub(r"#\w+", "", caption)
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