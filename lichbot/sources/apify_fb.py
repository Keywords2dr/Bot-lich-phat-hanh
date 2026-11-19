import io
import os
import re
import shutil
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image

from ..models import BotError, Poster
from ..policy import parse_target
from ..text_utils import (
    extract_months,
    fold,
    has_all,
    identify_photo_month,
    is_merged_jan_feb,
    month_matches,
    resolve_year,
)
from .base import PosterSource

VN_TZ = timezone(timedelta(hours=7))
APIFY_PHOTOS_ACTOR_URL = (
    "https://api.apify.com/v2/acts/automation_craft~facebook-photos-scraper/"
    "run-sync-get-dataset-items"
)

_TESSERACT_CONFIGURED = False


def _configure_tesseract():
    global _TESSERACT_CONFIGURED
    if _TESSERACT_CONFIGURED:
        return
    _TESSERACT_CONFIGURED = True
    try:
        import pytesseract
    except Exception:
        return
    if shutil.which("tesseract"):
        return
    for win_path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(win_path):
            pytesseract.pytesseract.tesseract_cmd = win_path
            return


def _format_published_at(raw_iso: str | None) -> str:
    if not raw_iso or not isinstance(raw_iso, str):
        return ""
    try:
        dt = datetime.fromisoformat(raw_iso.replace("Z", "+00:00")).astimezone(VN_TZ)
        return f"ngay {dt.day} thang {dt.month}, {dt.year}"
    except ValueError:
        return ""


def _parse_iso_ts(raw_iso: str | None) -> float:
    if not raw_iso or not isinstance(raw_iso, str):
        return 0.0
    try:
        return datetime.fromisoformat(raw_iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _detect_ext_and_size(data: bytes) -> tuple[str, int, int]:
    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
        fmt = (img.format or "JPEG").upper()
    ext_map = {"JPEG": "jpg", "JPG": "jpg", "PNG": "png", "WEBP": "webp"}
    return ext_map.get(fmt, "jpg"), w, h


def _photo_text(item: dict) -> str:
    caption = item.get("caption") or ""
    date_str = _format_published_at(item.get("publishedAt"))
    return fold(f"{caption}\n{date_str}".strip())


class ApifySession:
    """Gọi automation_craft~facebook-photos-scraper để tự dò Album theo năm và lấy ảnh kèm caption."""

    def __init__(
        self,
        token: str,
        results_limit: int = 40,
        days_back: int = 75,
        album_limit: int | None = None,
    ):
        self._token = token.strip()
        if not self._token:
            raise BotError("Thiếu APIFY_TOKEN để gọi Apify API.")
        self._max_albums_per_page = int(os.environ.get("APIFY_MAX_ALBUMS", "25"))
        self._default_album_photos = album_limit or int(
            os.environ.get("APIFY_ALBUM_LIMIT", "25")
        )
        self._albums_list_cache: dict[str, list[dict]] = {}
        self._album_photos_cache: dict[str, list[dict]] = {}
        self._image_cache: dict[str, bytes] = {}
        self._http = requests.Session()
        self._http.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            }
        )
        _configure_tesseract()

    def _call_actor(self, payload: dict) -> list[dict]:
        try:
            resp = self._http.post(
                APIFY_PHOTOS_ACTOR_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise BotError(f"Lỗi gọi Apify API: {exc}") from exc

        if not isinstance(data, list):
            raise BotError("Apify trả về dữ liệu không hợp lệ.")
        return data

    def list_page_albums(self, slug: str) -> list[dict]:
        if slug in self._albums_list_cache:
            print(
                f"[Apify] Dùng cache {len(self._albums_list_cache[slug])} album của '{slug}'."
            )
            return self._albums_list_cache[slug]

        page_url = f"https://www.facebook.com/{slug}"
        print(
            f"[Apify] Đang quét danh sách Album của '{page_url}' "
            f"(tối đa {self._max_albums_per_page} album)..."
        )
        items = self._call_actor(
            {
                "startUrls": [{"url": page_url}],
                "photoSources": ["albums"],
                "max_albums_per_profile": self._max_albums_per_page,
                "maxPhotosPerAlbum": 0,
            }
        )
        albums = [
            it
            for it in items
            if isinstance(it, dict) and it.get("type") == "album" and it.get("url")
        ]
        print(f"[Apify] Tìm thấy {len(albums)} album trên '{slug}'.")
        self._albums_list_cache[slug] = albums
        return albums

    def get_album_photos(self, album_url: str, max_photos: int | None = None) -> list[dict]:
        if album_url in self._album_photos_cache:
            print(
                f"[Apify] Dùng cache {len(self._album_photos_cache[album_url])} ảnh của album."
            )
            return self._album_photos_cache[album_url]

        limit = max_photos or self._default_album_photos
        print(f"[Apify] Đang đọc tối đa {limit} ảnh (kèm caption) từ '{album_url}'...")
        items = self._call_actor(
            {
                "startUrls": [{"url": album_url}],
                "maxPhotosPerAlbum": limit,
                "includeDetails": True,
            }
        )
        photos = [
            it
            for it in items
            if isinstance(it, dict) and it.get("type") == "photo" and it.get("imageUrl")
        ]
        print(f"[Apify] Đọc được {len(photos)} ảnh từ album.")
        self._album_photos_cache[album_url] = photos
        return photos

    def download_image(self, url: str) -> bytes:
        if url in self._image_cache:
            return self._image_cache[url]
        resp = self._http.get(url, timeout=45)
        resp.raise_for_status()
        self._image_cache[url] = resp.content
        return resp.content


class _BaseApifySource(PosterSource):
    def _build_poster(self, year: int, month: int, item: dict) -> Poster:
        data = self._fb.download_image(item["imageUrl"])
        ext, w, h = _detect_ext_and_size(data)
        print(f"  [Apify] Chọn ảnh lịch {month:02d}/{year} ({w}x{h}, {ext})")
        return Poster(
            year=year,
            month=month,
            data=data,
            ext=ext,
            width=w,
            height=h,
        )


YEAR_IN_TITLE_RE = re.compile(r"\b20\d\d\b")


class ApifyYearlyAlbumSource(_BaseApifySource):
    """Tự động tìm Album theo từ khóa + năm, hỗ trợ cả album tổng hợp không ghi năm."""

    kind = "apify_album"

    def supports(self, target):
        offset = self._opts.get("year_offset", 0)
        want = parse_target(target)
        if want and offset:
            return False
        return True

    def _find_album(self, year: int) -> tuple[dict | None, bool]:
        keys = [fold(k) for k in self._opts.get("keys", ["lich phat hanh"])]
        albums = self._fb.list_page_albums(self._publisher.slug)

        # Ưu tiên 1: Album ghi rõ năm mục tiêu
        for album in albums:
            title = fold(album.get("title") or "")
            if all(k in title for k in keys) and str(year) in title:
                return album, True

        # Ưu tiên 2: Album tổng hợp không ghi năm
        for album in albums:
            title = fold(album.get("title") or "")
            if all(k in title for k in keys) and not YEAR_IN_TITLE_RE.search(title):
                return album, False

        return None, False

    def fetch(self, target):
        offset = self._opts.get("year_offset", 0)
        want = parse_target(target)
        if want and offset:
            return None

        year = want[0] if want else self._today.year + offset
        album, has_year_in_title = self._find_album(year)
        if not album:
            print(f"  [Album] Không thấy album lịch phát hành năm {year}")
            return None

        title = " ".join((album.get("title") or "").split())[:80]
        item_count = int(album.get("itemCount") or 0)
        max_photos = min(max(item_count + 2, 16), 50)
        print(f"  [Album] Khớp: '{title}' ({item_count} ảnh)")

        photos = self._fb.get_album_photos(album["url"], max_photos=max_photos)
        if not photos:
            return None

        matched = []
        latest_all = []

        for idx, item in enumerate(photos, 1):
            text = _photo_text(item)
            months = extract_months(text)
            month = identify_photo_month(
                text,
                months,
                img_bytes=lambda u=item["imageUrl"]: self._fb.download_image(u),
                today=self._today,
            )
            if is_merged_jan_feb(text, months):
                month = 1

            if not month:
                print(f"  [Album] Ảnh #{idx}: bỏ qua (không nhận ra tháng)")
                continue

            photo_year = (
                year
                if has_year_in_title
                else resolve_year(text, month, "explicit", self._today)
            )
            ts = _parse_iso_ts(item.get("publishedAt"))
            has_explicit_month = bool(months)
            print(
                f"  [Album] Ảnh #{idx}: tháng {month:02d}/{photo_year} "
                f"(publishedAt={item.get('publishedAt') or 'N/A'})"
            )

            latest_all.append((photo_year, month, has_explicit_month, ts, idx, item))
            if want and photo_year == year and month_matches(month, want[1]):
                matched.append((has_explicit_month, ts, idx, item))

        if want:
            if not matched:
                return None
            matched.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            return self._build_poster(year, want[1], matched[0][3])

        if not latest_all:
            return None
        latest_all.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]), reverse=True)
        best = latest_all[0]
        return self._build_poster(best[0], best[1], best[5])

class ApifyPhotosAlbumSource(_BaseApifySource):
    """Quét trực tiếp Album tổng hợp nhiều năm như IPM_ALBUM, AMAK_ALBUM (giống photos.py)."""

    kind = "apify_photos"

    def fetch(self, target):
        album_url = self._opts.get("url")
        if not album_url:
            return None

        want = parse_target(target)
        keys = self._opts.get("required_keys", [])
        mode = self._opts.get("year_mode", "explicit")
        newest_first = self._opts.get("order", "newest_first") != "oldest_first"
        max_photos = min(int(self._opts.get("scan_limit", 25)), 30)

        photos = self._fb.get_album_photos(album_url, max_photos=max_photos)
        if not photos:
            return None

        candidates = []
        older_streak = 0

        for idx, item in enumerate(photos, 1):
            text = _photo_text(item)
            if not has_all(text, keys):
                tags = re.findall(r"#\w+", text)[:6]
                print(f"  [Photos] Ảnh #{idx}: bỏ qua (thiếu từ khóa) - hashtag: {tags}")
                continue

            months = extract_months(text)
            month = identify_photo_month(
                text,
                months,
                img_bytes=lambda u=item["imageUrl"]: self._fb.download_image(u),
                today=self._today,
            )
            if not month:
                print(f"  [Photos] Ảnh #{idx}: bỏ qua (không nhận ra tháng)")
                continue

            year = resolve_year(text, month, mode, self._today)
            ts = _parse_iso_ts(item.get("publishedAt"))
            has_explicit_month = bool(months)
            print(
                f"  [Photos] Ảnh #{idx}: khớp tháng {month:02d}/{year} "
                f"(caption_months={sorted(set(months))}, publishedAt={item.get('publishedAt') or 'N/A'})"
            )

            if want:
                wy, wm = want
                exact = (year, month) == want
                merged = (
                    year == wy
                    and wm in (1, 2)
                    and is_merged_jan_feb(text, months)
                )
                if exact or merged:
                    candidates.append((has_explicit_month, ts, -idx, wy, wm, item))
                    if has_explicit_month and newest_first:
                        break
                    continue

                if newest_first:
                    if year * 12 + month < wy * 12 + wm:
                        older_streak += 1
                        if older_streak >= 3 and not candidates:
                            print(
                                f"  [Photos] Đã lùi qua mốc {target} "
                                f"(đang ở {year:04d}-{month:02d}), dừng quét."
                            )
                            break
                    else:
                        older_streak = 0
            else:
                candidates.append((has_explicit_month, ts, -idx, year, month, item))
                if has_explicit_month and newest_first:
                    break

        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[3], c[4], c[1], c[2]), reverse=True)
        _, _, _, year, month, item = candidates[0]
        return self._build_poster(year, month, item)


def build_apify_sources(session, publisher, today, kinds=None, context=None):
    sources = []
    for options in publisher.sources:
        kind = options.get("type")
        if kind == "album":
            sources.append(
                ApifyYearlyAlbumSource(session, publisher, options, today, context=context)
            )
        elif kind == "photos" and options.get("url"):
            sources.append(
                ApifyPhotosAlbumSource(session, publisher, options, today, context=context)
            )
    return sources