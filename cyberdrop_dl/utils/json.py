from __future__ import annotations

import asyncio
import dataclasses
import datetime
import enum
import json
import json.decoder
import json.scanner
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager

    def _scanstring(*args, **kwargs) -> tuple[str, int]: ...

    def _py_make_scanner(*args, **kwargs) -> tuple[Any, int]: ...

else:
    _scanstring = json.decoder.scanstring
    _py_make_scanner = json.scanner.py_make_scanner

_encoders: dict[tuple[bool, int | None], LenientJSONEncoder] = {}
_REPLACE_QUOTES_PAIRS = [
    ("{'", '{"'),
    ("'}", '"}'),
    ("['", '["'),
    ("']", '"]'),
    (",'", ',"'),
    ("':", '":'),
    (", '", ', "'),
    ("' :", '" :'),
    ("',", '",'),
    (": '", ': "'),
]


class _DataclassInstance(Protocol):
    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]


class LenientJSONEncoder(json.JSONEncoder):
    def __init__(self, *, sort_keys: bool = False, indent: int | None = None) -> None:
        """Custom encoder that can handle:

        - dataclasses
        - namedtuples
        - enums
        - date & datetime
        - sets
        - subclasses of dict

        Any incompatible object will be serialized as str, except types."""
        super().__init__(check_circular=False, ensure_ascii=False, sort_keys=sort_keys, indent=indent)

    def default(self, o: object) -> Any:
        if isinstance(o, datetime.date):
            return o.isoformat()
        if isinstance(o, enum.Enum):
            return self.default(o.value)
        if isinstance(o, set):
            return sorted(o)
        if _is_namedtuple_instance(o):
            return o._asdict()
        if _is_dataclass_instance(o):
            return dataclasses.asdict(o)
        if isinstance(o, dict):  # Handle subclasses of dict
            return dict(o)
        if isinstance(o, type):  # Do not serialize classes, only instances
            return super().default(o)
        return str(o)


class _JSDecoder(json.JSONDecoder):
    def __init__(self):
        """Custom decoder that tries to transforms javascript objects into valid json

        It can only handle simple cases but that's enough most of the time"""
        super().__init__()
        self.parse_string = _parse_js_string
        self.scan_once = _py_make_scanner(self)

    def parse_js_obj(self, js_text: str, /) -> Any:
        """Get a python object from a string representation of a javascript object"""

        # Make it valid json by replacing single quotes with double quotes
        # we can't just replace every single ' with " because it will brake with english words like: it's
        string = js_text.replace("\t", "").replace("\n", "").strip()
        for old, new in _REPLACE_QUOTES_PAIRS:
            string = string.replace(old, new)
        return self.decode(string)


def _get_encoder(*, sort_keys: bool = False, indent: int | None = None):
    key = sort_keys, indent
    if key not in _encoders:
        _encoders[key] = LenientJSONEncoder(sort_keys=sort_keys, indent=indent)
    return _encoders[key]


def _parse_js_string(*args, **kwargs) -> tuple[Any, int]:
    string, end = _scanstring(*args, **kwargs)
    return _literal_value(string), end


def _literal_value(string: str) -> Any:
    string = string.removesuffix("'").removeprefix("'")
    if string.isdigit():
        return int(string)
    if string == "undefined":
        return None
    if string in ("true", "!0"):
        return True
    if string in ("false", "!1"):
        return False
    return string


def _is_namedtuple_instance(obj: object, /) -> TypeGuard[NamedTuple]:
    return isinstance(obj, tuple) and hasattr(obj, "_asdict") and hasattr(obj, "_fields")


def _is_dataclass_instance(obj: object, /) -> TypeGuard[_DataclassInstance]:
    return dataclasses.is_dataclass(obj) and not isinstance(obj, type)


def dumps(obj: object, /, *, sort_keys: bool = False, indent: int | None = None) -> Any:
    encoder = _get_encoder(sort_keys=sort_keys, indent=indent)
    return encoder.encode(obj)


def dump_jsonl(data: Iterable[dict[str, Any]], /, file: Path, *, append: bool = False) -> None:
    with file.open(mode="a" if append else "w", encoding="utf8") as f:
        for item in data:
            f.writelines(_get_encoder().iterencode(item))
            f.write("\n")


async def dump_items(manager: Manager) -> None:
    jsonl_file = manager.path_manager.main_log.with_suffix(".results.jsonl")

    def media_items_as_dict() -> Iterable[dict[str, Any]]:
        for item in manager.path_manager.prev_downloads:
            yield item.jsonable_dict()
        for item in manager.path_manager.completed_downloads:
            yield item.jsonable_dict()

    return await asyncio.to_thread(dump_jsonl, media_items_as_dict(), jsonl_file)


loads = json.loads
parse_js_obj = _JSDecoder().parse_js_obj
