from abc import ABC, abstractmethod

from ..models import Poster


class PosterSource(ABC):
    kind = ""

    def __init__(self, fb, publisher, options, today):
        self._fb = fb
        self._publisher = publisher
        self._opts = options
        self._today = today

    @abstractmethod
    def fetch(self, target):
        ...

    def _poster(self, year, month, page):
        return Poster(
            year=year,
            month=month,
            data=page.data,
            ext=page.ext,
            width=page.width,
            height=page.height,
        )
