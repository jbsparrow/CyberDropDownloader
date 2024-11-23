from typing import Annotated

from pydantic import AfterValidator, AnyUrl, BaseModel, ByteSize, ConfigDict, HttpUrl, Secret, StringConstraints
from yarl import URL


def convert_to_yarl(value: AnyUrl) -> URL:
    return URL(value)


def human_readable(value: ByteSize) -> str:
    return value.human_readable(decimal=True)


HttpURL = Annotated[HttpUrl, AfterValidator(convert_to_yarl)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
AnyURL = Annotated[AnyUrl, AfterValidator(convert_to_yarl)]
SecretAnyUrl = Secret[AnyURL]


class AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AppriseURL(BaseModel):
    url: SecretAnyUrl
    tags: set[NonEmptyStr]

    def __init__(self, url: URL | str):
        actual_url = str(url)
        tags = set()
        if not isinstance(url, URL):
            parts = url.split("://", 1)[0].split("=", 1)
            if len(parts) == 2:
                tags = set(parts[0].split(","))
            actual_url = parts[-1]
        super().__init__(tags=tags, url=actual_url)
