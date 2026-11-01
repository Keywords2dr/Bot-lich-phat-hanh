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
    @abstractmethod
    def save(self, publisher, poster):
        ...


class LocalStore(PosterStore):
    def __init__(self, directory):
        self._dir = directory

    def save(self, publisher, poster):
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{publisher}_{poster.period}.{poster.ext}"
        path.write_bytes(poster.data)
        print("Da luu may:", path, "-", poster.width, "x", poster.height)
        return f"luu may: {path.name}"


class DriveStore(PosterStore):
    def __init__(self, root_folder, attempts=3, delay=8, sleep=time.sleep):
        from .google_drive import get_service

        self._service = get_service()
        self._root_name = root_folder
        self._attempts = attempts
        self._delay = delay
        self._sleep = sleep

    def save(self, publisher, poster):
        return with_retry(
            lambda: self._save_once(publisher, poster),
            attempts=self._attempts,
            delay=self._delay,
            sleep=self._sleep,
        )

    def _save_once(self, publisher, poster):
        from .google_drive import get_or_create_folder, upload

        root = get_or_create_folder(self._service, self._root_name)
        publisher_folder = get_or_create_folder(self._service, publisher, root)
        folder = get_or_create_folder(self._service, poster.period, publisher_folder)
        name = f"{publisher}_{poster.period}.{poster.ext}"
        query = f"name='{name}' and '{folder}' in parents and trashed=false"
        if self._service.files().list(q=query, fields="files(id)").execute()["files"]:
            print("Da co tren Drive, bo qua:", name)
            return f"da co tren Drive: {poster.period}"
        result = upload(self._service, folder, name, poster.data, poster.mime)
        print("OK:", result["webViewLink"])
        return f"da upload: {poster.period}"


class DedupStore(PosterStore):
    """Khử trùng ảnh (ví dụ lịch gộp Tháng 1 & 2) cho mọi Store."""

    def __init__(self, inner):
        self._inner = inner
        self._saved_hashes = {}

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