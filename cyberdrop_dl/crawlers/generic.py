from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.clients.errors import InvalidContentTypeError, NoExtensionError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.scraper.filters import has_valid_extension
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import Callable

    from bs4 import BeautifulSoup
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


VIDEO_SELECTOR = "video > source"


def log_unsupported_wrapper(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(self: GenericCrawler, item: ScrapeItem, *args, **kwargs):
        try:
            return await func(self, item, *args, **kwargs)
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
    primary_base_domain = FakeURL(host=".")  # type: ignore
    scrape_prefix = "Scraping (unsupported domain):"
    scrape_mapper_domain = "."

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "generic", "Generic")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        await self.file(scrape_item)

    @error_handling_wrapper
    @log_unsupported_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file trying to guess the ext from the headers"""
        content_type = await self.get_content_type(scrape_item.url)
        if "html" in content_type:
            return await self.try_video_from_soup(scrape_item)

        filename, ext = guess_filename_and_ext(scrape_item.url, content_type)
        if not ext:
            msg = f"Received '{content_type}', was expecting other"
            raise InvalidContentTypeError(message=msg)
        fullname = Path(filename).with_suffix(ext)
        filename, _ = get_filename_and_ext(fullname.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    async def get_content_type(self, url: URL) -> str:
        async with self.request_limiter:
            headers: dict = await self.client.get_head(self.domain, url)
        content_type: str = headers.get("Content-Type", "")
        if not content_type:
            raise ScrapeError(422)
        return content_type.lower()

    async def try_video_from_soup(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title: str = soup.select_one("title").text  # type: ignore
        title = title.rsplit(" - ", 1)[0].rsplit("|", 1)[0]

        video = soup.select_one(VIDEO_SELECTOR)
        if not video:
            raise ScrapeError(422)

        link_str: str = video.get("src")  # type: ignore
        link = self.parse_url(link_str, scrape_item.url.with_path("/"))
        try:
            filename, ext = get_filename_and_ext(link.name)
        except NoExtensionError:
            filename, ext = get_filename_and_ext(link.name + ".mp4")
        await self.handle_file(link, scrape_item, filename, ext)

    async def log_unsupported(self, scrape_item: ScrapeItem, msg: str = "") -> None:
        log(f"Unsupported URL: {scrape_item.url} {msg}", 30)
        await self.manager.log_manager.write_unsupported_urls_log(
            scrape_item.url,
            scrape_item.parents[0] if scrape_item.parents else None,
        )
        self.manager.progress_manager.scrape_stats_progress.add_unsupported()


def guess_filename_and_ext(url: URL, content_type: str) -> tuple[str, str | None]:
    filename, ext = get_name_and_ext_from_url(url)
    if filename and ext:
        return filename, ext
    return url.name, get_ext_from_content_type(content_type)


def get_ext_from_content_type(content_type: str) -> str | None:
    return mimetypes.guess_extension(content_type) or CONTENT_TYPE_TO_EXTENSION.get(content_type)


def get_name_and_ext_from_url(url: URL) -> tuple[str, str | None]:
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
