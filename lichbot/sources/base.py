from abc import ABC, abstractmethod

from ..models import Poster
from ..policy import parse_target


class PosterSource(ABC):
    kind = ""

    def __init__(self, fb, publisher, options, today, context=None):
        self._fb = fb
        self._publisher = publisher
        self._opts = options
        self._today = today
        self._ctx = context

    def supports(self, target):
        """Cho phép nguồn tự quyết định có xử lý mốc thời gian này không."""
        return True

    @abstractmethod
    def fetch(self, target):
        ...

    def _poster(self, year, month, page):
        data = page.image_bytes()
        return Poster(
            year=year,
            month=month,
            data=data,
            ext=page.ext,
            width=page.width,
            height=page.height,
        )