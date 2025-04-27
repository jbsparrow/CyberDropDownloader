from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, fields
from functools import lru_cache, partial, wraps
from pathlib import Path
from stat import S_ISREG
from typing import TYPE_CHECKING, Any, ClassVar, ParamSpec, Protocol, TypeVar

import aiofiles
import rich
from aiohttp import ClientConnectorError, ClientSession, FormData
from aiohttp_client_cache.response import AnyResponse
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import (
    CDLBaseError,
    ErrorLogMessage,
    InvalidExtensionError,
    InvalidURLError,
    NoExtensionError,
    get_origin,
)
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer, log_with_color

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping

    from curl_cffi.requests.models import Response as CurlResponse
    from rich.text import Text

    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.downloader.downloader import Downloader
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem, ScrapeItem


P = ParamSpec("P")
R = TypeVar("R")


TEXT_EDITORS = "micro", "nano", "vim"  # Ordered by preference
FILENAME_REGEX = re.compile(r"filename\*=UTF-8''(.+)|.*filename=\"(.*?)\"", re.IGNORECASE)
subprocess_get_text = partial(subprocess.run, capture_output=True, text=True, check=False)


class Dataclass(Protocol):
    __dataclass_fields__: ClassVar[dict]


@dataclass(frozen=True, slots=True)
class OGProperties:
    """Open Graph properties.  Each attribute corresponds to an OG property."""

    title: str = ""
    description: str = ""
    image: str = ""
    url: str = ""
    type: str = ""
    site_name: str = ""
    locale: str = ""
    determiner: str = ""
    audio: str = ""
    video: str = ""


def error_handling_wrapper(
    func: Callable[..., Coroutine[None, None, R]],
) -> Callable[..., Coroutine[None, None, R | None]]:
    """Wrapper handles errors for url scraping."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R | None:
        self: Crawler | Downloader = args[0]
        item: ScrapeItem | MediaItem | URL = args[1]
        link: URL = item if isinstance(item, URL) else item.url
        origin = exc_info = None
        link_to_show: URL | str = ""
        try:
            return await func(*args, **kwargs)
        except CDLBaseError as e:
            error_log_msg = ErrorLogMessage(e.ui_failure, str(e))
            origin = e.origin
            e_url: URL | str | None = getattr(e, "url", None)
            link_to_show = e_url or link_to_show
        except NotImplementedError:
            error_log_msg = ErrorLogMessage("NotImplemented")
        except TimeoutError:
            error_log_msg = ErrorLogMessage("Timeout")
        except ClientConnectorError as e:
            ui_failure = "Client Connector Error"
            # link_to_show = link.with_host(e.host) # For bunkr and jpg5, to make sure the log message matches the actual URL we tried to connect
            log_msg = f"Can't connect to {link}. If you're using a VPN, try turning it off \n  {e!s}"
            error_log_msg = ErrorLogMessage(ui_failure, log_msg)
        except Exception as e:
            exc_info = e
            error_log_msg = ErrorLogMessage.from_unknown_exc(e)

        if (skip := getattr(item, "is_segment", None)) and skip is not None:
            return

        link_to_show = link_to_show or link
        origin = origin or get_origin(item)
        log_prefix = getattr(self, "log_prefix", None)
        if log_prefix:  # This error came from a Downloader
            await self.write_download_error(item, error_log_msg, exc_info)  # type: ignore
            return

        log(f"Scrape Failed: {link_to_show} ({error_log_msg.main_log_msg})", 40, exc_info=exc_info)
        await self.manager.log_manager.write_scrape_error_log(link_to_show, error_log_msg.csv_log_msg, origin)
        self.manager.progress_manager.scrape_stats_progress.add_failure(error_log_msg.ui_failure)

    return wrapper


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def sanitize_filename(name: str) -> str:
    """Simple sanitization to remove illegal characters from filename."""
    return re.sub(constants.SANITIZE_FILENAME_PATTERN, "", name).strip()


def sanitize_folder(title: str) -> str:
    """Simple sanitization to remove illegal characters from titles and trim the length to be less than 60 chars."""
    title = title.replace("\n", "").strip()
    title = title.replace("\t", "").strip()
    title = re.sub(" +", " ", title)
    title = re.sub(r'[\\*?:"<>|/]', "-", title)
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


def convert_text_by_diff(text: Text) -> str:
    """Returns `rich.text` as a plain str with diff syntax."""

    STYLE_TO_DIFF = {
        "green": "+   {}",
        "red": "-   {}",
        "yellow": "*** {}",
    }

    diff_text = ""
    default_format: str = "{}"
    for line in text.split(allow_blank=True):
        line_str = line.plain.rstrip("\n")
        first_span = line.spans[0] if line.spans else None
        style: str = str(first_span.style) if first_span else ""
        color = style.split(" ")[0] or "black"  # remove console hyperlink markup (if any)
        line_format: str = STYLE_TO_DIFF.get(color) or default_format
        diff_text += line_format.format(line_str) + "\n"

    return diff_text


def purge_dir_tree(dirname: Path) -> None:
    """Purges empty files and directories efficiently."""
    if not dirname.is_dir():
        return

    # Use os.walk() to remove empty files and directories in a single pass
    for dirpath, _dirnames, filenames in os.walk(dirname, topdown=False):
        dir_path = Path(dirpath)

        # Remove empty files
        for file_name in filenames:
            file_path = dir_path / file_name
            if file_path.exists() and file_path.stat().st_size == 0:
                file_path.unlink()

        # Remove empty directories
        with contextlib.suppress(OSError):
            dir_path.rmdir()


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


async def send_webhook_message(manager: Manager) -> None:
    """Outputs the stats to a code block for webhook messages."""
    webhook = manager.config_manager.settings_data.logs.webhook

    if not webhook:
        return

    rich.print("\nSending Webhook Notifications.. ")
    url: URL = webhook.url.get_secret_value()  # type: ignore
    text: Text = constants.LOG_OUTPUT_TEXT
    diff_text = convert_text_by_diff(text)
    main_log = manager.path_manager.main_log

    form = FormData()

    if "attach_logs" in webhook.tags and (size := await asyncio.to_thread(get_size_or_none, main_log)):
        if size <= 25 * 1024 * 1024:  # 25MB
            async with aiofiles.open(main_log, "rb") as f:
                form.add_field("file", await f.read(), filename=main_log.name)

        else:
            diff_text += "\n\nWARNING: log file too large to send as attachment\n"

    form.add_fields(
        ("content", f"```diff\n{diff_text}```"),
        ("username", "CyberDrop-DL"),
    )

    async with ClientSession() as session, session.post(url, data=form) as response:
        successful = 200 <= response.status <= 300
        result = [constants.NotificationResult.SUCCESS.value]
        result_to_log = result
        if not successful:
            json_resp: dict = await response.json()
            if "content" in json_resp:
                json_resp.pop("content")
            json_resp_str = json.dumps(json_resp, indent=4)
            result_to_log = constants.NotificationResult.FAILED.value, json_resp_str

        log_spacer(10, log_to_console=False)
        rich.print("Webhook Notifications Results:", *result)
        logger = log_debug if successful else log
        result_to_log = "\n".join(map(str, result_to_log))
        logger(f"Webhook Notifications Results: {result_to_log}")


def open_in_text_editor(file_path: Path) -> bool | None:
    """Opens file in OS text editor."""
    using_ssh = "SSH_CONNECTION" in os.environ
    using_desktop_enviroment = any(var in os.environ for var in ("DISPLAY", "WAYLAND_DISPLAY"))
    custom_editor = os.environ.get("EDITOR")

    if custom_editor:
        path = shutil.which(custom_editor)
        if not path:
            msg = f"Editor '{custom_editor}' from env bar $EDITOR is not available"
            raise ValueError(msg)
        cmd = path, file_path

    elif platform.system() == "Darwin":
        cmd = "open", "-a", "TextEdit", file_path

    elif platform.system() == "Windows":
        cmd = "notepad.exe", file_path

    elif using_desktop_enviroment and not using_ssh and set_default_app_if_none(file_path):
        cmd = "xdg-open", file_path

    elif fallback_editor := get_first_available_editor():
        cmd = fallback_editor, file_path
        if fallback_editor.stem == "micro":
            cmd = fallback_editor, "-keymenu", "true", file_path
    else:
        msg = "No default text editor found"
        raise ValueError(msg)

    rich.print(f"Opening '{file_path}' with '{cmd[0]}'...")
    subprocess.call([*cmd], stderr=subprocess.DEVNULL)


@lru_cache
def get_first_available_editor() -> Path | None:
    for editor in TEXT_EDITORS:
        path = shutil.which(editor)
        if path:
            return Path(path)


@lru_cache
def set_default_app_if_none(file_path: Path) -> bool:
    mimetype = xdg_mime_query("filetype", str(file_path))
    if not mimetype:
        return False

    default_app = xdg_mime_query("default", mimetype)
    if default_app:
        return True

    text_default = xdg_mime_query("default", "text/plain")
    if text_default:
        return subprocess.call(["xdg-mime", "default", text_default, mimetype]) == 0

    return False


def get_valid_dict(dataclass: Dataclass | type[Dataclass], info: dict[str, Any]) -> dict[str, Any]:
    """Remove all keys that are not fields in the dataclass"""
    return {k: v for k, v in info.items() if k in get_field_names(dataclass)}


@lru_cache
def get_field_names(dataclass: Dataclass | type[Dataclass]) -> list[str]:
    return [f.name for f in fields(dataclass)]


def get_text_between(original_text: str, start: str, end: str) -> str:
    """Extracts the text between two strings in a larger text."""
    start_index = original_text.index(start) + len(start)
    end_index = original_text.index(end, start_index)
    return original_text[start_index:end_index]


def xdg_mime_query(*args) -> str:
    assert args
    arg_list = ["xdg-mime", "query", *args]
    return subprocess_get_text(arg_list).stdout.strip()


def parse_url(link_str: str, relative_to: URL | None = None, *, trim: bool = True) -> URL:
    """Parse a string into an absolute URL, handling relative URLs, encoding and optionally removes trailing slash (trimming).
    Raises:
        InvalidURLError: If the input string is not a valid URL or if any other error occurs during parsing.
        TypeError: If `relative_to` is `None` and the parsed URL is relative or has no scheme.
    """

    base: URL = relative_to  # type: ignore

    def fix_query_params_encoding() -> str:
        if "?" not in link_str:
            return link_str
        parts, query_and_frag = link_str.split("?", 1)
        query_and_frag = query_and_frag.replace("+", "%20")
        return f"{parts}?{query_and_frag}"

    try:
        assert link_str, "link_str is empty"
        assert isinstance(link_str, str), f"link_str must be a string object, got: {link_str!r}"
        clean_link_str = fix_query_params_encoding()
        is_encoded = "%" in clean_link_str
        new_url = URL(clean_link_str, encoded=is_encoded)
    except (AssertionError, AttributeError, ValueError, TypeError) as e:
        raise InvalidURLError(str(e), url=link_str) from e
    if not new_url.absolute:
        new_url = base.join(new_url)
    if not new_url.scheme:
        new_url = new_url.with_scheme(base.scheme or "https")
    if not trim:
        return new_url
    return remove_trailing_slash(new_url)


def remove_trailing_slash(url: URL) -> URL:
    if url.name or url.path == "/":
        return url
    return url.parent.with_fragment(url.fragment).with_query(url.query)


def remove_parts(url: URL, *parts_to_remove: str, keep_query: bool = True, keep_fragment: bool = True) -> URL:
    assert parts_to_remove
    new_parts = [p for p in url.parts[1:] if p not in set(parts_to_remove)]
    return url.with_path("/".join(new_parts), keep_fragment=keep_fragment, keep_query=keep_query)


async def get_soup_no_error(response: CurlResponse | AnyResponse) -> BeautifulSoup | None:
    # We can't use `CurlResponse` at runtime so we check the reverse
    with contextlib.suppress(UnicodeDecodeError):
        if isinstance(response, AnyResponse):
            content = await response.read()  # aiohttp
        else:
            content = response.content  # curl response
        return BeautifulSoup(content, "html.parser")


def get_og_properties(soup: BeautifulSoup) -> OGProperties:
    """Extracts Open Graph properties (og properties) from soup."""
    og_properties: dict[str, str] = {}

    for meta in soup.select('meta[property^="og:"]'):
        property_name = meta["property"].replace("og:", "").replace(":", "_")  # type: ignore
        og_properties[property_name] = meta["content"] or ""  # type: ignore

    return OGProperties(**og_properties)


def get_filename_from_headers(headers: Mapping[str, Any]) -> str | None:
    """Get `filename=` value from `Content-Disposition`"""
    content_disposition: str | None = headers.get("Content-Disposition")
    if not content_disposition:
        return
    if match := re.search(FILENAME_REGEX, content_disposition):
        matches = match.groups()
        return matches[0] or matches[1]


def get_size_or_none(path: Path) -> int | None:
    """Checks if this is a file and returns its size with a single system call.

    Returns `None` otherwise"""

    try:
        stat = path.stat()
        if S_ISREG(stat.st_mode):
            return stat.st_size
    except (OSError, ValueError):
        return None


log_cyan = partial(log_with_color, style="cyan", level=20)
log_yellow = partial(log_with_color, style="yellow", level=20)
log_green = partial(log_with_color, style="green", level=20)
log_red = partial(log_with_color, style="red", level=20)
