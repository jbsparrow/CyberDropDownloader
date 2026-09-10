import dataclasses
from typing import Annotated, Protocol, override

from pydantic import BeforeValidator, Field

from cyberdrop_dl.models import DeferredModel
from cyberdrop_dl.models.types import AwareDatetime
from cyberdrop_dl.models.validators import falsy_as, falsy_as_none


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class User:
    service: str
    id: str

    @property
    def web_path_qs(self) -> str:
        return f"{self.service}/user/{self.id}"


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Post:
    service: str
    user: str
    id: str

    @property
    def web_path_qs(self) -> str:
        return f"{self.service}/user/{self.user}/post/{self.id}"


@dataclasses.dataclass(slots=True, frozen=True)
class File:
    path: str = ""
    name: str | None = None  # Sometimes present
    server: str | None = None  # Sometimes present in attachments
    deferred: bool = False


@dataclasses.dataclass(slots=True, frozen=True)
class Embed:
    url: str
    subject: str | None = None
    description: str | None = None


def _parse_tags(tags: object) -> object:
    tags = falsy_as(tags, ())
    if type(tags) is str:
        if tags.startswith("{") and tags.endswith("}"):
            tags = tags[1:-1]
        return [t.strip('"') for t in tags.split(",")]
    return tags


class PostProtocol[T](Protocol):
    @property
    def id(self) -> str: ...
    @property
    def content(self) -> str | None: ...
    @property
    def file(self) -> T | None: ...
    @property
    def attachments(self) -> tuple[T, ...]: ...
    @property
    def published(self) -> AwareDatetime | None: ...
    @property
    def added(self) -> AwareDatetime | None: ...
    @property
    def timestamp(self) -> int | None: ...
    @property
    def tags(self) -> tuple[str, ...]: ...
    @property
    def preview_state(self) -> str | None: ...
    @property
    def has_full(self) -> bool: ...


class PostModel(DeferredModel, extra="ignore"):
    id: str
    content: str | None = None  # search results has no "content" key, only "substring"

    file: Annotated[File | None, BeforeValidator(falsy_as_none)] = None
    attachments: tuple[File, ...] = ()
    published: AwareDatetime | None = None
    added: AwareDatetime | None = None
    edited: AwareDatetime | None = None
    timestamp: int | None = None
    tags: Annotated[tuple[str, ...], BeforeValidator(_parse_tags)] = ()
    embed: Annotated[Embed | None, BeforeValidator(falsy_as_none)] = None
    preview_state: str | None = None
    has_full: bool = True

    @override
    def model_post_init(self, *_: object) -> None:
        if date := self.published or self.added:
            self.timestamp = int(date.timestamp())


class UserPostProtocol[T](PostProtocol[T], Protocol):
    @property
    def service(self) -> str: ...
    @property
    def user_id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def user_name(self) -> str | None: ...
    @property
    def user(self) -> User: ...
    @property
    def web_path_qs(self) -> str: ...


class UserPostModel(PostModel):
    service: str
    user_id: str = Field(validation_alias="user")
    title: str
    user_name: str | None = None

    @property
    def user(self) -> User:
        return User(self.service, self.user_id)

    @property
    def web_path_qs(self) -> str:
        return f"{self.service}/user/{self.user_id}/post/{self.id}"


class Creator(DeferredModel):
    id: str
    name: str
    displayName: str | None = None  # noqa: N815
