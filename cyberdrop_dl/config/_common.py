from pathlib import Path
from typing import Any, Self

from pydantic import Field as P_Field
from pydantic.fields import _Unset

from cyberdrop_dl.exceptions import InvalidYamlError
from cyberdrop_dl.models import PathAliasModel, get_model_fields
from cyberdrop_dl.utils import yaml


def Field(default: Any, validation_alias: str = _Unset, **kwargs) -> Any:  # noqa: N802
    return P_Field(default=default, validation_alias=validation_alias, **kwargs)


class ConfigModel(PathAliasModel):
    @classmethod
    def load_file(cls, file: Path, update_if_has_string: str) -> Self:
        default = cls()
        if not file.is_file():
            config = default
            needs_update = True

        else:
            all_fields = get_model_fields(default, exclude_unset=False)
            config = cls.model_validate(yaml.load(file))
            set_fields = get_model_fields(config)
            needs_update = all_fields != set_fields or _is_in_file(update_if_has_string, file)

        if needs_update:
            yaml.save(file, config)
        return config

    def save_to_file(self, file: Path) -> None:
        yaml.save(file, self)


def _is_in_file(search_value: str, file: Path) -> bool:
    try:
        return search_value.casefold() in file.read_text().casefold()
    except FileNotFoundError:
        return False
    except Exception as e:
        raise InvalidYamlError(file, e) from e
