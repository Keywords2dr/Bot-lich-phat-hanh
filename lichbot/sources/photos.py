import re

from ..text_utils import dominant, has_all, parse_target, resolve_year
from .base import PosterSource


class PhotosSource(PosterSource):
    kind = "photos"

    def fetch(self, target):
        fb = self._fb
        want = parse_target(target)
        url = self._opts.get("url") or f"https://www.facebook.com/{self._publisher.slug}/photos"
        state_map = getattr(fb, "_photos_scan_state", None)
        if state_map is None:
            state_map = {}
            try:
                setattr(fb, "_photos_scan_state", state_map)
            except Exception:
                state_map = None

        state = state_map.get(url) if state_map is not None else None
        if state and want and want in state["found"]:
            page = state["found"][want]
            print(f"-> Lay ngay lich thang {want[1]} nam {want[0]} da quet san trong bo nho!")
            return self._poster(want[0], want[1], page)

        links = state["links"] if state else self._collect_links()
        if not links:
            shot = fb.screenshot(f"debug_photos_{self._publisher.name}.png")
            print("Khong thay anh nao trong album. Da chup man hinh:", shot)
            return None

        if state_map is not None and not state:
            state = {"links": links, "next_idx": 0, "found": {}}
            state_map[url] = state

        keys = self._opts.get("required_keys", [])
        mode = self._opts.get("year_mode", "explicit")
        newest_first = self._opts.get("order", "newest_first") != "oldest_first"
        older_streak = 0
        start_idx = state["next_idx"] if state else 0

        for idx in range(start_idx, len(links)):
            i = idx + 1
            href = links[idx]
            if state:
                state["next_idx"] = idx + 1
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
            if state and (year, month) not in state["found"]:
                state["found"][(year, month)] = page

            if not want or (month == want[1] and year == want[0]):
                return self._poster(year, month, page)

            if want and newest_first:
                want_total = want[0] * 12 + want[1]
                cur_total = year * 12 + month
                if cur_total < want_total:
                    older_streak += 1
                    if older_streak >= 2:
                        print(
                            f"-> Da lui qua moc {target} (dang o {year}-{month:02d}), dung quet album de tiet kiem thoi gian!"
                        )
                        break
                else:
                    older_streak = 0
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
            rounds = max(10, limit // 2 + 5)
            found = fb.gather_photos(fb.thumb_links, rounds=rounds, limit=limit, step=1500)
            links = found[:limit]
        print("Album anh: so anh doc duoc:", len(found), "- se kiem tra", len(links), "anh moi nhat")
        return links