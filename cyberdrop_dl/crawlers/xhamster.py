from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple, Self

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_valid_dict

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


NEXT_PAGE_SELECTOR = ""
JS_VIDEO_INFO_SELECTOR = "script#initials-script"


class Format(NamedTuple):
    height: int
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Video:
    id: str
    id_hash_slug: str
    title: str
    formats: tuple[Format, ...]
    mp4_file: str
    created: int
    url: str

    @classmethod
    def from_dict(cls, info_dict: dict) -> Self:
        sources: dict = info_dict.get("sources") or {}
        mp4_sources: dict[str, dict] = sources.get("mp4") or {}
        mp4_file: str = info_dict.get("mp4File") or ""
        formats = [Format(0, mp4_file)]

        for resolution, details in mp4_sources.items():
            height = int(resolution.removesuffix("p"))
            url: str = details["link"]
            formats.append(Format(height, url))

        valid_vars = get_valid_dict(cls, info_dict)
        return cls(
            **valid_vars,
            url=info_dict["pageURL"],
            id_hash_slug=info_dict["idHashSlug"],
            mp4_file=mp4_file,
            formats=tuple(formats),
        )


class XhamsterCrawler(Crawler):
    primary_base_domain = URL("https://xhamster.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xhamster", "xHamster")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        ## TODO: gallery support, user profile support, categories and tags
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        video_info = get_info_dict(soup)
        if not video_info:
            raise ScrapeError(422)

        video = Video.from_dict(video_info)
        canonical_url = self.parse_url(video.url)
        best_format = max(video.formats)
        if not best_format.url:
            raise ScrapeError(422, message="No video source found")

        scrape_item.url = canonical_url
        scrape_item.possible_datetime = video.created
        resolution = f"{best_format.height}p" if best_format.height else "Unknown"
        link = self.primary_base_domain / "movies" / video.id_hash_slug / "download" / resolution
        debrid_link = self.parse_url(best_format.url)

        filename = f"{video.id_hash_slug}.mp4"
        filename, ext = self.get_filename_and_ext(filename)
        custom_filename = f"{video.title} [{video.id_hash_slug}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(
            link, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=debrid_link
        )


def get_info_dict(soup: BeautifulSoup) -> dict[str, Any]:
    info_js_script = soup.select_one(JS_VIDEO_INFO_SELECTOR)
    del soup
    info_js_script_text = info_js_script.text if info_js_script else None
    if not info_js_script_text:
        raise ScrapeError(422)
    json_text = info_js_script_text.split("=", 1)[-1].removesuffix(";")
    info_dict = javascript.parse_json_to_dict(json_text)
    javascript.clean_dict(info_dict)
    video_info = info_dict["videoModel"]
    log_debug(video_info)
    return video_info
