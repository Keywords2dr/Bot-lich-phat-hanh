from ..text_utils import dominant, fold, month_matches, parse_target
from .base import PosterSource


class AlbumSource(PosterSource):
    kind = "album"

    def fetch(self, target):
        offset = self._opts.get("year_offset", 0)
        want = parse_target(target)
        if want and offset:
            return None
        year = want[0] if want else self._today.year + offset
        album = self._find_album(year)
        if not album:
            print("Khong thay album lich phat hanh nam", year)
            return None
        print("Album:", " ".join(album["text"].split())[:80])
        self._fb.goto(album["href"])
        links = self._fb.gather_photos(self._fb.thumb_links, rounds=8)
        print("So anh trong album:", len(links))
        if not links:
            return None
        if want:
            return self._by_month(links, year, want[1])
        return self._latest(links, year)

    def _find_album(self, year):
        fb = self._fb
        fb.goto(f"https://www.facebook.com/{self._publisher.slug}/photos_albums")
        fb.require_login()
        keys = [fold(k) for k in self._opts.get("keys", ["lich phat hanh"])]
        for _ in range(12):
            for album in fb.album_links():
                title = fold(album["text"])
                if all(k in title for k in keys) and str(year) in title:
                    return album
            fb.scroll()
        return None

    def _by_month(self, links, year, want_month):
        guess = 1 if want_month <= 2 else want_month
        order = sorted(range(1, len(links) + 1), key=lambda i: abs(i - guess))[:4]
        for i in order:
            page = self._fb.open_photo(links[i - 1])
            month = dominant(page.months) if page else None
            print(f"Thu anh {i}: thang nhan ra =", month)
            if page and month_matches(month, want_month):
                return self._poster(year, want_month, page)
        return None

    def _latest(self, links, year):
        page = self._fb.open_photo(links[-1])
        month = dominant(page.months) if page else None
        if not month:
            return None
        print("Anh moi nhat la thang", month)
        return self._poster(year, month, page)
