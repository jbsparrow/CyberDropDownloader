from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Literal

from pydantic import AliasPath, BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterable


class Link(BaseModel):
    url: str


class LinkCounts(Link):
    internal: bool
    reflection: bool
    title: str | None = None


class Post(BaseModel):
    hidden: bool
    deleted_at: str | None


class AvailablePost(Post):
    id: int
    title: str | None = None
    username: str
    created_at: datetime
    number: int = Field(validation_alias="post_number")
    content_html: str = Field(validation_alias="cooked")
    type: int = Field(validation_alias="post_type")
    updated_at: datetime
    content: str = Field(default="", validation_alias="raw")  # Only request to the `/posts` endpoint have it
    topic_id: int
    topic_slug: str
    user_id: int
    path: str = Field(validation_alias="post_url")
    link_counts: list[LinkCounts] = []
    hidden: Literal[False]
    deleted_at: None


class PostStream(BaseModel):
    all_posts: list[AvailablePost | Post] = Field(validation_alias=AliasPath("post_stream", "posts"))
    stream: list[int] = Field(default=[], validation_alias=AliasPath("post_stream", "stream"))
    id: int

    @property
    def posts(self) -> Iterable[AvailablePost]:
        for post in self.all_posts:
            if isinstance(post, AvailablePost):
                yield post


class Topic(PostStream):
    title: str
    created_at: datetime
    last_posted_at: datetime
    slug: str
    category_id: int
    user_id: int
    image_url: str | None = None
    current_post_number: int
    highest_post_number: int
    thumbnails: list[Link] = []
    init_post_number: int = 1

    @property
    def path(self) -> str:
        return f"t/{self.slug}/{self.id}"
