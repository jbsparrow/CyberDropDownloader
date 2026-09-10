from __future__ import annotations

import contextlib
import itertools
import logging
import sys
from typing import TYPE_CHECKING, Any, cast

from cyberdrop_dl.constants import MISSING
from cyberdrop_dl.utils._url import parse_http_url as parse_url  # noqa: F401
from cyberdrop_dl.utils._url import remove_trailing_slash  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from contextvars import ContextVar


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def enter_context[T](context_var: ContextVar[T], value: T, /) -> Generator[None]:
    token = context_var.set(value)
    try:
        yield
    finally:
        context_var.reset(token)


def extract_text(text: str, /, start: str, end: str, pos: int | None = None) -> tuple[int, str]:
    """Extracts the text between two strings in a larger text.

    Result will be stripped"""
    start_index = text.index(start, pos) + len(start)
    end_index = text.index(end, start_index)
    return end_index + len(end), text[start_index:end_index].strip()


def extr_text(text: str, /, start: str, end: str) -> str:
    """Extracts the text between two strings in a larger text.

    Result will be stripped"""
    _, txt = extract_text(text, start, end)
    return txt


class TextExtractor:
    def __init__(self, text: str, /, pos: int | None = None) -> None:
        self.text: str = text
        self.cursor: int | None = pos

    def __repr__(self) -> str:
        return f"{type(self).__name__}(text={self.text!r}, cursor={self.cursor!r})"

    def __call__(self, start: str, end: str) -> str:
        self.cursor, txt = extract_text(self.text, start, end, self.cursor)
        return txt

    def repeat(self, start: str, end: str) -> Generator[str]:
        while True:
            try:
                yield self(start, end)
            except ValueError:
                return


def get_system_information() -> dict[str, Any]:
    import platform
    import sqlite3
    import ssl

    def get_common_name() -> str:
        system = platform.system()

        if system == "Linux":
            try:
                return platform.freedesktop_os_release()["PRETTY_NAME"]
            except OSError:
                pass

        if system == "Android" and sys.version_info >= (3, 13):
            ver = platform.android_ver()
            os_name = f"{system} {ver.release}"
            for component in (ver.manufacturer, ver.model, ver.device):
                if component:
                    os_name += f" ({component})"
            return os_name

        default = platform.platform(aliased=True, terse=True).replace("-", " ")
        if system == "Windows" and (edition := platform.win32_edition()):
            return f"{default} {edition}"
        return default

    system_info = (
        {
            "prefix": sys.prefix,
            "executable": sys.executable,
            "GIL enabled": sys._is_gil_enabled() if sys.version_info >= (3, 13) else True,
        }
        | platform.uname()._asdict()
        | {
            "architecture": str(platform.architecture()),
            "python": f"{platform.python_version()} {platform.python_implementation()}",
            "common_name": get_common_name(),
            "sqlite": sqlite3.sqlite_version,
            "openSSL": ssl.OPENSSL_VERSION,
        }
    )
    _ = system_info.pop("node", None)
    return system_info


def is_blob_or_svg(link: str) -> bool:
    return link.startswith(("data:", "blob:", "javascript:"))


def xor_decrypt(encrypted_data: bytes, key: bytes) -> str:
    data = bytearray(b_input ^ b_key for b_input, b_key in zip(encrypted_data, itertools.cycle(key)))
    return data.decode("utf-8", errors="ignore")


def truncated_preview(content: str, max_len: int = 100) -> str:
    if len(content) <= max_len:
        return content
    return f"{content[:max_len]} ... ({len(content) - max_len:,} chars omitted)"


def basic_auth(username: str, password: str) -> str:
    import base64

    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def unique[T](itr: Iterable[T], /, key: Callable[[T], Any] | None = None) -> Generator[T]:
    seen: set[Any] = set()
    for elem in itr:
        lookup = elem if key is None else key(elem)
        if lookup not in seen:
            seen.add(lookup)
            yield elem


def fast_cache[T, R](fn: Callable[[T], R]) -> Callable[[T], R]:
    "Like functools.cache but for single argument function and without all the stats logic"
    cache: dict[T, R] = {}

    def compute(obj: T) -> R:
        val = cache.get(obj, MISSING)
        if val is not MISSING:
            return cast("R", val)

        cache[obj] = val = fn(obj)
        return val

    return compute


def b64_pad(b64_string: str) -> str:
    if pad := len(b64_string) % 4:
        return b64_string + "=" * (4 - pad)
    return b64_string
