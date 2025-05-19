"""Custom types for type annotations


1. Only add types here if they do NOT depend on any runtime import from `cyberdrop_dl` itself, except utils
2. Only add types here if they are going to be used across multiple modules
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, NewType, TypeAlias, TypeGuard, TypeVar

import yarl
from pydantic import (
    AfterValidator,
    AnyUrl,
    BaseModel,
    BeforeValidator,
    ByteSize,
    ConfigDict,
    NonNegativeInt,
    PlainSerializer,
    PlainValidator,
    Secret,
    SerializationInfo,
    StringConstraints,
    model_serializer,
    model_validator,
)

from cyberdrop_dl.utils.converters import change_path_suffix, convert_byte_size_to_str
from cyberdrop_dl.utils.validators import (
    parse_apprise_url,
    parse_falsy_as_none,
    parse_list,
    pydantyc_yarl_url,
)

if TYPE_CHECKING:

    class AbsoluteHttpURL(yarl.URL):
        absolute: Literal[True]
        scheme: Literal["http", "https"]

        @property
        def host(self) -> str:  # type: ignore
            """Decoded host part of URL."""

else:
    AbsoluteHttpURL = yarl.URL


def is_absolute_http_url(url: yarl.URL) -> TypeGuard[AbsoluteHttpURL]:
    return url.absolute and url.scheme.startswith("http")


# ~~~~~ Strings ~~~~~~~
StrSerializer = PlainSerializer(str, return_type=str, when_used="json-unless-none")
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
NonEmptyStrOrNone = Annotated[NonEmptyStr | None, BeforeValidator(parse_falsy_as_none)]
ListNonEmptyStr = Annotated[list[NonEmptyStr], BeforeValidator(parse_list)]

# ~~~~~ Paths ~~~~~~~
PathOrNone = Annotated[Path | None, BeforeValidator(parse_falsy_as_none)]
LogPath = Annotated[Path, AfterValidator(partial(change_path_suffix, suffix=".csv"))]
MainLogPath = Annotated[LogPath, AfterValidator(partial(change_path_suffix, suffix=".log"))]

# URL with pydantic.HttpUrl validation (must be absolute, must be http/https, detailed validation error).
# In type hints it's a yarl.URL. After validation the result is parsed with `parse_url` so this is also a yarl.URL at runtime
# Only use for config validation. To parse URLs internally while scraping, call `parse_url` directly
HttpURL = Annotated[yarl.URL, PlainValidator(pydantyc_yarl_url), StrSerializer]

# ~~~~~ Others ~~~~~~~
ByteSizeSerilized = Annotated[ByteSize, PlainSerializer(convert_byte_size_to_str, return_type=str)]
ListNonNegativeInt = Annotated[list[NonNegativeInt], BeforeValidator(parse_list)]


class AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class AppriseURLModel(FrozenModel):
    url: Secret[AnyUrl]
    tags: set[str] = set()

    @model_serializer()
    def serialize(self, info: SerializationInfo) -> str:
        dump_secret = info.mode != "json"
        url = self.url.get_secret_value() if dump_secret else self.url
        tags = self.tags - set("no_logs")
        tags = sorted(tags)
        return f"{','.join(tags)}{'=' if tags else ''}{url}"

    @model_validator(mode="before")
    @staticmethod
    def parse_input(value: yarl.URL | dict | str) -> dict:
        return parse_apprise_url(value)


class HttpAppriseURL(AppriseURLModel):
    url: Secret[HttpURL]


# DEPRECATED
# HttpURL = Annotated[HttpUrl, AfterValidator(convert_to_yarl), StrSerializer]


T = TypeVar("T")
Array: TypeAlias = list[T] | tuple[T, ...]
CMD: TypeAlias = Array[str]
U32Int: TypeAlias = int
U32IntArray: TypeAlias = Array[U32Int]
U32IntSequence: TypeAlias = Sequence[U32Int]
AnyDict: TypeAlias = dict[str, Any]

AbsolutePath = NewType("AbsolutePath", Path)
HashValue = NewType("HashValue", str)
TimeStamp = NewType("TimeStamp", int)
