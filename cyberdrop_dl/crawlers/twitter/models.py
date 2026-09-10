# Simplified version of https://github.com/FxEmbed/FxEmbed/blob/07612ab44d1a489489e97f0b219d09dcfdb10081/docs/specs/fxtwitter-openapi.json
from __future__ import annotations

import dataclasses
import operator
from typing import Any, Literal, NotRequired, final

from typing_extensions import TypedDict

from cyberdrop_dl.models import DeferredModel
from cyberdrop_dl.url_objects import AbsoluteHttpURL  # noqa: TC001

_score = operator.attrgetter("score")


class User(TypedDict):
    id: str
    name: str
    screen_name: str


@dataclasses.dataclass(slots=True)
class Photo:
    id: str
    type: Literal["photo", "gif"]
    url: AbsoluteHttpURL
    height: int
    width: int
    format: str | None = None
    altText: str | None = None  # noqa: N815
    transcode_url: AbsoluteHttpURL | None = None


@dataclasses.dataclass(slots=True)
class VideoFormat:
    url: AbsoluteHttpURL
    container: Literal["mp4", "webm", "m3u8"] | None = None
    codec: Literal["h264", "hevc", "vp9", "av1"] | None = None
    bitrate: int | None = None

    @property
    def score(self) -> tuple[int, int, int]:
        return (
            self.container != "m3u8",
            (None, "vp9", "h264", "hevc", "av1").index(self.codec),
            self.bitrate or 0,
        )


@dataclasses.dataclass(slots=True)
class Video:
    type: Literal["video", "gif"]
    url: AbsoluteHttpURL
    width: int
    height: int
    duration: float
    id: str | None = None
    format: str | None = None
    thumbnail_url: AbsoluteHttpURL | None = None
    transcode_url: AbsoluteHttpURL | None = None
    filesize: int | None = None
    formats: list[VideoFormat] = dataclasses.field(default_factory=list)

    @property
    def best_format(self) -> VideoFormat:
        return max(self.formats, key=_score)


@dataclasses.dataclass(slots=True)
class ExternalMedia:
    type: str
    url: AbsoluteHttpURL
    thumbnail_url: AbsoluteHttpURL | None = None
    height: int | None = None
    width: int | None = None


@dataclasses.dataclass(slots=True)
class PostMedia:
    external: ExternalMedia | None = None
    photos: list[Photo] = dataclasses.field(default_factory=list)
    videos: list[Video] = dataclasses.field(default_factory=list)
    mosaic: Any = None
    broadcast: Any = None


class CardImage(TypedDict):
    url: NotRequired[AbsoluteHttpURL]


@dataclasses.dataclass(slots=True)
class Card:
    """Preview card for external links (AKA embed)."""

    url: AbsoluteHttpURL
    title: str | None = None
    description: str | None = None
    domain: str | None = None
    card_name: str | None = None
    image: CardImage | None = None


class Facet(TypedDict):
    type: str  # "url", "mention", "hashtag", "bold", "media", "custom_emoji"
    original: NotRequired[AbsoluteHttpURL]
    replacement: NotRequired[AbsoluteHttpURL]


@dataclasses.dataclass(slots=True)
class RawText:
    text: str
    facets: list[Facet]


class _ArticleImageInfo(TypedDict):
    original_img_url: AbsoluteHttpURL


@dataclasses.dataclass(slots=True)
class _ArticleVideoVariant:
    url: AbsoluteHttpURL
    content_type: str
    bit_rate: int | None = None  # missing for m3u8 urls

    @property
    def score(self) -> tuple[bool, int]:
        return (self.url.suffix != ".m3u8", self.bit_rate or 0)


@final
@dataclasses.dataclass(slots=True)
class _ArticleVideoInfo:
    variants: list[_ArticleVideoVariant]


@dataclasses.dataclass(slots=True)
class MediaEntity:
    id: str
    media_key: str
    media_id: str
    media_info: _ArticleImageInfo | _ArticleVideoInfo

    @property
    def src(self) -> AbsoluteHttpURL:
        if type(self.media_info) is _ArticleVideoInfo:
            return max(self.media_info.variants, key=_score).url
        return self.media_info["original_img_url"]


@dataclasses.dataclass(slots=True)
class Article:
    created_at: str
    id: str
    title: str
    preview_text: str
    cover_media: MediaEntity
    content: dict[str, Any]
    media_entities: list[MediaEntity]
    modified_at: str | None = None


class Tweet(DeferredModel):
    type: Literal["status"]
    id: str
    url: AbsoluteHttpURL
    text: str
    created_at: str
    created_timestamp: int
    likes: int
    reposts: int
    quotes: int
    replies: int
    author: User
    media: PostMedia
    raw_text: RawText
    reposted_by: User | None = None
    card: Card | None = None
    lang: str | None = None
    article: Article | None = None


class Broadcast(DeferredModel):
    id: str
    media_key: str
    created_at_ms: int
    user_id: str
    twitter_user_id: str
    user_display_name: str
    username: str
    twitter_username: str
    is_locked: bool
    height: int
    width: int
    status: str | None = None
    tweet_id: str | None = None
