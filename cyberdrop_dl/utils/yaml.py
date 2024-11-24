from __future__ import annotations

from enum import IntEnum, StrEnum
from pathlib import Path, PurePath

import yaml
from pydantic import BaseModel, ValidationError
from yarl import URL

from cyberdrop_dl.clients.errors import InvalidYamlError
from cyberdrop_dl.utils.logger import print_to_console


def _save_as_str(dumper: yaml.Dumper, value):
    return dumper.represent_str(str(value))


yaml.add_multi_representer(PurePath, _save_as_str)
yaml.add_multi_representer(StrEnum, _save_as_str)
yaml.add_multi_representer(IntEnum, int)
yaml.add_representer(URL, _save_as_str)

VALIDATION_ERROR_FOOTER = """
Read the documentation for guidance on how to resolve this error: https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options
Please note, this is not a bug. Do not open issues related to this"""


def save(file: Path, data: BaseModel | dict) -> None:
    """Saves a dict to a yaml file."""
    if isinstance(data, BaseModel):
        data = data.model_dump()
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf8") as yaml_file:
        yaml.dump(data, yaml_file)


def load(file: Path, *, create: bool = False) -> dict:
    """Loads a yaml file and returns it as a dict."""
    if create:
        file.parent.mkdir(parents=True, exist_ok=True)
        if not file.is_file():
            file.touch()
    try:
        with file.open(encoding="utf8") as yaml_file:
            yaml_values = yaml.safe_load(yaml_file.read())
            return yaml_values if yaml_values else {}
    except yaml.constructor.ConstructorError as e:
        raise InvalidYamlError(file, e) from None


def handle_validation_error(e: ValidationError, sources: dict | None = None):
    error_count = e.error_count()
    source: Path = sources.get(e.title, None) if sources else None
    source = f"from {source.resolve()}" if source else ""
    msg = f"found {error_count} error{'s' if error_count>1 else ''} parsing {e.title} {source}"
    print_to_console(msg, error=True)
    for error in e.errors(include_url=False):
        msg = f"\nValue of '{'.'.join(error['loc'])}' is invalid:"
        print_to_console(msg, markup=False)
        print_to_console(f"  {error['msg']} (input_value='{error['input']}')", style="bold red")
    print_to_console(VALIDATION_ERROR_FOOTER)
