from ..text_utils import dominant, fold, month_matches, parse_target, resolve_year
from .base import PosterSource


class HashtagSource(PosterSource):
    kind = "hashtag"

    def fetch(self, target):
        fb = self._fb
        limit = self._opts.get("scan_limit", 12)
        mode = self._opts.get("year_mode", "explicit")
        fb.goto(self._opts["url"])
        fb.require_login()
        links = fb.gather_photos(fb.big_photo_links, rounds=10, limit=limit)[:limit]
        print("Hashtag: so anh tim thay:", len(links))
        if not links:
            shot = fb.screenshot(f"debug_hashtag_{self._publisher.name}.png")
            print("Khong thay link anh nao trong trang hashtag. Da chup man hinh:", shot)
            return None

        want = parse_target(target)
        candidates = []
        for i, href in enumerate(links, 1):
            page = fb.open_photo(href)
            month = dominant(page.months) if page else None
            if not page or not month or not self._from_publisher(page.text):
                print(f"Anh {i}: bo qua")
                continue
            year = resolve_year(page.text, month, mode, self._today)
            print(f"Anh {i}: thang {month} nam {year}")
            if want:
                if month_matches(month, want[1]) and year in (want[0], None):
                    return self._poster(want[0], want[1], page)
            elif year:
                candidates.append((year, month, page))
        if want or not candidates:
            return None
        year, month, page = max(candidates, key=lambda c: (c[0], c[1]))
        print("Anh moi nhat tren hashtag la thang", month, "nam", year)
        return self._poster(year, month, page)

    def _from_publisher(self, text):
        key = self._opts.get("text_key")
        return fold(key) in text if key else True