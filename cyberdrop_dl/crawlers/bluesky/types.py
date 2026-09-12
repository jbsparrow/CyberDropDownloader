"https://github.com/bluesky-social/atproto/blob/727701085829daf8e0440253346b5e70fc3810ad/lexicons/app/bsky/feed/defs.json"

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Literal, Self, TypedDict

from cyberdrop_dl.models import type_adapter

if TYPE_CHECKING:
    from cyberdrop_dl.mediaprops import Resolution

type FeedFilter = Literal[
    "posts_with_replies",
    "posts_no_replies",
    "posts_with_media",
    "posts_and_author_threads",
    "posts_with_video",
]


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileViewBasic:
    did: str
    handle: str
    display_name: str | None = None
    created_at: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PostView:
    uri: str
    cid: str
    author: ProfileViewBasic
    record: dict[str, Any]  # This is typed as unknown on their spec

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return type_adapter(cls).validate_python(data)

    @property
    def id(self) -> str:
        return self.uri.rpartition("/")[-1]

    @property
    def web_path(self) -> str:
        return f"profile/{self.author.handle}/post/{self.id}"


Href = TypedDict("Href", {"$link": str})
Asset = TypedDict("Asset", {"$type": str})


class Blob(Asset):
    ref: Href
    mimeType: str  # noqa: N815
    size: int


class LegacyBlob(TypedDict):
    cid: str
    mimeType: str


class AspectRatio(TypedDict):
    width: int
    height: int


class Image(Asset):
    type: Literal["app.bsky.embed.image"]
    image: Blob | LegacyBlob
    alt: str
    aspectRatio: AspectRatio | None  # noqa: N815


class Images(Asset):
    type: Literal["app.bsky.embed.images"]
    images: list[Image]


class Gallery(Asset):
    type: Literal["app.bsky.embed.gallery"]
    items: list[Image | Video]


class Captions(TypedDict):
    lang: str
    file: Blob


class Video(Asset):
    type: Literal["app.bsky.embed.video"]
    video: Blob | LegacyBlob
    alt: str | None
    aspectRatio: AspectRatio | None  # noqa: N815
    captions: Captions | None


class External(Asset):
    type: Literal["app.bsky.embed.external"]
    uri: str
    title: str
    description: str
    thumb: Blob | LegacyBlob
    created_at: str | None
    updated_at: str | None


type MediaAsset = Video | Image | Images | Gallery | External


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Media:
    type: str
    cid: str
    name: str
    mime: str
    aspect_ratio: Resolution | None = None
