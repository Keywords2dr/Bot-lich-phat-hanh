import re

from ..facebook import FBID_RE
from ..policy import parse_target
from ..text_utils import has_all, identify_photo_month, resolve_year
from .base import PosterSource


class FeaturedSource(PosterSource):
    kind = "featured"

    def supports(self, target):
        want = parse_target(target)
        if not want:
            return True
        months_ago = (self._today.year - want[0]) * 12 + (self._today.month - want[1])
        return months_ago < 2

    def fetch(self, target):
        fb = self._fb
        url = self._opts.get("url") or f"https://www.facebook.com/{self._publisher.slug}"
        limit = self._opts.get("scan_limit", 8)
        keys = self._opts.get("required_keys", ["lich phat hanh"])
        mode = self._opts.get("year_mode", "explicit")
        state = self._state(url, keys, mode, limit)

        if state is not None and state["links"] is not None:
            links = state["links"]
            print("Dang chu y: dung danh sach da quet truoc do, so bai:", len(links))
        else:
            fb.goto(url)
            fb.require_login()
            links = fb.featured_links()[:limit]
            if state is not None:
                state["links"] = links
            print("Dang chu y: so bai tim thay:", len(links))
            if not links:
                shot = fb.screenshot(f"debug_featured_{self._publisher.name}.png")
                print("Khong thay muc Dang chu y. Da chup man hinh:", shot)
        if not links:
            return None

        want = parse_target(target)
        candidates = []
        for i, href in enumerate(links, 1):
            entry = self._analyze(i, href, keys, mode, state)
            if entry is None:
                continue
            year, month, page = entry
            if want and (year, month) != want:
                continue
            candidates.append((year, month, href, page))
            if want:
                break
        if not candidates:
            return None
        year, month, href, page = max(candidates, key=lambda c: (c[0], c[1]))
        page = self._sharper(href, page, keys, month)
        print("Chon lich thang", month, "nam", year)
        return self._poster(year, month, page)

    def _state(self, url, keys, mode, limit):
        if not self._ctx:
            return None
        return self._ctx.get_featured_state((url, tuple(keys), mode, limit))

    def _analyze(self, i, href, keys, mode, state):
        entries = state["entries"] if state is not None else None
        if entries is not None and href in entries:
            entry = entries[href]
            if entry is not None:
                print(f"Bai {i}: dung ket qua da quet - thang {entry[1]} nam {entry[0]}")
            return entry

        entry = self._analyze_uncached(i, href, keys, mode)
        if entries is not None:
            entries[href] = entry
        return entry

    def _analyze_uncached(self, i, href, keys, mode):
        fb = self._fb
        page = fb.open_photo(href)
        month = identify_photo_month(page.text, page.months, img_bytes=page.image_bytes) if page else None
        if not month:
            print(f"Bai {i}: bo qua (khong nhan ra thang)")
            return None
        if not has_all(page.text, keys):
            tags = re.findall(r"#\w+", page.text)[:8]
            print(f"Bai {i}: bo qua (khong khop tu khoa) - hashtag thay duoc: {tags}")
            return None
        year = resolve_year(page.text, month, mode, self._today)
        print(
            f"Bai {i}: khop, thang {month} nam {year}",
            "(cac thang thay trong trang:", sorted(set(page.months)), ")",
        )
        return (year, month, page)

    def _sharper(self, href, page, keys, month):
        if FBID_RE.search(href):
            return page
        fb = self._fb
        fb.goto(href, wait=(3, 5))
        for photo_href in fb.thumb_links()[:2]:
            better = fb.open_photo(photo_href)
            if not better or better.width <= page.width:
                continue
            better_month = identify_photo_month(better.text, better.months, img_bytes=better.image_bytes)
            if has_all(better.text, keys) and better_month == month:
                return better
        return page