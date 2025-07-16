from __future__ import annotations

import json
import re
from typing import Any

_HTTPS_PLACEHOLDER = "<<SAFE_HTTPS>>"
_HTTP_PLACEHOLDER = "<<SAFE_HTTP>>"
_QUOTE_KEYS_REGEX = r"(\w+)\s?:", r'"\1":'  # wrap keys with double quotes
_QUOTE_VALUES_REGEX = r":\s?(?!(\d+|true|false))(\w+)", r':"\2"'  # wrap values with double quotes, skip int or bool
_REPLACE_PAIRS = [
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


def _escape_urls(js_text: str) -> str:
    return js_text.replace("https:", _HTTPS_PLACEHOLDER).replace("http:", _HTTP_PLACEHOLDER)


def _recover_urls(js_text: str) -> str:
    return js_text.replace(_HTTPS_PLACEHOLDER, "https:").replace(_HTTP_PLACEHOLDER, "http:")


def parse_js_vars(js_text: str, use_regex: bool = False) -> dict:
    data = {}
    lines = js_text.split(";")
    for line in lines:
        line = line.strip()
        if not (line and line.startswith("var ")):
            continue
        name_and_value = line.removeprefix("var ")
        name, value = name_and_value.split("=", 1)
        name = name.strip()
        value = value.strip()
        data[name] = value
        if value.startswith("{") or value.startswith("["):
            data[name] = parse_obj(value, use_regex)
    return data


def parse_obj(js_text: str, use_regex: bool = False) -> Any:
    json_str = js_text.replace("\t", "").replace("\n", "").strip()
    json_str = _replace_quotes(json_str)
    if use_regex:
        json_str = _escape_urls(json_str)
        json_str = re.sub(*_QUOTE_KEYS_REGEX, json_str)
        json_str = re.sub(*_QUOTE_VALUES_REGEX, json_str)
        json_str = _recover_urls(json_str)
    result = json.loads(json_str)
    is_dict = isinstance(result, dict)
    if not is_dict:
        result = {"data": result}
    _coerce_dict_values(result)
    if not is_dict:
        return result["data"]
    return result


def _replace_quotes(js_text: str) -> str:
    # We can't just replace every single ' with " because it will brake if the json has english words like: it's

    clean_js_text = js_text
    for old, new in _REPLACE_PAIRS:
        clean_js_text = clean_js_text.replace(old, new)
    return clean_js_text


def _coerce_dict_values(data: dict[str, Any]) -> None:
    for k, v in data.items():
        if isinstance(v, dict):
            continue
        data[k] = _literal_value(v)


def _literal_value(value: list | str | int | None) -> list[Any] | str | int | bool | None:
    if isinstance(value, str):
        value = value.removesuffix("'").removeprefix("'")
        if value.isdigit():
            return int(value)
        if value == "undefined":
            return None
        if value == "true":
            return True
        if value == "false":
            return False
        return value

    if isinstance(value, list):
        return [_literal_value(v) for v in value]
    return value
