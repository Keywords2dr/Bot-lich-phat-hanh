class ScanContext:
    """Bộ nhớ trạng thái phiên quét dùng chung, không gắn thuộc tính ẩn vào FacebookSession."""

    def __init__(self):
        self.cached_albums = {}
        self.album_photo_months = {}
        self.photos_scan_state = {}
        self.featured_scan_state = {}

    def get_album(self, pub_slug, year, keys):
        return self.cached_albums.get((pub_slug, year, tuple(keys)))

    def set_album(self, pub_slug, year, keys, album_data):
        self.cached_albums[(pub_slug, year, tuple(keys))] = album_data

    def get_album_photos(self, pub_slug, year):
        return self.album_photo_months.setdefault((pub_slug, year), {})

    def get_photos_state(self, url):
        return self.photos_scan_state.setdefault(url, {"links": [], "next_idx": 0, "found": {}})

    def get_featured_state(self, key):
        return self.featured_scan_state.setdefault(key, {"links": None, "entries": {}})

    def all_known_periods(self, pub_slug=None, year=None):
        periods = set()
        for state in self.photos_scan_state.values():
            periods.update(state.get("found", {}).keys())
        for (slug, y), visited in self.album_photo_months.items():
            if pub_slug and slug != pub_slug:
                continue
            if year and y != year:
                continue
            for m, page in visited.values():
                if m:
                    periods.add((y, m))
        return periods