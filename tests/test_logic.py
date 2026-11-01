import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lichbot.models import LoginError, Poster, Publisher
from lichbot.runner import Runner
from lichbot.storage import PosterStore
from lichbot.text_utils import (
    dominant,
    explicit_year,
    extract_months,
    fold,
    has_all,
    month_matches,
    nearest_year,
    parse_target,
    resolve_year,
)


def make_poster(year=2026, month=11):
    return Poster(year, month, b"x", "jpg", 100, 100)


class FakeSource:
    def __init__(self, kind, poster=None, error=None):
        self.kind = kind
        self._poster = poster
        self._error = error
        self.calls = 0

    def fetch(self, target):
        self.calls += 1
        if self._error:
            raise self._error
        return self._poster


class FakeStore(PosterStore):
    def __init__(self):
        self.saved = []

    def save(self, publisher, poster):
        self.saved.append((publisher, poster.period))
        return "saved " + poster.period


def factory_for(mapping):
    def factory(session, publisher, today, kinds):
        return mapping[publisher.name]
    return factory


def pub(name):
    return Publisher(name=name, slug=name.lower(), sources=())


class TextUtilsTest(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(fold("LỊCH PHÁT HÀNH Đồng"), "lich phat hanh dong")

    def test_months(self):
        text = fold("Tháng 11 - 2026, THÁNG 11, tháng này IPM có gì, tháng 9")
        self.assertEqual(extract_months(text), [11, 11, 9])
        self.assertEqual(dominant(extract_months(text)), 11)

    def test_explicit_year(self):
        self.assertEqual(explicit_year(fold("THÁNG 10 - 2026!!"), 10), 2026)
        self.assertEqual(explicit_year(fold("THÁNG 10.2026"), 10), 2026)
        self.assertIsNone(explicit_year(fold("tháng 10 không có năm"), 10))

    def test_nearest_year(self):
        self.assertEqual(nearest_year(11, date(2026, 11, 1)), 2026)
        self.assertEqual(nearest_year(1, date(2026, 12, 28)), 2027)
        self.assertEqual(nearest_year(12, date(2027, 1, 3)), 2026)

    def test_resolve_year(self):
        today = date(2026, 11, 1)
        self.assertEqual(resolve_year("thang 3 - 2025", 3, "nearest", today), 2027)
        self.assertEqual(resolve_year("thang 3 - 2025", 3, "explicit", today), 2025)
        self.assertEqual(resolve_year("thang 11", 11, "explicit", today), 2026)

    def test_month_matches(self):
        self.assertTrue(month_matches(11, 11))
        self.assertTrue(month_matches(2, 1))
        self.assertFalse(month_matches(2, 3))
        self.assertFalse(month_matches(None, 1))

    def test_has_all(self):
        text = fold("#IPM #Tháng_này_IPM_có_gì #lịch_phát_hành")
        self.assertTrue(has_all(text, ["thang_nay_ipm_co_gi"]))
        self.assertFalse(has_all(text, ["comingsoon"]))
        self.assertTrue(has_all(text, []))

    def test_parse_target(self):
        self.assertEqual(parse_target("2026-11"), (2026, 11))
        self.assertIsNone(parse_target(None))


class RunnerTest(unittest.TestCase):
    def make(self, mapping, stores=None):
        stores = stores if stores is not None else [FakeStore()]
        runner = Runner(
            session=None,
            stores=stores,
            today=date(2026, 11, 1),
            sleep=lambda s: None,
            source_factory=factory_for(mapping),
        )
        return runner, stores

    def test_first_source_wins(self):
        first = FakeSource("album", make_poster())
        second = FakeSource("hashtag", make_poster(2026, 10))
        runner, stores = self.make({"A": [first, second]})
        results = runner.run([pub("A")])
        self.assertTrue(results[0].ok)
        self.assertEqual(stores[0].saved, [("A", "2026-11")])
        self.assertEqual(second.calls, 0)

    def test_fallback_to_next_source(self):
        first = FakeSource("album", None)
        second = FakeSource("hashtag", make_poster())
        runner, stores = self.make({"A": [first, second]})
        results = runner.run([pub("A")])
        self.assertTrue(results[0].ok)
        self.assertEqual((first.calls, second.calls), (1, 1))

    def test_failure_does_not_stop_others(self):
        runner, stores = self.make(
            {
                "A": [FakeSource("album", None)],
                "B": [FakeSource("photos", make_poster(2026, 10))],
            }
        )
        results = runner.run([pub("A"), pub("B")])
        self.assertFalse(results[0].ok)
        self.assertTrue(results[1].ok)
        self.assertEqual(stores[0].saved, [("B", "2026-10")])

    def test_login_error_stops_run(self):
        runner, stores = self.make(
            {
                "A": [FakeSource("album", error=LoginError("login"))],
                "B": [FakeSource("photos", make_poster())],
            }
        )
        results = runner.run([pub("A"), pub("B")])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(stores[0].saved, [])

    def test_no_matching_source_is_skipped(self):
        runner, stores = self.make({"A": []})
        results = runner.run([pub("A")])
        self.assertTrue(results[0].ok)
        self.assertEqual(stores[0].saved, [])

    def test_warns_when_poster_is_stale(self):
        runner, stores = self.make({"A": [FakeSource("photos", make_poster(2026, 6))]})
        result = runner.run([pub("A")])[0]
        self.assertTrue(result.ok)
        self.assertIn("CANH BAO", result.message)

    def test_no_warning_for_recent_poster(self):
        runner, stores = self.make({"A": [FakeSource("photos", make_poster(2026, 10))]})
        self.assertNotIn("CANH BAO", runner.run([pub("A")])[0].message)

    def test_no_warning_when_target_given(self):
        runner, stores = self.make({"A": [FakeSource("photos", make_poster(2026, 6))]})
        self.assertNotIn("CANH BAO", runner.run([pub("A")], target="2026-06")[0].message)

    def test_all_stores_receive_poster(self):
        runner, stores = self.make(
            {"A": [FakeSource("album", make_poster())]},
            stores=[FakeStore(), FakeStore()],
        )
        runner.run([pub("A")])
        self.assertEqual(stores[0].saved, stores[1].saved)
        self.assertEqual(len(stores[0].saved), 1)


if __name__ == "__main__":
    unittest.main()
