import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lichbot import facebook
from lichbot.facebook import FacebookSession
from lichbot.models import PhotoPage, Publisher
from lichbot.sources import build_sources
from lichbot.sources.album import AlbumSource
from lichbot.sources.featured import FeaturedSource
from lichbot.sources.hashtag import HashtagSource
from lichbot.sources.photos import PhotosSource
from lichbot.text_utils import fold

TODAY = date(2026, 11, 1)


def page_of(text, data=b"img", width=2048):
    folded = fold(text)
    import re
    months = tuple(int(m) for m in re.findall(r"thang\s*0?(\d{1,2})(?!\d)", folded))
    return PhotoPage(folded, months, data, "jpg", width, 1600)


class FakeFB:
    def __init__(self, albums=(), links=(), pages=None, featured=()):
        self._albums = list(albums)
        self._links = list(links)
        self._pages = pages or {}
        self._featured = list(featured)
        self.opened = []
        self.shots = []
        self.visited = []

    def goto(self, url, wait=(5, 7)):
        self.visited.append(url)

    def featured_links(self):
        return self._featured

    def require_login(self):
        pass

    def scroll(self, pixels=900):
        pass

    def album_links(self):
        return self._albums

    def thumb_links(self):
        return self._links

    def big_photo_links(self):
        return self._links

    def gather_photos(self, picker, rounds, limit=None, stable_rounds=0, step=900):
        links = list(picker())
        return links[:limit] if limit else links

    def screenshot(self, name):
        self.shots.append(name)
        return name

    def open_photo(self, href):
        self.opened.append(href)
        return self._pages.get(href)


PUB = Publisher(name="X", slug="x", sources=())


class AlbumSourceTest(unittest.TestCase):
    def setUp(self):
        self.albums = [
            {"href": "a2025", "text": "LỊCH PHÁT HÀNH MANGA-COMIC 2025"},
            {"href": "a2026", "text": "★★★ LỊCH PHÁT HÀNH MANGA-COMIC 2026 ★★★"},
        ]
        self.links = [f"p{i}" for i in range(1, 11)]
        self.pages = {f"p{i}": page_of(f"tháng {i + 1}") for i in range(1, 11)}
        self.pages["p1"] = page_of("tháng 1 và tháng 2")

    def make(self, **opts):
        fb = FakeFB(self.albums, self.links, self.pages)
        return fb, AlbumSource(fb, PUB, opts, TODAY)

    def test_latest_is_last_photo(self):
        fb, src = self.make()
        poster = src.fetch(None)
        self.assertEqual((poster.year, poster.month), (2026, 11))
        self.assertEqual(fb.opened, ["p10"])

    def test_target_month(self):
        fb, src = self.make()
        poster = src.fetch("2026-11")
        self.assertEqual(poster.period, "2026-11")
        self.assertEqual(fb.opened[0], "p10")

    def test_target_jan_accepts_merged_poster(self):
        fb, src = self.make()
        poster = src.fetch("2026-02")
        self.assertEqual(poster.period, "2026-02")

    def test_previous_year_offset_skipped_with_target(self):
        fb, src = self.make(year_offset=-1)
        self.assertIsNone(src.fetch("2026-11"))
        self.assertEqual(fb.opened, [])

    def test_previous_year_album(self):
        fb, src = self.make(year_offset=-1)
        poster = src.fetch(None)
        self.assertEqual(poster.year, 2025)

    def test_missing_album(self):
        fb = FakeFB(albums=[], links=[], pages={})
        self.assertIsNone(AlbumSource(fb, PUB, {}, TODAY).fetch(None))


class HashtagSourceTest(unittest.TestCase):
    def test_latest_by_year_and_month(self):
        pages = {
            "a": page_of("Kim Đồng #Lich_phat_hanh THÁNG 9 - 2026"),
            "b": page_of("Kim Đồng THÁNG 10 - 2026"),
            "c": page_of("Kim Đồng THÁNG 12 - 2025"),
            "d": page_of("Nha khac THÁNG 12 - 2026"),
            "e": page_of("Kim Đồng thang 7 khong co nam"),
        }
        fb = FakeFB(links=list(pages), pages=pages)
        src = HashtagSource(fb, PUB, {"url": "u", "text_key": "kim dong"}, TODAY)
        poster = src.fetch(None)
        self.assertEqual(poster.period, "2026-10")

    def test_target(self):
        pages = {
            "a": page_of("Kim Đồng THÁNG 10 - 2026"),
            "b": page_of("Kim Đồng THÁNG 11 - 2026"),
        }
        fb = FakeFB(links=list(pages), pages=pages)
        src = HashtagSource(fb, PUB, {"url": "u", "text_key": "kim dong"}, TODAY)
        self.assertEqual(src.fetch("2026-11").period, "2026-11")
        self.assertIsNone(src.fetch("2026-12"))

    def test_no_links_takes_screenshot(self):
        fb = FakeFB(links=[], pages={})
        src = HashtagSource(fb, PUB, {"url": "u"}, TODAY)
        self.assertIsNone(src.fetch(None))
        self.assertEqual(len(fb.shots), 1)


class PhotosSourceTest(unittest.TestCase):
    OPTS = {"required_keys": ["thang_nay_ipm_co_gi"], "year_mode": "nearest"}

    def pages(self):
        return {
            "p1": page_of("#IPM comingsoon tháng 12 sách mới"),
            "p2": page_of("#Tháng_này_IPM_có_gì THÁNG 11 #lịch_phát_hành"),
            "p3": page_of("#Tháng_này_IPM_có_gì THÁNG 10"),
        }

    def test_newest_first_skips_posts_without_hashtag(self):
        pages = self.pages()
        fb = FakeFB(links=["p1", "p2", "p3"], pages=pages)
        poster = PhotosSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None)
        self.assertEqual(poster.period, "2026-11")
        self.assertEqual(fb.opened, ["p1", "p2"])

    def test_oldest_first_reverses(self):
        pages = self.pages()
        fb = FakeFB(links=["p3", "p2", "p1"], pages=pages)
        opts = dict(self.OPTS, order="oldest_first")
        poster = PhotosSource(fb, PUB, opts, TODAY).fetch(None)
        self.assertEqual(poster.period, "2026-11")

    def test_target(self):
        pages = self.pages()
        fb = FakeFB(links=["p1", "p2", "p3"], pages=pages)
        poster = PhotosSource(fb, PUB, dict(self.OPTS), TODAY).fetch("2026-10")
        self.assertEqual(poster.period, "2026-10")

    def test_year_rolls_over(self):
        pages = {"p1": page_of("#Tháng_này_IPM_có_gì THÁNG 1")}
        fb = FakeFB(links=["p1"], pages=pages)
        poster = PhotosSource(fb, PUB, dict(self.OPTS), date(2026, 12, 28)).fetch(None)
        self.assertEqual(poster.period, "2027-01")


class FeaturedSourceTest(unittest.TestCase):
    OPTS = {"required_keys": ["lich phat hanh"]}

    def test_picks_latest_matching_card(self):
        pages = {
            "https://x/photo/?fbid=1": page_of("QUY HOC BONG tháng 10"),
            "https://x/photo/?fbid=2": page_of("LỊCH PHÁT HÀNH THÁNG 10.2026"),
            "https://x/photo/?fbid=3": page_of("LỊCH PHÁT HÀNH THÁNG 11.2026"),
        }
        fb = FakeFB(featured=list(pages), pages=pages)
        poster = FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None)
        self.assertEqual(poster.period, "2026-11")

    def test_target_month(self):
        pages = {
            "https://x/photo/?fbid=2": page_of("LỊCH PHÁT HÀNH THÁNG 10.2026"),
            "https://x/photo/?fbid=3": page_of("LỊCH PHÁT HÀNH THÁNG 11.2026"),
        }
        fb = FakeFB(featured=list(pages), pages=pages)
        src = FeaturedSource(fb, PUB, dict(self.OPTS), TODAY)
        self.assertEqual(src.fetch("2026-10").period, "2026-10")
        self.assertIsNone(src.fetch("2026-12"))

    def test_hashtag_key_with_underscores(self):
        pages = {"https://x/photo/?fbid=3": page_of("#Lich_phat_hanh_comicKĐ THÁNG 11 - 2026!!")}
        fb = FakeFB(featured=list(pages), pages=pages)
        opts = {"required_keys": ["lich_phat_hanh_comickd"]}
        self.assertEqual(FeaturedSource(fb, PUB, opts, TODAY).fetch(None).period, "2026-11")

    def test_nothing_matching(self):
        pages = {"https://x/photo/?fbid=1": page_of("Sach moi thang 11")}
        fb = FakeFB(featured=list(pages), pages=pages)
        self.assertIsNone(FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None))

    def test_no_featured_section_takes_screenshot(self):
        fb = FakeFB(featured=[])
        self.assertIsNone(FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None))
        self.assertEqual(fb.shots, ["debug_featured_X.png"])

    def test_uses_sharper_photo_from_post(self):
        post = "https://x/posts/pfbid1"
        pages = {
            post: page_of("LỊCH PHÁT HÀNH THÁNG 11.2026", data=b"small", width=960),
            "https://x/photo/?fbid=9": page_of("LỊCH PHÁT HÀNH THÁNG 11.2026", data=b"big", width=2048),
        }
        fb = FakeFB(featured=[post], links=["https://x/photo/?fbid=9"], pages=pages)
        poster = FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None)
        self.assertEqual((poster.data, poster.width), (b"big", 2048))

    def test_keeps_post_image_when_photo_belongs_to_other_post(self):
        post = "https://x/posts/pfbid1"
        pages = {
            post: page_of("LỊCH PHÁT HÀNH THÁNG 11.2026", data=b"small", width=960),
            "https://x/photo/?fbid=9": page_of("Sach moi thang 11", data=b"other", width=2048),
        }
        fb = FakeFB(featured=[post], links=["https://x/photo/?fbid=9"], pages=pages)
        poster = FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None)
        self.assertEqual(poster.data, b"small")

    def test_photo_links_are_not_upgraded(self):
        link = "https://x/photo/?fbid=5"
        pages = {link: page_of("LỊCH PHÁT HÀNH THÁNG 11.2026")}
        fb = FakeFB(featured=[link], links=["https://x/photo/?fbid=6"], pages=pages)
        FeaturedSource(fb, PUB, dict(self.OPTS), TODAY).fetch(None)
        self.assertEqual(fb.opened, [link])


class RegistryTest(unittest.TestCase):
    def test_build_and_filter(self):
        pub = Publisher(
            name="X",
            slug="x",
            sources=({"type": "album"}, {"type": "hashtag", "url": "u"}, {"type": "photos"}, {"type": "featured"}),
        )
        self.assertEqual([s.kind for s in build_sources(None, pub, TODAY)], ["album", "hashtag", "photos", "featured"])
        self.assertEqual([s.kind for s in build_sources(None, pub, TODAY, {"photos"})], ["photos"])

    def test_unknown_type(self):
        pub = Publisher(name="X", slug="x", sources=({"type": "web"},))
        with self.assertRaises(Exception):
            build_sources(None, pub, TODAY)


class FakeMouse:
    def __init__(self):
        self.wheels = 0

    def wheel(self, x, y):
        self.wheels += 1


class FakePage:
    def __init__(self, clicked=0):
        self.mouse = FakeMouse()
        self._clicked = clicked
        self.evaluated = []

    def evaluate(self, script, *args):
        self.evaluated.append(script)
        return self._clicked


class GatherPhotosTest(unittest.TestCase):
    def setUp(self):
        self._orig = facebook.pause
        facebook.pause = lambda *a, **k: None

    def tearDown(self):
        facebook.pause = self._orig

    def session(self):
        return FacebookSession(FakePage(), None, Path("."))

    def test_dedupes_by_fbid_and_accumulates(self):
        batches = iter([
            ["https://x/photo/?fbid=1&set=a", "https://x/photo/?fbid=2"],
            ["https://x/photo/?fbid=2&other=1", "https://x/photo/?fbid=3"],
            [],
        ])
        s = self.session()
        links = s.gather_photos(lambda: next(batches), rounds=3)
        self.assertEqual(len(links), 3)

    def test_limit(self):
        s = self.session()
        links = s.gather_photos(lambda: [f"u?fbid={i}" for i in range(20)], rounds=5, limit=12)
        self.assertEqual(len(links), 20)
        self.assertEqual(s._page.mouse.wheels, 0)

    def test_stable_rounds_stop(self):
        s = self.session()
        s.gather_photos(lambda: ["u?fbid=1"], rounds=40, stable_rounds=3)
        self.assertEqual(s._page.mouse.wheels, 3)


class ExpandCaptionsTest(unittest.TestCase):
    def setUp(self):
        self._orig = facebook.pause
        self.pauses = []
        facebook.pause = lambda *a, **k: self.pauses.append(a)

    def tearDown(self):
        facebook.pause = self._orig

    def test_clicks_and_waits_when_buttons_found(self):
        page = FakePage(clicked=2)
        session = FacebookSession(page, None, Path("."))
        self.assertEqual(session.expand_captions(), 2)
        self.assertEqual(page.evaluated, [facebook.EXPAND_JS])
        self.assertEqual(len(self.pauses), 1)

    def test_no_wait_when_nothing_to_expand(self):
        page = FakePage(clicked=0)
        session = FacebookSession(page, None, Path("."))
        self.assertEqual(session.expand_captions(), 0)
        self.assertEqual(self.pauses, [])


if __name__ == "__main__":
    unittest.main()
