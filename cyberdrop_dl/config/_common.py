from pathlib import Path
from typing import Any

from pydantic import Field as P_Field
from pydantic.fields import _Unset

from cyberdrop_dl.models.base_models import AliasModel


def Field(default: Any, validation_alias: str = _Unset, **kwargs) -> Any:  # noqa: N802
    return P_Field(default=default, validation_alias=validation_alias, **kwargs)


def replace_config_and_resolve(path: Path, current_config: str) -> Path:
    return Path(str(path).replace("{config}", current_config)).resolve()


class PathAliasModel(AliasModel):
    def resolve_paths(self, current_config: str) -> None:
        for name, value in vars(self).items():
            if isinstance(value, Path):
                setattr(self, name, replace_config_and_resolve(value, current_config))
            elif isinstance(value, PathAliasModel):
                value.resolve_paths(current_config)
