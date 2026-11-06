from dataclasses import dataclass, field
from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_PUBLISHED = "NOT_PUBLISHED"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


class BotError(Exception):
    pass


class LoginError(BotError):
    pass


@dataclass(frozen=True)
class Publisher:
    name: str
    slug: str
    sources: tuple


@dataclass(frozen=True)
class PhotoPage:
    text: str
    months: tuple
    data: bytes | None
    ext: str
    width: int
    height: int
    loader: object = field(default=None, repr=False, compare=False)

    def image_bytes(self):
        """Trả về dữ liệu ảnh; nếu chưa tải thì gọi loader (trả về (bytes, ext)) đúng một lần."""
        if self.data is None and self.loader is not None:
            data, ext = self.loader()
            object.__setattr__(self, "data", data)
            object.__setattr__(self, "ext", ext)
        return self.data


@dataclass(frozen=True)
class Poster:
    year: int
    month: int
    data: bytes
    ext: str
    width: int
    height: int

    @property
    def period(self):
        return f"{self.year}-{self.month:02d}"

    @property
    def mime(self):
        return "image/" + ("jpeg" if self.ext == "jpg" else self.ext)


@dataclass(frozen=True)
class RunResult:
    publisher: str
    target: str | None
    status: RunStatus
    message: str

    @property
    def ok(self):
        return self.status == RunStatus.SUCCESS