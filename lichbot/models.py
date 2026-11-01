from dataclasses import dataclass
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
    data: bytes
    ext: str
    width: int
    height: int


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