from ..text_utils import dominant, fold, is_merged_jan_feb, month_matches, parse_target
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
        keys = [fold(k) for k in self._opts.get("keys", ["lich phat hanh"])]
        cache_attr = "_cached_albums"
        cached = getattr(fb, cache_attr, {}).get((self._publisher.slug, year, tuple(keys)))
        if cached:
            return cached

        fb.goto(f"https://www.facebook.com/{self._publisher.slug}/photos_albums")
        fb.require_login()
        for _ in range(12):
            for album in fb.album_links():
                title = fold(album["text"])
                if all(k in title for k in keys) and str(year) in title:
                    if not hasattr(fb, cache_attr):
                        try:
                            setattr(fb, cache_attr, {})
                        except Exception:
                            return album
                    getattr(fb, cache_attr)[(self._publisher.slug, year, tuple(keys))] = album
                    return album
            fb.scroll()
        return None

    def _by_month(self, links, year, want_month):
        fb = self._fb
        idx_attr = "_album_photo_months"
        visited = getattr(fb, idx_attr, {}).get((self._publisher.slug, year), {})

        # Nếu ảnh của tháng này đã được mở ở lượt trước thì lấy luôn, không cần thử lại
        for i, (m, page) in visited.items():
            if page and month_matches(m, want_month):
                print(f"-> Lay ngay lich thang {want_month} nam {year} tu anh {i} da kiem tra truoc do!")
                return self._poster(year, want_month, page)

        guess = 1 if want_month <= 2 else min(want_month - 1, len(links))
        order = [i for i in sorted(range(1, len(links) + 1), key=lambda i: (abs(i - guess), i)) if i not in visited]
        max_try = self._opts.get("max_month_tries", 8)

        for i in order[:max_try]:
            page = fb.open_photo(links[i - 1])
            month = dominant(page.months) if page else None
            # Kiểm tra nếu đây là lịch gộp Tháng 1 & 2
            if page and is_merged_jan_feb(page.text, page.months):
                month = 1
            visited[i] = (month, page)
            if not hasattr(fb, idx_attr):
                try:
                    setattr(fb, idx_attr, {})
                except Exception:
                    pass
            if hasattr(fb, idx_attr):
                getattr(fb, idx_attr)[(self._publisher.slug, year)] = visited

            print(f"Thu anh {i}: thang nhan ra =", month)
            if page and month_matches(month, want_month):
                print(f"-> Da tim thay lich thang {want_month} nam {year} trong album (anh {i}), dung tim kiem!")
                return self._poster(year, want_month, page)
        return None

    def _latest(self, links, year):
        page = self._fb.open_photo(links[-1])
        month = dominant(page.months) if page else None
        if not month:
            return None
        print("Anh moi nhat la thang", month)
        return self._poster(year, month, page)