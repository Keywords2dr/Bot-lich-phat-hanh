from ..models import BotError
from .album import AlbumSource
from .base import PosterSource
from .featured import FeaturedSource
from .hashtag import HashtagSource
from .photos import PhotosSource

REGISTRY = {cls.kind: cls for cls in (FeaturedSource, AlbumSource, HashtagSource, PhotosSource)}


def build_sources(fb, publisher, today, kinds=None):
    sources = []
    for options in publisher.sources:
        kind = options["type"]
        if kind not in REGISTRY:
            raise BotError("Loai nguon khong biet: " + kind)
        if kinds and kind not in kinds:
            continue
        sources.append(REGISTRY[kind](fb, publisher, options, today))
    return sources
