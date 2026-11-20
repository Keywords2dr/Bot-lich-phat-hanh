import io
import re
from urllib.parse import urljoin

import requests
from PIL import Image

from ..models import BotError, Poster
from ..policy import parse_target
from .base import PosterSource

NXBTRE_LIST_URL = "https://www.nxbtre.com.vn/thong-tin/lich-phat-hanh-sach/"
LINK_RE = re.compile(r'href=["\']([^"\']*lich-phat-hanh[^"\']*\.html)["\']', re.I)
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
MONTH_YEAR_RE = re.compile(
    r"thang[-_](\d{1,2})(?:[-_&]+(\d{1,2}))?[-_](?:nam[-_])?(20\d{2})",
    re.I,
)
FALLBACK_MY_RE = re.compile(r"(?<!\d)(\d{1,2})[-_.](20\d{2})(?!\d)")


def _detect_ext_and_size(data: bytes) -> tuple[str, int, int]:
    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
        fmt = (img.format or "JPEG").upper()
    ext_map = {"JPEG": "jpg", "JPG": "jpg", "PNG": "png", "WEBP": "webp"}
    return ext_map.get(fmt, "jpg"), w, h


def _parse_link_period(url: str) -> tuple[int, list[int]] | None:
    match = MONTH_YEAR_RE.search(url)
    if match:
        m1 = int(match.group(1))
        m2 = int(match.group(2)) if match.group(2) else None
        year = int(match.group(3))
        months = [m for m in (m1, m2) if m is not None and 1 <= m <= 12]
        if months:
            return year, months

    fallback = FALLBACK_MY_RE.search(url)
    if fallback:
        month = int(fallback.group(1))
        year = int(fallback.group(2))
        if 1 <= month <= 12:
            return year, [month]

    return None


def _is_comic_link(url: str) -> bool:
    lowered = url.lower()
    return "truyen-tranh" in lowered or "manga" in lowered or "comic" in lowered


class NxbTreWebSource(PosterSource):
    kind = "nxbtre_web"

    def _get_session_and_cache(self) -> tuple[requests.Session, dict[str, str]]:
        http = getattr(self._fb, "_http", None)
        if http is None:
            http = requests.Session()
            http.headers.update({"User-Agent": "Mozilla/5.0"})
        if self._fb is not None:
            cache = getattr(self._fb, "_nxbtre_html_cache", None)
            if cache is None:
                cache = {}
                self._fb._nxbtre_html_cache = cache
            return http, cache
        return http, {}

    def _fetch_html(self, url: str) -> str:
        http, cache = self._get_session_and_cache()
        if url in cache:
            return cache[url]
        try:
            resp = http.get(url, timeout=25)
            resp.raise_for_status()
            cache[url] = resp.text
            return resp.text
        except requests.RequestException as exc:
            raise BotError(f"Lỗi truy cập trang NXB Trẻ ({url}): {exc}") from exc

    def _extract_entries(self, html: str, base_url: str) -> list[tuple[bool, int, list[int], str]]:
        entries = []
        seen = set()
        for raw_href in LINK_RE.findall(html):
            full_url = urljoin(base_url, raw_href)
            if full_url in seen:
                continue
            seen.add(full_url)
            parsed = _parse_link_period(full_url)
            if not parsed:
                continue
            year, months = parsed
            entries.append((_is_comic_link(full_url), year, months, full_url))
        return entries

    def _find_article(self, want: tuple[int, int] | None) -> tuple[int, int, str] | None:
        list_url = self._opts.get("url", NXBTRE_LIST_URL)
        html = self._fetch_html(list_url)
        entries = self._extract_entries(html, list_url)

        if want:
            wy, wm = want
            matched = [e for e in entries if e[1] == wy and wm in e[2]]
            if not matched and entries:
                detail_html = self._fetch_html(entries[0][3])
                more_entries = self._extract_entries(detail_html, entries[0][3])
                matched = [e for e in more_entries if e[1] == wy and wm in e[2]]
            if not matched:
                return None
            matched.sort(key=lambda e: (e[0], len(e[2]) == 1), reverse=True)
            return wy, wm, matched[0][3]

        if not entries:
            return None
        entries.sort(key=lambda e: (e[0], e[1], max(e[2])), reverse=True)
        best = entries[0]
        return best[1], max(best[2]), best[3]

    def _download_poster_image(self, detail_url: str) -> tuple[bytes, str, int, int] | None:
        http, _ = self._get_session_and_cache()
        html = self._fetch_html(detail_url)
        raw_srcs = list(dict.fromkeys(IMG_RE.findall(html)))

        primary = []
        fallback = []
        for src in raw_srcs:
            lowered = src.lower()
            if lowered.startswith("data:") or "/css/skin/" in lowered:
                continue
            full_url = urljoin(detail_url, src)
            if "/images/info/" in lowered:
                primary.append(full_url)
            else:
                fallback.append(full_url)

        candidates = (primary or fallback)[:5]
        best = None
        for img_url in candidates:
            try:
                resp = http.get(img_url, timeout=30)
                resp.raise_for_status()
                ext, w, h = _detect_ext_and_size(resp.content)
            except Exception:
                continue
            if w < 400 or h < 300:
                continue
            area = w * h
            if best is None or area > best[0]:
                best = (area, resp.content, ext, w, h, img_url)

        if not best:
            return None
        print(f"  [NXB-Tre Web] Chọn ảnh: {best[5]} ({best[3]}x{best[4]}, {best[2]})")
        return best[1], best[2], best[3], best[4]

    def fetch(self, target):
        want = parse_target(target)
        found = self._find_article(want)
        if not found:
            label = f"{want[1]:02d}/{want[0]}" if want else "mới nhất"
            print(f"  [NXB-Tre Web] Chưa có bài lịch phát hành {label} trên nxbtre.com.vn")
            return None

        year, month, detail_url = found
        print(f"  [NXB-Tre Web] Khớp bài {month:02d}/{year}: {detail_url}")
        downloaded = self._download_poster_image(detail_url)
        if not downloaded:
            print("  [NXB-Tre Web] Không tìm thấy ảnh lịch hợp lệ trong bài viết")
            return None

        data, ext, w, h = downloaded
        return Poster(
            year=year,
            month=month,
            data=data,
            ext=ext,
            width=w,
            height=h,
        )