from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from enum import Enum
from pathlib import Path, PurePath

import yaml
from pydantic import BaseModel, ValidationError
from yaml.error import YAMLError
from yarl import URL

from cyberdrop_dl.clients.errors import InvalidYamlError
from cyberdrop_dl.utils.constants import VALIDATION_ERROR_FOOTER


class TimedeltaSerializer(BaseModel):
    duration: timedelta


def _save_as_str(dumper: yaml.Dumper, value):
    if isinstance(value, Enum):
        return dumper.represent_str(value.name)
    return dumper.represent_str(str(value))


def _save_date(dumper: yaml.Dumper, value: date):
    return dumper.represent_str(value.isoformat())


def _save_timedelta(dumper: yaml.Dumper, value: timedelta):
    timespan = TimedeltaSerializer(duration=value).model_dump(mode="json")
    return dumper.represent_str(timespan["duration"])


yaml.add_multi_representer(PurePath, _save_as_str)
yaml.add_multi_representer(Enum, _save_as_str)
yaml.add_multi_representer(date, _save_date)
yaml.add_representer(timedelta, _save_timedelta)
yaml.add_representer(URL, _save_as_str)


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
    except YAMLError as e:
        raise InvalidYamlError(file, e) from None


def handle_validation_error(e: ValidationError, *, title: str | None = None, sources: dict[str, Path] | None = None):
    startup_logger = logging.getLogger("cyberdrop_dl_startup")
    error_count = e.error_count()
    source = sources.get(e.title) if sources else None
    title = title or e.title
    source = f"from {source.resolve()}" if source else ""
    msg = f"Found {error_count} error{'s' if error_count>1 else ''} parsing {title} {source}"
    startup_logger.error(msg)
    for error in e.errors(include_url=False):
        loc = ".".join(map(str, error["loc"]))
        if title == "CLI arguments":
            loc = error["loc"][-1]
            if isinstance(error["loc"][-1], int):
                loc = ".".join(map(str, error["loc"][-2:]))
            loc = f"--{loc}"
        msg = f"Value of '{loc}' is invalid:\n"
        msg += f"  {error['msg']} (input_value='{error['input']}', input_type='{error['type']}')\n"
        startup_logger.error(msg)
    startup_logger.error(VALIDATION_ERROR_FOOTER)
    sys.exit(1)
