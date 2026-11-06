import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lichbot import facebook
from lichbot.facebook import FacebookSession
from lichbot.models import PhotoPage, Poster, Publisher
from lichbot.runner import Runner
from lichbot.scan_context import ScanContext
from lichbot.sources.featured import FeaturedSource
from lichbot.storage import DedupStore, DriveStore, LocalStore, PosterStore, make_skip_check
from lichbot.text_utils import fold, identify_photo_month

TODAY = date(2026, 11, 1)


class DriveStub(PosterStore):
    skippable = True

    def __init__(self, have=()):
        self.have = set(have)
        self.saved = []
        self.checked = []

    def has(self, publisher, period):
        self.checked.append((publisher, period))
        return (publisher, period) in self.have

    def save(self, publisher, poster):
        self.saved.append((publisher, poster.period))
        return "saved " + poster.period


class CountingSource:
    kind = "album"

    def __init__(self):
        self.calls = 0

    def fetch(self, target):
        self.calls += 1
        year, month = (int(x) for x in target.split("-"))
        return Poster(year, month, b"x", "jpg", 10, 10)


def pub(name):
    return Publisher(name=name, slug=name.lower(), sources=())


class SkipExistingTest(unittest.TestCase):
    def run_with(self, stores, skip_check, publishers, targets):
        source = CountingSource()
        runner = Runner(
            session=None,
            stores=stores,
            today=TODAY,
            sleep=lambda s: None,
            source_factory=lambda session, publisher, today, kinds: [source],
            skip_check=skip_check,
        )
        return source, runner.run(publishers, targets=targets)

    def test_skips_scan_when_everything_exists(self):
        drive = DriveStub({("A", "2026-11"), ("A", "2026-10")})
        source, results = self.run_with([drive], make_skip_check([drive]), [pub("A")], ["2026-11", "2026-10"])
        self.assertEqual(source.calls, 0)
        self.assertEqual(drive.saved, [])
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(len(results), 2)

    def test_scans_only_missing_periods(self):
        drive = DriveStub({("A", "2026-11")})
        source, results = self.run_with([drive], make_skip_check([drive]), [pub("A")], ["2026-11", "2026-10"])
        self.assertEqual(source.calls, 1)
        self.assertEqual(drive.saved, [("A", "2026-10")])
        self.assertEqual([r.target for r in results], ["2026-11", "2026-10"])

    def test_no_skip_check_scans_everything(self):
        drive = DriveStub({("A", "2026-11")})
        source, _ = self.run_with([drive], None, [pub("A")], ["2026-11"])
        self.assertEqual(source.calls, 1)

    def test_no_wait_between_publishers_when_all_skipped(self):
        drive = DriveStub({("A", "2026-11"), ("B", "2026-11")})
        waits = []
        source = CountingSource()
        runner = Runner(
            session=None,
            stores=[drive],
            today=TODAY,
            sleep=waits.append,
            source_factory=lambda session, publisher, today, kinds: [source],
            skip_check=make_skip_check([drive]),
        )
        runner.run([pub("A"), pub("B")], targets=["2026-11"])
        self.assertEqual(waits, [])

    def test_target_none_is_never_skipped(self):
        drive = DriveStub()
        check = make_skip_check([drive])
        self.assertFalse(check("A", None))
        self.assertEqual(drive.checked, [])

    def test_local_store_alone_has_no_skip_check(self):
        self.assertIsNone(make_skip_check([LocalStore(Path("."))]))

    def test_check_failure_falls_back_to_scanning(self):
        class Broken(DriveStub):
            def has(self, publisher, period):
                raise RuntimeError("drive down")

        check = make_skip_check([Broken()])
        self.assertFalse(check("A", "2026-11"))

    def test_check_is_memoised(self):
        drive = DriveStub({("A", "2026-11")})
        check = make_skip_check([drive])
        check("A", "2026-11")
        check("A", "2026-11")
        self.assertEqual(len(drive.checked), 1)

    def test_dedup_store_forwards_skippable(self):
        drive = DriveStub({("A", "2026-11")})
        wrapped = DedupStore(drive)
        self.assertTrue(wrapped.skippable)
        self.assertTrue(wrapped.has("A", "2026-11"))
        self.assertFalse(DedupStore(LocalStore(Path("."))).skippable)


class DriveStoreTest(unittest.TestCase):
    def make_store(self):
        from lichbot import google_drive

        self.google_drive = google_drive
        self.folder_lookups = 0
        self.file_lookups = 0
        self.existing_folders = {}
        self.existing_files = {}
        outer = self

        def find_folder(service, name, parent="root"):
            outer.folder_lookups += 1
            return outer.existing_folders.get((name, parent))

        def create_folder(service, name, parent="root"):
            fid = f"id-{name}"
            outer.existing_folders[(name, parent)] = fid
            return fid

        def find_file(service, folder_id, names):
            outer.file_lookups += 1
            for n in names:
                if (folder_id, n) in outer.existing_files:
                    return "file-id"
            return None

        def upload(service, folder_id, filename, data, mime):
            outer.existing_files[(folder_id, filename)] = data
            return {"webViewLink": "http://x"}

        self.originals = (
            google_drive.find_folder,
            google_drive.create_folder,
            google_drive.find_file,
            google_drive.upload,
        )
        google_drive.find_folder = find_folder
        google_drive.create_folder = create_folder
        google_drive.find_file = find_file
        google_drive.upload = upload
        self.addCleanup(self.restore)
        return DriveStore("Root", service=object(), attempts=1, delay=0, sleep=lambda s: None)

    def restore(self):
        (
            self.google_drive.find_folder,
            self.google_drive.create_folder,
            self.google_drive.find_file,
            self.google_drive.upload,
        ) = self.originals

    def poster(self, month):
        return Poster(2026, month, b"data", "jpg", 1, 1)

    def test_has_is_false_without_creating_folders(self):
        store = self.make_store()
        self.assertFalse(store.has("A", "2026-11"))
        self.assertEqual(self.existing_folders, {})

    def test_save_then_has(self):
        store = self.make_store()
        store.save("A", self.poster(11))
        self.assertTrue(store.has("A", "2026-11"))
        self.assertFalse(store.has("A", "2026-10"))

    def test_folder_ids_are_cached_across_saves(self):
        store = self.make_store()
        store.save("A", self.poster(11))
        after_first = self.folder_lookups
        store.save("A", self.poster(10))
        self.assertEqual(self.folder_lookups - after_first, 1)

    def test_existing_file_is_not_uploaded_again(self):
        store = self.make_store()
        store.save("A", self.poster(11))
        message = store.save("A", self.poster(11))
        self.assertIn("da co tren Drive", message)

    def test_other_extension_counts_as_existing(self):
        store = self.make_store()
        store.save("A", Poster(2026, 11, b"d", "png", 1, 1))
        self.assertTrue(store.has("A", "2026-11"))


class LazyImageTest(unittest.TestCase):
    def make_page(self, calls, text="", months=()):
        def loader():
            calls.append(1)
            return b"bytes", "png"

        return PhotoPage(fold(text), tuple(months), None, "jpg", 2048, 1600, loader=loader)

    def test_loader_runs_once_and_updates_ext(self):
        calls = []
        page = self.make_page(calls)
        self.assertEqual(page.image_bytes(), b"bytes")
        self.assertEqual(page.image_bytes(), b"bytes")
        self.assertEqual(calls, [1])
        self.assertEqual(page.ext, "png")

    def test_page_with_data_never_calls_loader(self):
        page = PhotoPage("t", (), b"ready", "jpg", 1, 1)
        self.assertEqual(page.image_bytes(), b"ready")

    def test_month_from_caption_does_not_download(self):
        calls = []
        page = self.make_page(calls, "Lich phat hanh thang 11", months=(11,))
        month = identify_photo_month(page.text, page.months, img_bytes=page.image_bytes)
        self.assertEqual(month, 11)
        self.assertEqual(calls, [])

    def test_download_only_when_ocr_is_needed(self):
        calls = []
        page = self.make_page(calls, "khong co thang nao", months=())
        identify_photo_month(page.text, page.months, img_bytes=page.image_bytes)
        self.assertEqual(calls, [1])

    def test_failing_loader_does_not_break_identification(self):
        def broken():
            raise OSError("network")

        month = identify_photo_month("khong co thang", (), img_bytes=broken)
        self.assertIsNone(month)

    def test_plain_bytes_still_accepted(self):
        self.assertIsNone(identify_photo_month("khong co thang", (), img_bytes=b"not an image"))


class FakeResponse:
    ok = True
    status = 200
    headers = {"content-type": "image/png"}

    def body(self):
        return b"PNGDATA"


class FakeRequest:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return FakeResponse()


class FakeCtx:
    def __init__(self):
        self.request = FakeRequest()


class FakePage:
    def goto(self, href, wait_until=None):
        pass

    def wait_for_function(self, js, timeout=0):
        pass

    def evaluate(self, js, *args):
        if "naturalWidth" in js and "src" in js:
            return [
                {"src": "http://img/small.jpg", "w": 400, "h": 300},
                {"src": "http://img/big.jpg", "w": 2048, "h": 1600},
            ]
        return 0

    def inner_text(self, selector):
        return "Lich phat hanh thang 11"


class OpenPhotoLazyTest(unittest.TestCase):
    def setUp(self):
        self._pause = facebook.pause
        facebook.pause = lambda *a, **k: None
        self.addCleanup(lambda: setattr(facebook, "pause", self._pause))

    def test_open_photo_does_not_download_until_needed(self):
        ctx = FakeCtx()
        session = FacebookSession(FakePage(), ctx, Path("."))
        page = session.open_photo("https://www.facebook.com/photo?fbid=99")
        self.assertEqual(ctx.request.urls, [])
        self.assertEqual((page.width, page.height), (2048, 1600))
        self.assertEqual(page.image_bytes(), b"PNGDATA")
        self.assertEqual(ctx.request.urls, ["http://img/big.jpg"])
        self.assertEqual(page.ext, "png")

    def test_cached_photo_is_downloaded_at_most_once(self):
        ctx = FakeCtx()
        session = FacebookSession(FakePage(), ctx, Path("."))
        href = "https://www.facebook.com/photo?fbid=99"
        session.open_photo(href).image_bytes()
        session.open_photo(href).image_bytes()
        self.assertEqual(len(ctx.request.urls), 1)


class CachingFB:
    def __init__(self, pages, featured):
        self._pages = pages
        self._featured = featured
        self.goto_calls = 0
        self.opened = []

    def goto(self, url, wait=(5, 7)):
        self.goto_calls += 1

    def require_login(self):
        pass

    def featured_links(self):
        return self._featured

    def screenshot(self, name):
        return name

    def open_photo(self, href):
        self.opened.append(href)
        return self._pages.get(href)


class FeaturedCacheTest(unittest.TestCase):
    def make(self):
        pages = {
            "p1": PhotoPage(fold("Lich phat hanh thang 11 2026"), (11,), b"n", "jpg", 2000, 1500),
            "p2": PhotoPage(fold("Lich phat hanh thang 10 2026"), (10,), b"o", "jpg", 2000, 1500),
        }
        fb = CachingFB(pages, ["https://www.facebook.com/x/photo?fbid=1", "https://www.facebook.com/x/photo?fbid=2"])
        fb._pages = {
            "https://www.facebook.com/x/photo?fbid=1": pages["p1"],
            "https://www.facebook.com/x/photo?fbid=2": pages["p2"],
        }
        ctx = ScanContext()
        pub_ = Publisher(name="X", slug="x", sources=())
        return fb, FeaturedSource(fb, pub_, {}, TODAY, context=ctx)

    def test_page_is_loaded_once_for_several_targets(self):
        fb, src = self.make()
        self.assertEqual(src.fetch("2026-11").period, "2026-11")
        self.assertEqual(src.fetch("2026-10").period, "2026-10")
        self.assertEqual(fb.goto_calls, 1)

    def test_each_post_is_opened_once(self):
        fb, src = self.make()
        src.fetch("2026-11")
        src.fetch("2026-10")
        src.fetch("2026-11")
        self.assertEqual(len(fb.opened), len(set(fb.opened)))

    def test_without_context_still_works(self):
        fb, _ = self.make()
        src = FeaturedSource(fb, Publisher(name="X", slug="x", sources=()), {}, TODAY)
        self.assertEqual(src.fetch("2026-10").period, "2026-10")


if __name__ == "__main__":
    unittest.main()