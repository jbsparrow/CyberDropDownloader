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
    url: SecretAnyURL
    tags: set[str]

    @model_serializer()
    def serialize(self, info: SerializationInfo):
        dump_secret = info.mode != "json"
        url = self.url.get_secret_value() if dump_secret else self.url
        tags = self.tags - set("no_logs")
        return f"{','.join(tags)}{'=' if tags else ''}{url}"

    @model_validator(mode="before")
    @staticmethod
    def parse_input(value: dict | URL | str):
        url_obj = value
        tags = None
        if isinstance(url_obj, dict):
            tags = url_obj.get("tags")
            url_obj = url_obj.get("url")
        if isinstance(value, URL):
            url_obj = str(value)
        url = AppriseURL(url_obj, validate=False)
        return {"url": url._url, "tags": tags or url.tags or set("no_logs")}


class AppriseURL:
    _validator = AppriseURLModel

    def __init__(self, url: URL | str, tags: set | None = None, *, validate: bool = True):
        self._actual_url = None
        self._url = str(url)
        if validate:
            self._validate()
        else:
            self.parse_str(url, tags)

    @property
    def tags(self) -> set[str]:
        return self._tags

    @property
    def url(self) -> URL:
        self._validate()
        return self._actual_url

    def parse_str(self, url: URL | str, tags: set | None = None):
        self._tags = tags or set("no_logs")
        self._url = str(url)
        self._actual_url = url if isinstance(url, URL) else None
        parts = self._url.split("://", 1)[0].split("=", 1)
        if len(parts) == 2 and not self._actual_url:
            self._tags = set(parts[0].split(","))
            self._url: str = url.split("=", 1)[-1]

    def _validate(self):
        if not self._actual_url:
            apprise_model = self._validator(url=self._url)
            self._actual_url = apprise_model.url

    def __repr__(self):
        return f"AppriseURL({self._url}, tags={self.tags})"

    def __str__(self):
        return f"{','.join(self.tags)}{'=' if self.tags else ''}{self.url}"


class HttpAppriseURLModel(AppriseURLModel):
    url: SecretHttpURL


class HttpAppriseURL(AppriseURL):
    _validator = HttpAppriseURLModel
