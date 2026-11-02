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
        fb.goto(url)
        fb.require_login()
        limit = self._opts.get("scan_limit", 8)
        links = fb.featured_links()[:limit]
        print("Dang chu y: so bai tim thay:", len(links))
        if not links:
            shot = fb.screenshot(f"debug_featured_{self._publisher.name}.png")
            print("Khong thay muc Dang chu y. Da chup man hinh:", shot)
            return None

        want = parse_target(target)
        keys = self._opts.get("required_keys", ["lich phat hanh"])
        mode = self._opts.get("year_mode", "explicit")
        candidates = []
        for i, href in enumerate(links, 1):
            page = fb.open_photo(href)
            month = identify_photo_month(page.text, page.months, img_bytes=page.data) if page else None
            if not month:
                print(f"Bai {i}: bo qua (khong nhan ra thang)")
                continue
            if not has_all(page.text, keys):
                tags = re.findall(r"#\w+", page.text)[:8]
                print(f"Bai {i}: bo qua (khong khop tu khoa) - hashtag thay duoc: {tags}")
                continue
            year = resolve_year(page.text, month, mode, self._today)
            print(
                f"Bai {i}: khop, thang {month} nam {year}",
                "(cac thang thay trong trang:", sorted(set(page.months)), ")",
            )
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

    def _sharper(self, href, page, keys, month):
        if FBID_RE.search(href):
            return page
        fb = self._fb
        fb.goto(href, wait=(3, 5))
        for photo_href in fb.thumb_links()[:2]:
            better = fb.open_photo(photo_href)
            if not better or better.width <= page.width:
                continue
            better_month = identify_photo_month(better.text, better.months, img_bytes=better.data)
            if has_all(better.text, keys) and better_month == month:
                return better
        return page