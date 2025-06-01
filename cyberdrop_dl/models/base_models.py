"""Pydantic models"""

from collections.abc import Mapping
from pathlib import Path

import yarl
from pydantic import AnyUrl, BaseModel, ConfigDict, Secret, SerializationInfo, model_serializer, model_validator

from cyberdrop_dl.models.types import HttpURL
from cyberdrop_dl.models.validators import to_apprise_url_dict


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
    def parse_input(value: yarl.URL | dict | str) -> Mapping:
        return to_apprise_url_dict(value)


class HttpAppriseURL(AppriseURLModel):
    url: Secret[HttpURL]


class PathAliasModel(AliasModel):
    @staticmethod
    def replace_config_and_resolve(path: Path, current_config: str) -> Path:
        return Path(str(path).replace("{config}", current_config)).resolve()

    def resolve_paths(self, config_name: str) -> None:
        for name, value in vars(self).items():
            if isinstance(value, Path):
                setattr(self, name, self.replace_config_and_resolve(value, config_name))
            elif isinstance(value, PathAliasModel):
                value.resolve_paths(config_name)
