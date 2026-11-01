import re

from ..text_utils import dominant, has_all, parse_target, resolve_year
from .base import PosterSource


class PhotosSource(PosterSource):
    kind = "photos"

    def fetch(self, target):
        fb = self._fb
        links = self._collect_links()
        if not links:
            shot = fb.screenshot(f"debug_photos_{self._publisher.name}.png")
            print("Khong thay anh nao trong album. Da chup man hinh:", shot)
            return None

        want = parse_target(target)
        keys = self._opts.get("required_keys", [])
        mode = self._opts.get("year_mode", "explicit")
        for i, href in enumerate(links, 1):
            page = fb.open_photo(href)
            month = dominant(page.months) if page else None
            if not month:
                print(f"Anh {i}: bo qua (khong nhan ra thang)")
                continue
            if not has_all(page.text, keys):
                tags = re.findall(r"#\w+", page.text)[:8]
                print(f"Anh {i}: bo qua (thieu hashtag bat buoc) - hashtag thay duoc: {tags}")
                continue
            year = resolve_year(page.text, month, mode, self._today)
            print(
                f"Anh {i}: khop, thang {month} nam {year}",
                "(cac thang thay trong trang:", sorted(set(page.months)), ")",
            )
            if not want or (month == want[1] and year == want[0]):
                return self._poster(year, month, page)
        return None

    def _collect_links(self):
        fb = self._fb
        url = self._opts.get("url") or f"https://www.facebook.com/{self._publisher.slug}/photos"
        limit = self._opts.get("scan_limit", 12)
        oldest_first = self._opts.get("order", "newest_first") == "oldest_first"
        fb.goto(url)
        fb.require_login()
        if oldest_first:
            found = fb.gather_photos(fb.thumb_links, rounds=40, stable_rounds=3, step=1500)
            links = list(reversed(found))[:limit]
        else:
            found = fb.gather_photos(fb.thumb_links, rounds=10, limit=limit, step=1500)
            links = found[:limit]
        print("Album anh: so anh doc duoc:", len(found), "- se kiem tra", len(links), "anh moi nhat")
        return links
