from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated

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
from pydantic import HttpUrl as PydanticHttpUrl

from .converters import change_path_suffix, convert_byte_size_to_str, convert_to_yarl
from .validators import parse_apprise_url, parse_falsy_as_none, parse_list

# ~~~~~ Strings ~~~~~~~
StrSerializer = PlainSerializer(str, return_type=str, when_used="json-unless-none")
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
NonEmptyStrOrNone = Annotated[NonEmptyStr | None, BeforeValidator(parse_falsy_as_none)]
ListNonEmptyStr = Annotated[list[NonEmptyStr], BeforeValidator(parse_list)]

# ~~~~~ Paths ~~~~~~~
PathOrNone = Annotated[Path | None, BeforeValidator(parse_falsy_as_none)]
LogPath = Annotated[Path, AfterValidator(partial(change_path_suffix, suffix=".csv"))]
MainLogPath = Annotated[LogPath, AfterValidator(partial(change_path_suffix, suffix=".log"))]

# ~~~~~ URLs ~~~~~~~
URLSerilized = Annotated[yarl.URL, StrSerializer]
HttpStr = Annotated[URLSerilized, PlainValidator(str)]  # URL in type hints, str at runtime
HttpStrURL = Annotated[HttpStr, AfterValidator(convert_to_yarl)]  # URL with str validation
HttpUrl = Annotated[URLSerilized, PlainValidator(PydanticHttpUrl)]  # URL in type hints, pydantic.HttpUrl at runtime
HttpURL = Annotated[HttpUrl, AfterValidator(convert_to_yarl)]  # URL with pydantic.HttpUrl validation

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
    def serialize(self, info: SerializationInfo):
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
