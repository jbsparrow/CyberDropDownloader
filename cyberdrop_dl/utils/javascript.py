from __future__ import annotations

import json
import re
from typing import Any

HTTPS_PLACEHOLDER = "<<SAFE_HTTPS>>"
HTTP_PLACEHOLDER = "<<SAFE_HTTP>>"
QUOTE_KEYS_REGEX = r"(\w+)\s?:", r'"\1":'  # wrap keys with double quotes
QUOTE_VALUES_REGEX = r":\s?(?!(\d+|true|false))(\w+)", r':"\2"'  # wrap values with double quotes, skip int or bool


def scape_urls(js_text: str) -> str:
    return js_text.replace("https:", HTTPS_PLACEHOLDER).replace("http:", HTTP_PLACEHOLDER)


def recover_urls(js_text: str) -> str:
    return js_text.replace(HTTPS_PLACEHOLDER, "https:").replace(HTTP_PLACEHOLDER, "http:")


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
            data[name] = parse_json_to_dict(value, use_regex)
    return data


def parse_json_to_dict(js_text: str, use_regex: bool = False) -> Any:
    json_str = js_text.replace("\t", "").replace("\n", "").strip()
    json_str = replace_quotes(json_str)
    if use_regex:
        json_str = scape_urls(json_str)
        json_str = re.sub(*QUOTE_KEYS_REGEX, json_str)
        json_str = re.sub(*QUOTE_VALUES_REGEX, json_str)
        json_str = recover_urls(json_str)
    result = json.loads(json_str)
    is_list = isinstance(result, list)
    if is_list:
        result = {"data": result}
    clean_dict(result)
    if is_list:
        return result["data"]
    return result


def replace_quotes(js_text: str) -> str:
    # We can't just replace every single ' with " because it will brake if the json has english words like: it's

    replace_pairs = [
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
    clean_js_text = js_text
    for old, new in replace_pairs:
        clean_js_text = clean_js_text.replace(old, new)
    return clean_js_text


def is_valid_key(key: str) -> bool:
    return not any(p in key for p in ("@", "m3u8"))


def clean_dict(data: dict, *keys_to_clean) -> None:
    """Modifies dict in place"""

    for key in keys_to_clean:
        inner_dict = data.get(key)
        if inner_dict and isinstance(inner_dict, dict):
            data[key] = {k: v for k, v in inner_dict.items() if is_valid_key(k)}

    for k, v in data.items():
        if isinstance(v, dict):
            continue
        data[k] = clean_value(v)


def clean_value(value: list | str | int) -> list | str | int | None:
    if isinstance(value, str):
        value = value.removesuffix("'").removeprefix("'")
        if value.isdigit():
            return int(value)
        return value

    if isinstance(value, list):
        return [clean_value(v) for v in value]
    return value
