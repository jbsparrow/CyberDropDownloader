from __future__ import annotations

from pathlib import Path
from typing import Annotated, TypeVar

import yarl
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ByteSize,
    NonNegativeInt,
    PlainSerializer,
    PlainValidator,
    StringConstraints,
)

from cyberdrop_dl.models.validators import (
    bytesize_to_str,
    change_path_suffix,
    falsy_as_list,
    falsy_as_none,
    to_yarl_url_w_pydantyc_validation,
)

T = TypeVar("T")
# ~~~~~ Strings ~~~~~~~
StrSerializer = PlainSerializer(str, return_type=str, when_used="json-unless-none")
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
NonEmptyStrOrNone = Annotated[NonEmptyStr | None, BeforeValidator(falsy_as_none)]
ListNonEmptyStr = Annotated[list[NonEmptyStr], BeforeValidator(falsy_as_list)]


# ~~~~~ Paths ~~~~~~~
PathOrNone = Annotated[Path | None, BeforeValidator(falsy_as_none)]
LogPath = Annotated[Path, AfterValidator(change_path_suffix(".csv"))]
MainLogPath = Annotated[LogPath, AfterValidator(change_path_suffix(".log"))]

# URL with pydantic.HttpUrl validation (must be absolute, must be http/https, detailed validation error).
# In type hints it's a yarl.URL. After validation the result is parsed with `parse_url` so this is also a yarl.URL at runtime
# Only use for config validation. To parse URLs internally while scraping, call `parse_url` directly
HttpURL = Annotated[yarl.URL, PlainValidator(to_yarl_url_w_pydantyc_validation), StrSerializer]

# ~~~~~ Others ~~~~~~~
ByteSizeSerilized = Annotated[ByteSize, PlainSerializer(bytesize_to_str, return_type=str)]
ListNonNegativeInt = Annotated[list[NonNegativeInt], BeforeValidator(falsy_as_list)]
ListPydanticURL = Annotated[list[HttpURL], BeforeValidator(falsy_as_list)]
