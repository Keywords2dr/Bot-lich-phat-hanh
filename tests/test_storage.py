import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lichbot.storage import with_retry


class Flaky:
    def __init__(self, failures, error=TimeoutError("timeout")):
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


class RetryTest(unittest.TestCase):
    def test_succeeds_after_transient_failures(self):
        action = Flaky(2)
        waits = []
        result = with_retry(action, attempts=3, delay=8, sleep=waits.append)
        self.assertEqual(result, "ok")
        self.assertEqual(action.calls, 3)
        self.assertEqual(waits, [8, 8])

    def test_gives_up_after_attempts(self):
        action = Flaky(5)
        with self.assertRaises(TimeoutError):
            with_retry(action, attempts=3, delay=1, sleep=lambda s: None)
        self.assertEqual(action.calls, 3)

    def test_other_errors_are_not_retried(self):
        action = Flaky(5, error=ValueError("bad"))
        with self.assertRaises(ValueError):
            with_retry(action, attempts=3, delay=1, sleep=lambda s: None)
        self.assertEqual(action.calls, 1)


if __name__ == "__main__":
    unittest.main()
