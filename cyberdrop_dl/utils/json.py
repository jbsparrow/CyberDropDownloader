from __future__ import annotations

import asyncio
import dataclasses
import datetime
import enum
import functools
import json
import json.decoder
import json.scanner
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, ParamSpec, Protocol, TypeGuard, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    def _scanstring(*args, **kwargs) -> tuple[str, int]: ...

    def _py_make_scanner(*args, **kwargs) -> tuple[Any, int]: ...

    _P = ParamSpec("_P")
    _R = TypeVar("_R")

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


class JSDecoder(json.JSONDecoder):
    def __init__(self):
        """Custom decoder that tries to transforms javascript objects into valid json

        It can only handle simple js objects but that's enough most of the time"""
        super().__init__()
        self.parse_string = _parse_js_string
        self.scan_once = _py_make_scanner(self)


def _verbose_decode_error_msg(func: Callable[_P, _R]) -> Callable[_P, _R]:
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> _R:
        try:
            return func(*args, **kwargs)
        except json.JSONDecodeError as e:
            sub_string = e.doc[e.pos - 10 : e.pos + 10]
            msg = f"{e.msg} at around '{sub_string}', char: '{e.doc[e.pos]}'"
            raise json.JSONDecodeError(msg, e.doc, e.pos) from None

    return wrapper


def _get_encoder(*, sort_keys: bool = False, indent: int | None = None):
    key = sort_keys, indent
    if key not in _encoders:
        _encoders[key] = LenientJSONEncoder(sort_keys=sort_keys, indent=indent)
    return _encoders[key]


def _parse_js_string(*args, **kwargs) -> tuple[Any, int]:
    string, end = _scanstring(*args, **kwargs)
    for quote in ("'", '"'):
        if len(string) > 2 and string.startswith(quote) and string.endswith(quote):
            string = string[1:-1]
    return _literal_value(string), end


def _literal_value(string: str) -> Any:
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


async def dump_jsonl(data: Iterable[dict[str, Any]], /, file: Path, *, append: bool = True) -> None:
    def dump():
        with file.open(mode="a" if append else "w", encoding="utf8") as f:
            for item in data:
                f.writelines(_DEFAULT_ENCODER.iterencode(item))
                f.write("\n")

    await asyncio.to_thread(dump)


loads = _verbose_decode_error_msg(json.loads)
_JS_DECODER = JSDecoder()
_DEFAULT_ENCODER = _get_encoder()


@_verbose_decode_error_msg
def load_js_obj(string: str, /) -> Any:
    """Parses a string representation of a JavaScript object into a Python object.

    It can handle JavaScript object strings that may not be valid JSON"""

    string = string.replace("\t", "").replace("\n", "").strip()
    # Remove tailing comma
    string = string[:-1].strip().removesuffix(",") + string[-1]
    # Make it valid json by replacing single quotes with double quotes
    # we can't just replace every single ' with " because it will brake with english words like: it's
    for old, new in _REPLACE_QUOTES_PAIRS:
        string = string.replace(old, new)
    string = re.sub(r"\s\b(?!http)(\w+)\s?:", r' "\1" : ', string)  # wrap keys without quotes with double quotes
    return _JS_DECODER.decode(string)
