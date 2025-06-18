from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, NewType, TypeVar

from bs4 import BeautifulSoup
from pydantic import AfterValidator, AliasPath, BaseModel, Field

from cyberdrop_dl.compat import StrEnum
from cyberdrop_dl.models.base_models import SequenceModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def make_soup(string: str) -> BeautifulSoup:
    return BeautifulSoup(string, "html.parser")


def unescape_html(string: str) -> str:
    return make_soup(string).get_text(strip=True)


def add_utc_tz(parsed_date: datetime) -> datetime:
    return parsed_date.replace(tzinfo=UTC)


TitleFromHTML = Annotated[str, AfterValidator(unescape_html)]
AwareDatetimeUTC = Annotated[datetime, AfterValidator(add_utc_tz)]


class ColletionType(StrEnum):
    TAG = "tag"
    CATEGORY = "category"


HTML = NewType("HTML", str)


class WordPressModel(BaseModel):
    id: int | None = None
    slug: str
    link: str


class Post(WordPressModel):
    title: TitleFromHTML = Field(validation_alias=AliasPath("title", "rendered"))
    content: HTML = Field(validation_alias=AliasPath("content", "rendered"))
    thumbnail: str | None = Field(default=None, validation_alias=AliasPath("acf", "fifu_image_url"))
    date_gmt: AwareDatetimeUTC


class Collection(WordPressModel):
    description: str = ""
    taxonomy: str


class Category(Collection):
    taxonomy: Literal["category"] = "category"
    _type: ColletionType = ColletionType.CATEGORY


class Tag(Category):
    taxonomy: Literal["post_tag"] = "post_tag"
    _type: ColletionType = ColletionType.TAG


class PostSequence(SequenceModel[Post]): ...


class TagSequence(SequenceModel[Tag]): ...


class CategorySequence(SequenceModel[Category]): ...


class PostExtraData(Post):
    # Not used at the moment
    date: datetime
    modified: datetime
    modified_gmt: AwareDatetimeUTC
    status: Literal["publish", "future", "draft", "pending", "private"]
    type: str
    categories: list[int] = []
    tags: list[int] = []
    format: Literal["standard", "aside", "chat", "gallery", "link", "image", "quote", "status", "video", "audio"]


class CollectionExtraData(Collection):
    # Not used at the moment
    count: int
    parent: int
