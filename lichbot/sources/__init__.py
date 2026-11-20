from ..models import BotError
from .album import AlbumSource
from .featured import FeaturedSource
from .hashtag import HashtagSource
from .nxbtre_web import NxbTreWebSource
from .photos import PhotosSource

REGISTRY = {
    cls.kind: cls
    for cls in (
        FeaturedSource,
        AlbumSource,
        HashtagSource,
        PhotosSource,
        NxbTreWebSource,
    )
}


def build_sources(fb, publisher, today, kinds=None, context=None):
    sources = []
    for options in publisher.sources:
        kind = options["type"]
        if kind not in REGISTRY:
            raise BotError("Loai nguon khong biet: " + kind)
        if kinds and kind != "nxbtre_web" and kind not in kinds:
            continue
        sources.append(REGISTRY[kind](fb, publisher, options, today, context=context))
    return sources