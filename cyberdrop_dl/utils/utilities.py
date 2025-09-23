from __future__ import annotations

import contextlib
import dataclasses
import inspect
import itertools
import json
import os
import platform
import re
import sys
import unicodedata
from collections.abc import Mapping
from functools import lru_cache, partial, wraps
from pathlib import Path
from stat import S_ISREG
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Concatenate,
    ParamSpec,
    Protocol,
    SupportsInt,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)

from aiohttp import ClientConnectorError
from pydantic import ValidationError
from yarl import URL

from cyberdrop_dl import constants
from cyberdrop_dl.data_structures import AbsoluteHttpURL
from cyberdrop_dl.exceptions import (
    CDLBaseError,
    ErrorLogMessage,
    InvalidExtensionError,
    InvalidURLError,
    NoExtensionError,
    TooManyCrawlerErrors,
    create_error_msg,
    get_origin,
)
from cyberdrop_dl.utils.logger import log, log_with_color

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator, Iterable, Mapping

    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, AnyURL, MediaItem, ScrapeItem
    from cyberdrop_dl.downloader.downloader import Downloader
    from cyberdrop_dl.managers.manager import Manager

    CrawerOrDownloader = TypeVar("CrawerOrDownloader", bound=Crawler | Downloader)
    Origin = TypeVar("Origin", bound=ScrapeItem | MediaItem | URL)

    _P = ParamSpec("_P")
    _T = TypeVar("_T")
    _R = TypeVar("_R")

    class Dataclass(Protocol):
        __dataclass_fields__: ClassVar[dict]


_ALLOWED_FILEPATH_PUNCTUATION = " .-_!#$%'()+,;=@[]^{}~"
_BLOB_OR_SVG = ("data:", "blob:", "javascript:")


@contextlib.contextmanager
def error_handling_context(self: Crawler | Downloader, item: ScrapeItem | MediaItem | URL) -> Generator[None]:
    link: URL = item if isinstance(item, URL) else item.url
    error_log_msg = origin = exc_info = None
    link_to_show: URL | str = ""
    is_segment: bool = getattr(item, "is_segment", False)
    is_downloader: bool = bool(getattr(self, "log_prefix", False))
    try:
        yield
    except TooManyCrawlerErrors:
        return
    except CDLBaseError as e:
        error_log_msg = ErrorLogMessage(e.ui_failure, str(e))
        origin = e.origin
        link_to_show: URL | str = getattr(e, "url", None) or link_to_show
    except NotImplementedError as e:
        error_log_msg = ErrorLogMessage("NotImplemented")
        exc_info = e
    except TimeoutError as e:
        error_log_msg = ErrorLogMessage("Timeout", repr(e))
    except ClientConnectorError as e:
        ui_failure = "Client Connector Error"
        suffix = "" if (link.host or "").startswith(e.host) else f" from {link}"
        log_msg = f"{e}{suffix}. If you're using a VPN, try turning it off"
        error_log_msg = ErrorLogMessage(ui_failure, log_msg)
    except ValidationError as e:
        exc_info = e
        ui_failure = create_error_msg(422)
        log_msg = str(e).partition("For further information")[0].strip()
        error_log_msg = ErrorLogMessage(ui_failure, log_msg)
    except Exception as e:
        exc_info = e
        error_log_msg = ErrorLogMessage.from_unknown_exc(e)

    if error_log_msg is None or is_segment:
        return

    link_to_show = link_to_show or link
    origin = origin or get_origin(item)
    if is_downloader:
        self, item = cast("Downloader", self), cast("MediaItem", item)
        self.write_download_error(item, error_log_msg, exc_info)
        return

    log(f"Scrape Failed: {link_to_show} ({error_log_msg.main_log_msg})", 40, exc_info=exc_info)
    self.manager.log_manager.write_scrape_error_log(link_to_show, error_log_msg.csv_log_msg, origin)
    self.manager.progress_manager.scrape_stats_progress.add_failure(error_log_msg.ui_failure)


@overload
def error_handling_wrapper(
    func: Callable[Concatenate[CrawerOrDownloader, Origin, _P], _R],
) -> Callable[Concatenate[CrawerOrDownloader, Origin, _P], _R]: ...


@overload
def error_handling_wrapper(
    func: Callable[Concatenate[CrawerOrDownloader, Origin, _P], Coroutine[None, None, _R]],
) -> Callable[Concatenate[CrawerOrDownloader, Origin, _P], Coroutine[None, None, _R]]: ...


def error_handling_wrapper(
    func: Callable[Concatenate[CrawerOrDownloader, Origin, _P], _R | Coroutine[None, None, _R]],
) -> Callable[Concatenate[CrawerOrDownloader, Origin, _P], _R | Coroutine[None, None, _R]]:
    """Wrapper handles errors for url scraping."""

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(self: CrawerOrDownloader, item: Origin, *args: _P.args, **kwargs: _P.kwargs) -> _R:
            with error_handling_context(self, item):
                return await func(self, item, *args, **kwargs)

        return async_wrapper

    @wraps(func)
    def wrapper(self: CrawerOrDownloader, item: Origin, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        with error_handling_context(self, item):
            result = func(self, item, *args, **kwargs)
            assert not inspect.isawaitable(result)
            return result

    return wrapper


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def sanitize_unicode_emojis_and_symbols(title: str) -> str:
    """Allow all Unicode letters/numbers/marks, plus safe filename punctuation, but not symbols or emoji."""
    return "".join(
        c for c in title if (c in _ALLOWED_FILEPATH_PUNCTUATION or unicodedata.category(c)[0] in {"L", "N", "M"})
    ).strip()


def sanitize_filename(name: str, sub: str = "") -> str:
    """Simple sanitization to remove illegal characters from filename."""
    clean_name = re.sub(constants.SANITIZE_FILENAME_PATTERN, sub, name)
    if platform.system() in ("Windows", "Darwin"):
        return sanitize_unicode_emojis_and_symbols(clean_name)
    return clean_name


def sanitize_folder(title: str) -> str:
    """Simple sanitization to remove illegal characters from titles and trim the length to be less than 60 chars."""

    title = title.replace("\n", "").strip()
    title = title.replace("\t", "").strip()
    title = re.sub(" +", " ", title)
    title = sanitize_filename(title, "-")
    title = re.sub(r"\.{2,}", ".", title)
    title = title.rstrip(".").strip()

    if all(char in title for char in ("(", ")")):
        new_title, domain_part = title.rsplit("(", 1)
        new_title = truncate_str(new_title, constants.MAX_NAME_LENGTHS["FOLDER"])
        return f"{new_title} ({domain_part.strip()}"
    return truncate_str(title, constants.MAX_NAME_LENGTHS["FOLDER"])


def truncate_str(text: str, max_length: int = 0) -> str:
    """Truncates and strip strings to the desired len.

    If `max_length` is 0, uses `constants.MAX_NAME_LENGTHS["FILE"]`"""
    truncate_to = max_length or constants.MAX_NAME_LENGTHS["FILE"]
    if len(text) > truncate_to:
        return text[:truncate_to].strip()
    return text.strip()


def get_filename_and_ext(filename: str, forum: bool = False) -> tuple[str, str]:
    """Returns the filename and extension of a given file, throws `NoExtensionError` if there is no extension."""
    clean_filename = Path(filename).as_posix().replace("/", "-")  # remove OS separators
    filename_as_path = Path(clean_filename)
    if not filename_as_path.suffix:
        raise NoExtensionError
    ext_no_dot = filename_as_path.suffix.split(".")[1]
    if ext_no_dot.isdigit() and forum and "-" in filename:
        name, ext = filename_as_path.name.rsplit("-", 1)
        ext = ext.rsplit(".")[0]
        ext_w_dot = f".{ext}".lower()
        if ext_w_dot not in constants.MEDIA_EXTENSIONS:
            raise InvalidExtensionError
        filename_as_path = Path(f"{name}.{ext}")
    if len(filename_as_path.suffix) > 5:
        raise InvalidExtensionError

    filename_as_path = filename_as_path.with_suffix(filename_as_path.suffix.lower())
    filename_as_str = truncate_str(filename_as_path.stem.removesuffix(".")) + filename_as_path.suffix
    filename_as_path = Path(sanitize_filename(filename_as_str))
    filename_as_path = Path(filename_as_path.stem.strip() + filename_as_path.suffix)
    return filename_as_path.name, filename_as_path.suffix


def get_download_path(manager: Manager, scrape_item: ScrapeItem, domain: str) -> Path:
    """Returns the path to the download folder."""
    download_dir = manager.path_manager.download_folder

    if scrape_item.retry:
        return scrape_item.retry_path  # type: ignore
    if scrape_item.parent_title and scrape_item.part_of_album:
        return download_dir / scrape_item.parent_title
    if scrape_item.parent_title:
        return download_dir / scrape_item.parent_title / f"Loose Files ({domain})"
    return download_dir / f"Loose Files ({domain})"


def remove_file_id(manager: Manager, filename: str, ext: str) -> tuple[str, str]:
    """Removes the additional string some websites adds to the end of every filename."""
    original_filename = filename
    if not manager.config_manager.settings_data.download_options.remove_generated_id_from_filenames:
        return original_filename, filename

    filename = filename.rsplit(ext, 1)[0]
    filename = filename.rsplit("-", 1)[0]
    tail_no_dot = filename.rsplit("-", 1)[-1]
    ext_no_dot = ext.rsplit(".", 1)[-1]
    tail = f".{tail_no_dot}"
    if re.match(constants.RAR_MULTIPART_PATTERN, tail_no_dot) and ext == ".rar" and "-" in filename:
        filename, part = filename.rsplit("-", 1)
        filename = f"{filename}.{part}"
    elif ext_no_dot.isdigit() and tail in constants.FILE_FORMATS["7z"] and "-" in filename:
        filename, _7z_ext = filename.rsplit("-", 1)
        filename = f"{filename}.{_7z_ext}"
    if not filename.endswith(ext):
        filename = filename + ext
    return original_filename, filename


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def clear_term():
    os.system("cls" if os.name == "nt" else "clear")


def get_size(path: os.DirEntry) -> int | None:
    try:
        return path.stat(follow_symlinks=False).st_size
    except (OSError, ValueError):
        return


def purge_dir_tree(dirname: Path | str) -> bool:
    """walks and removes in place"""

    has_non_empty_files = False
    has_non_empty_subfolders = False

    try:
        for entry in os.scandir(dirname):
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir:
                deleted = purge_dir_tree(entry.path)
                if not deleted:
                    has_non_empty_subfolders = True
            elif get_size(entry) == 0:
                os.unlink(entry)  # noqa: PTH108
            else:
                has_non_empty_files = True

    except (OSError, PermissionError):
        pass

    if has_non_empty_files or has_non_empty_subfolders:
        return False
    try:
        os.rmdir(dirname)  # noqa: PTH106
        return True
    except OSError:
        return False


def check_partials_and_empty_folders(manager: Manager):
    """Checks for partial downloads, deletes partial files and empty folders."""
    settings = manager.config_manager.settings_data.runtime_options
    if settings.delete_partial_files:
        delete_partial_files(manager)
    if not settings.skip_check_for_partial_files:
        check_for_partial_files(manager)
    if not settings.skip_check_for_empty_folders:
        delete_empty_folders(manager)


def delete_partial_files(manager: Manager):
    """Deletes partial download files recursively."""
    log_red("Deleting partial downloads...")
    for file in manager.path_manager.download_folder.rglob("*.part"):
        file.unlink(missing_ok=True)


def check_for_partial_files(manager: Manager):
    """Checks if there are partial downloads in any subdirectory and logs if found."""
    log_yellow("Checking for partial downloads...")
    if next(manager.path_manager.download_folder.rglob("*.part"), None) is not None:
        log_yellow("There are partial downloads in the downloads folder")


def delete_empty_folders(manager: Manager):
    """Deletes empty folders efficiently."""
    log_yellow("Checking for empty folders...")
    purge_dir_tree(manager.path_manager.download_folder)

    sorted_folder = manager.path_manager.sorted_folder
    if sorted_folder and manager.config_manager.settings_data.sorting.sort_downloads:
        purge_dir_tree(sorted_folder)


def get_valid_dict(dataclass: Dataclass | type[Dataclass], info: Mapping[str, Any]) -> dict[str, Any]:
    """Remove all keys that are not fields in the dataclass"""
    fields_names = [f.name for f in dataclasses.fields(dataclass)]
    return {name: info[name] for name in fields_names if name in info}


def get_text_between(original_text: str, start: str, end: str) -> str:
    """Extracts the text between two strings in a larger text. Result will be stripped"""
    start_index = original_text.index(start) + len(start)
    end_index = original_text.index(end, start_index)
    return original_text[start_index:end_index].strip()


def parse_url(link_str: str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool = True) -> AbsoluteHttpURL:
    """Parse a string into an absolute URL, handling relative URLs, encoding and optionally removes trailing slash (trimming).
    Raises:
        InvalidURLError: If the input string is not a valid URL or if any other error occurs during parsing.
        TypeError: If `relative_to` is `None` and the parsed URL is relative or has no scheme.
    """

    base: AbsoluteHttpURL = relative_to  # type: ignore

    def fix_query_params_encoding(link: str) -> str:
        if "?" not in link:
            return link
        parts, query_and_frag = link.split("?", 1)
        query_and_frag = query_and_frag.replace("+", "%20")
        return f"{parts}?{query_and_frag}"

    def fix_multiple_slashes(link_str: str) -> str:
        return re.sub(r"(?:https?)?:?(\/{3,})", "//", link_str)

    try:
        assert link_str, "link_str is empty"
        assert isinstance(link_str, str), f"link_str must be a string object, got: {link_str!r}"
        clean_link_str = fix_multiple_slashes(fix_query_params_encoding(link_str))
        is_encoded = "%" in clean_link_str
        new_url = URL(clean_link_str, encoded=is_encoded)

    except (AssertionError, AttributeError, ValueError, TypeError) as e:
        raise InvalidURLError(str(e), url=link_str) from e

    if not new_url.absolute:
        new_url = base.join(new_url)
    if not new_url.scheme:
        new_url = new_url.with_scheme(base.scheme or "https")
    assert is_absolute_http_url(new_url)
    if not trim:
        return new_url
    return remove_trailing_slash(new_url)


def is_absolute_http_url(url: URL) -> TypeGuard[AbsoluteHttpURL]:
    return url.absolute and url.scheme.startswith("http")


def remove_trailing_slash(url: AnyURL) -> AnyURL:
    if url.name or url.path == "/":
        return url
    return url.parent.with_fragment(url.fragment).with_query(url.query)


def remove_parts(
    url: AbsoluteHttpURL, *parts_to_remove: str, keep_query: bool = True, keep_fragment: bool = True
) -> AbsoluteHttpURL:
    if not parts_to_remove:
        return url
    new_parts = [p for p in url.parts[1:] if p not in parts_to_remove]
    return url.with_path("/".join(new_parts), keep_fragment=keep_fragment, keep_query=keep_query)


def get_size_or_none(path: Path) -> int | None:
    """Checks if this is a file and returns its size with a single system call.

    Returns `None` otherwise"""

    try:
        stat = path.stat()
        if S_ISREG(stat.st_mode):
            return stat.st_size
    except (OSError, ValueError):
        return None


class HasClose(Protocol):
    def close(self): ...


class HasAsyncClose(Protocol):
    async def close(self): ...


C = TypeVar("C", bound=HasAsyncClose | HasClose)


async def close_if_defined(obj: C) -> C:
    if not isinstance(obj, dataclasses.Field):
        await obj.close() if inspect.iscoroutinefunction(obj.close) else obj.close()
    return constants.NOT_DEFINED


@lru_cache
def get_system_information() -> str:
    def get_common_name() -> str:
        system = platform.system()

        if system in ("Linux",):
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

    system_info = platform.uname()._asdict() | {
        "architecture": str(platform.architecture()),
        "python": f"{platform.python_version()} {platform.python_implementation()}",
        "common_name": get_common_name(),
    }
    _ = system_info.pop("node", None)
    return json.dumps(system_info, indent=4)


def is_blob_or_svg(link: str) -> bool:
    return any(link.startswith(x) for x in _BLOB_OR_SVG)


def unique(iterable: Iterable[_T], *, hashable: bool = True) -> Iterable[_T]:
    """Yields unique values from iterable, keeping original order"""
    if hashable:
        seen: set[_T] | list[_T] = set()
        add: Callable[[_T], None] = seen.add
    else:
        seen = []
        add = seen.append

    for value in iterable:
        if value not in seen:
            add(value)
            yield value


def get_valid_kwargs(
    func: Callable[..., Any], kwargs: Mapping[str, _T], accept_kwargs: bool = True
) -> Mapping[str, _T]:
    """Get the subset of ``kwargs`` that are valid params for ``func`` and their values are not `None`

    If func takes **kwargs, returns everything"""
    params = inspect.signature(func).parameters
    if accept_kwargs and any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs

    return {k: v for k, v in kwargs.items() if k in params.keys() and v is not None}


def call_w_valid_kwargs(cls: Callable[..., _R], kwargs: Mapping[str, Any]) -> _R:
    return cls(**get_valid_kwargs(cls, kwargs))


def type_adapter(func: Callable[..., _R], aliases: dict[str, str] | None = None) -> Callable[[dict[str, Any]], _R]:
    """Like `pydantic.TypeAdapter`, but without type validation of attributes (faster)

    Ignores attributes with `None` as value"""
    param_names = inspect.signature(func).parameters.keys()

    def call(kwargs: dict[str, Any]):
        if aliases:
            for original, alias in aliases.items():
                if original not in kwargs:
                    kwargs[original] = kwargs.get(alias)

        return func(**{name: value for name in param_names if (value := kwargs.get(name)) is not None})

    return call


def xor_decrypt(encrypted_data: bytes, key: bytes) -> str:
    data = bytearray(b_input ^ b_key for b_input, b_key in zip(encrypted_data, itertools.cycle(key)))
    return data.decode("utf-8", errors="ignore")


log_cyan = partial(log_with_color, style="cyan", level=20)
log_yellow = partial(log_with_color, style="yellow", level=20)
log_green = partial(log_with_color, style="green", level=20)
log_red = partial(log_with_color, style="red", level=20)


def filter_query(
    query: Mapping[str, str | SupportsInt | float],
    *keep: str | tuple[str, str | SupportsInt | float],
) -> dict[str, str | SupportsInt | float]:
    """Returns a dictionary with only the `keep` keys.

     Each `keep` argument can be either:
    - A string: The key will be kept only if was present in `query`
    - A tuple `(key, default_value)`: If `key` is not found in `query`, it will be added with `default_value`.
    """

    defaults: dict[str, str | SupportsInt | float] = {}
    keys: set[str] = set()
    for key in keep:
        if isinstance(key, str):
            keys.add(key)
            continue
        name, default = key
        defaults[name] = default
        keys.add(name)

    def get_key(key: str):
        if key in query:
            return query[key]
        return defaults.get(key)

    return {k: value for k in sorted(keys) if (value := get_key(k)) is not None}


def keep_query_params(url: AbsoluteHttpURL, *keep: str | tuple[str, str | SupportsInt | float]) -> AbsoluteHttpURL:
    """Returns a new URL with only the `keep` keys as query params.

    Each `keep` argument can be either:
    - A string: The key will be kept only if was present in `url.query`
    - A tuple `(key, default_value)`: If `key` is not found in `url.query`, it will be added with `default_value`.
    """
    return url.with_query(filter_query(url.query, *keep))
