from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, ParamSpec, TypeVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import InvalidContentTypeError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.filters import has_valid_extension
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


P = ParamSpec("P")
R = TypeVar("R")

VIDEO_SELECTOR = "video > source"


def log_unsupported_wrapper(
    func: Callable[P, Coroutine[None, None, R]],
) -> Callable[P, Coroutine[None, None, R | None]]:
    @wraps(func)
    async def wrapper(*args, **kwargs) -> R | None:
        self: GenericCrawler = args[0]
        item: ScrapeItem = args[1]
        try:
            return await func(*args, **kwargs)
        except (InvalidContentTypeError, ScrapeError) as e:
            await self.log_unsupported(item, f"({e})")
        except Exception:
            raise

    return wrapper


@dataclass(frozen=True, slots=True)
class FakeURL:
    host: str
    scheme: str = "https"
    path: str = "/"
    query: str = ""
    fragment: str = ""


class GenericCrawler(Crawler):
    DOMAIN: ClassVar[str] = "generic"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = FakeURL(host=".")  # type: ignore

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        await self.file(scrape_item)

    @error_handling_wrapper
    @log_unsupported_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        content_type = await self.get_content_type(scrape_item.url)
        if "html" in content_type:
            return await self.try_video_from_soup(scrape_item)

        filename, ext = guess_filename_and_ext(scrape_item.url, content_type)
        if not ext:
            msg = f"Received '{content_type}', was expecting other"
            raise InvalidContentTypeError(message=msg)
        fullname = Path(filename).with_suffix(ext)
        filename, _ = self.get_filename_and_ext(fullname.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    async def get_content_type(self, url: AbsoluteHttpURL) -> str:
        async with self.request_limiter:
            headers = await self.client.get_head(self.DOMAIN, url)
        content_type: str = headers.get("Content-Type", "")
        if not content_type:
            raise ScrapeError(422)
        return content_type.lower()

    async def try_video_from_soup(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        try:
            title = css.select_one_get_text(soup, "title").rsplit(" - ", 1)[0].rsplit("|", 1)[0]
            link_str: str = css.select_one_get_attr(soup, VIDEO_SELECTOR, "src")
        except (AssertionError, AttributeError, KeyError):
            raise ScrapeError(422) from None

        link = self.parse_url(link_str, scrape_item.url.with_path("/"))
        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            filename, ext = self.get_filename_and_ext(link.name + ".mp4")
        custom_filename = self.create_custom_filename(title, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def log_unsupported(self, scrape_item: ScrapeItem, msg: str = "") -> None:
        log(f"Unsupported URL: {scrape_item.url} {msg}", 30)
        self.manager.log_manager.write_unsupported_urls_log(scrape_item.url, scrape_item.origin)
        self.manager.progress_manager.scrape_stats_progress.add_unsupported()


def guess_filename_and_ext(url: AbsoluteHttpURL, content_type: str) -> tuple[str, str | None]:
    filename, ext = get_name_and_ext_from_url(url)
    if filename and ext:
        return filename, ext
    return url.name, get_ext_from_content_type(content_type)


def get_ext_from_content_type(content_type: str) -> str | None:
    return mimetypes.guess_extension(content_type) or CONTENT_TYPE_TO_EXTENSION.get(content_type)


def get_name_and_ext_from_url(url: AbsoluteHttpURL) -> tuple[str, str | None]:
    if not has_valid_extension(url):
        return url.name, None
    try:
        filename, ext = get_filename_and_ext(url.name)
    except NoExtensionError:
        filename, ext = get_filename_and_ext(url.name, forum=True)
    return filename, ext


CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/x-tar": ".tar",
    "image/svg+xml": ".svg",
}
