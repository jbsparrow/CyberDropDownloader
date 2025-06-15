from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Literal, NewType, TypeVar

from bs4 import BeautifulSoup
from pydantic import AfterValidator, AliasPath, BaseModel, Field, RootModel

from cyberdrop_dl.compat import StrEnum

if TYPE_CHECKING:
    from collections.abc import Iterator

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def unescape_html(string: Html) -> str:
    return BeautifulSoup(string, "html.parser").get_text(strip=True)


def add_utc_tz(parsed_date: datetime) -> datetime:
    return parsed_date.replace(tzinfo=UTC)


UnescapedStr = Annotated[str, AfterValidator(unescape_html)]
datetimeUTC = Annotated[datetime, AfterValidator(add_utc_tz)]  # noqa: N816


class ColletionType(StrEnum):
    TAG = "tag"
    CATEGORY = "category"


Html = NewType("Html", str)


class WordPressModel(BaseModel):
    id: int
    slug: str
    link: str


class Post(WordPressModel):
    date: datetime
    title: UnescapedStr = Field(validation_alias=AliasPath("title", "rendered"))
    content: Html = Field(validation_alias=AliasPath("content", "rendered"))
    thumbnail: str | None = Field(default=None, validation_alias=AliasPath("acf", "fifu_image_url"))
    date_gmt: datetimeUTC

    # Not used at the moment
    # A subclass may use it to add spscific logic on how to handle each post
    modified: datetime
    modified_gmt: datetimeUTC
    status: Literal["publish", "future", "draft", "pending", "private"]
    type: str
    categories: list[int] = []
    tags: list[int] = []
    format: Literal["standard", "aside", "chat", "gallery", "link", "image", "quote", "status", "video", "audio"]


class Category(WordPressModel):
    count: int
    description: str
    parent: int
    taxonomy: Literal["category"]
    _type: ColletionType = ColletionType.CATEGORY


class Tag(Category):
    taxonomy: Literal["post_tag"]
    _type: ColletionType = ColletionType.TAG


# TODO: Move to core `models.py`` module
class SequenceModel(RootModel[list[_ModelT]], Sequence[_ModelT]):
    def __len__(self) -> int:
        return len(self.root)

    def __iter__(self) -> Iterator[_ModelT]:
        yield from self.root

    def __getitem__(self, index: int) -> _ModelT:
        return self.root[index]

    def __bool__(self) -> bool:
        return bool(len(self))


class PostSequence(SequenceModel[Post]): ...


class TagSequence(SequenceModel[Tag]): ...


class CategorySequence(SequenceModel[Category]): ...
