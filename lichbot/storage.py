import hashlib
import time
from abc import ABC, abstractmethod


def transient_errors():
    try:
        from google.auth.exceptions import TransportError

        return (OSError, TransportError)
    except ImportError:
        return (OSError,)


def with_retry(action, attempts=3, delay=8, sleep=time.sleep):
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except transient_errors() as error:
            if attempt == attempts:
                raise
            print(
                f"Loi mang ({type(error).__name__}), thu lai lan {attempt + 1}/{attempts} sau {delay}s"
            )
            sleep(delay)


class PosterStore(ABC):
    skippable = False

    @abstractmethod
    def save(self, publisher, poster):
        ...

    def has(self, publisher, period):
        return False


class LocalStore(PosterStore):
    def __init__(self, directory):
        self._dir = directory

    def save(self, publisher, poster):
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{publisher}_{poster.period}.{poster.ext}"
        path.write_bytes(poster.data)
        print("Da luu may:", path, "-", poster.width, "x", poster.height)
        return f"luu may: {path.name}"


POSTER_EXTS = ("jpg", "png", "webp")


class DriveStore(PosterStore):
    skippable = True

    def __init__(self, root_folder, attempts=3, delay=8, sleep=time.sleep, service=None):
        if service is None:
            from .google_drive import get_service

            service = get_service()
        self._service = service
        self._root_name = root_folder
        self._attempts = attempts
        self._delay = delay
        self._sleep = sleep
        self._folders = {}

    def _retry(self, action):
        return with_retry(action, attempts=self._attempts, delay=self._delay, sleep=self._sleep)

    def save(self, publisher, poster):
        return self._retry(lambda: self._save_once(publisher, poster))

    def has(self, publisher, period):
        return self._retry(lambda: self._has_once(publisher, period))

    def _folder(self, name, parent, create):
        from . import google_drive as drive

        key = (name, parent)
        if key in self._folders:
            return self._folders[key]
        parent_id = parent or "root"
        folder = drive.find_folder(self._service, name, parent_id)
        if folder is None and create:
            folder = drive.create_folder(self._service, name, parent_id)
        if folder is not None:
            self._folders[key] = folder
        return folder

    def _period_folder(self, publisher, period, create):
        folder = None
        for name in (self._root_name, publisher, period):
            folder = self._folder(name, folder, create)
            if folder is None:
                return None
        return folder

    def _existing_file(self, folder, publisher, period):
        from .google_drive import find_file

        names = [f"{publisher}_{period}.{ext}" for ext in POSTER_EXTS]
        return find_file(self._service, folder, names)

    def _has_once(self, publisher, period):
        folder = self._period_folder(publisher, period, create=False)
        if folder is None:
            return False
        return self._existing_file(folder, publisher, period) is not None

    def _save_once(self, publisher, poster):
        from .google_drive import upload

        folder = self._period_folder(publisher, poster.period, create=True)
        if self._existing_file(folder, publisher, poster.period):
            print("Da co tren Drive, bo qua:", f"{publisher}_{poster.period}")
            return f"da co tren Drive: {poster.period}"
        name = f"{publisher}_{poster.period}.{poster.ext}"
        result = upload(self._service, folder, name, poster.data, poster.mime)
        print("OK:", result["webViewLink"])
        return f"da upload: {poster.period}"


class DedupStore(PosterStore):
    """Khử trùng ảnh (ví dụ lịch gộp Tháng 1 & 2) cho mọi Store."""

    def __init__(self, inner):
        self._inner = inner
        self._saved_hashes = {}

    @property
    def skippable(self):
        return getattr(self._inner, "skippable", False)

    def has(self, publisher, period):
        return self._inner.has(publisher, period)

    def save(self, publisher, poster):
        digest = hashlib.sha256(poster.data).hexdigest()
        key = (publisher, digest)
        if key in self._saved_hashes:
            prev = self._saved_hashes[key]
            msg = f"lich gop chung voi {prev} (bo qua luu trung)"
            print(f"-> Phat hien lich gop: {poster.period} trung anh voi {prev}, bo qua!")
            return msg
        res = self._inner.save(publisher, poster)
        self._saved_hashes[key] = poster.period
        return res


def make_skip_check(stores):
    """Trả về hàm (publisher, target) -> bool: True nếu mọi kho 'skippable' đã có sẵn kỳ này."""
    checkers = [s for s in stores if getattr(s, "skippable", False)]
    if not checkers:
        return None
    memo = {}

    def check(publisher, target):
        from .policy import parse_target

        parsed = parse_target(target)
        if not parsed:
            return False
        period = f"{parsed[0]:04d}-{parsed[1]:02d}"
        key = (publisher, period)
        if key not in memo:
            try:
                memo[key] = all(s.has(publisher, period) for s in checkers)
                print(f"[Kiem tra Drive] {publisher} {period}: {'da co' if memo[key] else 'chua co'}")
            except Exception as error:
                print(f"Khong kiem tra duoc {publisher} {period} ({type(error).__name__}), se quet nhu binh thuong")
                memo[key] = False
        return memo[key]

    return check