"https://github.com/bluesky-social/atproto/blob/727701085829daf8e0440253346b5e70fc3810ad/lexicons/app/bsky/feed/defs.json"

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from cyberdrop_dl.utils.dataclass import deserialize

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
    record: Any
    indexed_at: str
    embed: EmbedView | None = None

    parse = classmethod(deserialize)

    @property
    def id(self) -> str:
        return self.uri.rpartition("/")[-1]

    @property
    def web_path(self) -> str:
        return f"profile/{self.author.handle}/post/{self.id}"


@dataclasses.dataclass(frozen=True, slots=True)
class AspectRatio:
    width: int
    height: int


@dataclasses.dataclass(frozen=True, slots=True)
class ImageView:
    # $type "app.bsky.embed.image#view"
    thumb: str
    fullsize: str
    alt: str
    aspect_ratio: AspectRatio | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class VideoView:
    # $type "app.bsky.embed.video#view"
    cid: str
    playlist: str
    thumbnail: str | None = None
    alt: str | None = None
    aspect_ratio: AspectRatio | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ViewExternal:
    uri: str
    title: str
    description: str
    thumb: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    source: ViewExternalSource | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ViewExternalSource:
    uri: str
    title: str
    icon: str | None = None
    description: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class EmbedView:
    images: list[ImageView]
    items: list[ImageView]
    external: ViewExternal | None = None
    video: VideoView | None = None
    # TODO: handle records (embeded posts): app.bsky.embed.record, app.bsky.embed.recordWithMedia
