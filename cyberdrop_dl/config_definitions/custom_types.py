from __future__ import annotations

from typing import Annotated

from pydantic import (
    AfterValidator,
    AnyUrl,
    BaseModel,
    ConfigDict,
    HttpUrl,
    Secret,
    SerializationInfo,
    StringConstraints,
    model_serializer,
    model_validator,
)
from yarl import URL


def convert_to_yarl(value: AnyUrl) -> URL:
    return URL(str(value))


HttpURL = Annotated[HttpUrl, AfterValidator(convert_to_yarl)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
AnyURL = Annotated[AnyUrl, AfterValidator(convert_to_yarl)]
SecretAnyURL = Secret[AnyURL]
SecretHttpURL = Secret[HttpURL]


class AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class AppriseURLModel(FrozenModel):
    url: Secret[AnyUrl]
    tags: set[str]

    @model_serializer()
    def serialize(self, info: SerializationInfo):
        dump_secret = info.mode != "json"
        url = self.url.get_secret_value() if dump_secret else self.url
        tags = self.tags - set("no_logs")
        tags = sorted(tags)
        return f"{','.join(tags)}{'=' if tags else ''}{url}"

    @model_validator(mode="before")
    @staticmethod
    def parse_input(value: dict | URL | str):
        url = value
        tags = set()
        if isinstance(value, dict):
            tags = value.get("tags") or tags
            url = value.get("url", "")

        if isinstance(url, URL):
            url = str(url)
        parts = url.split("://", 1)[0].split("=", 1)
        if len(parts) == 2:
            tags = set(parts[0].split(","))
            url: str = url.split("=", 1)[-1]

        return {"url": url, "tags": tags}


class HttpAppriseURL(AppriseURLModel):
    url: Secret[HttpURL]
