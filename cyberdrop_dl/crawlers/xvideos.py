from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class XVideosCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/video<video_id>/<title>",
            "/video.<video_id>/<title>",
        ),
    }

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.xvideos.com")
    DOMAIN: ClassVar[str] = "xvideos"
    FOLDER_DOMAIN: ClassVar[str] = "xVideos"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [part, _] if part.startswith("video"):
                video_id = part.removeprefix("video").removeprefix(".")
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if error := soup.select_one("h1.inlineError"):
            raise ScrapeError(404, css.get_text(error))

        title = page_title(soup, self.DOMAIN)
        scrape_item.possible_datetime = self.parse_iso_date(get_json_ld_date(soup))
        script = css.select_one_get_text(soup, "script:contains('setVideoHLS(')")
        m3u8_url = self.parse_url(get_text_between(script, "setVideoHLS('", "')"))
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_url)
        custom_filename = self.create_custom_filename(title, ".mp4", file_id=video_id, resolution=info.resolution.name)
        await self.handle_file(
            scrape_item.url, scrape_item, video_id + ".mp4", m3u8=m3u8, custom_filename=custom_filename
        )


# TODO: Move title funtions to css utils
def sanitize_page_title(title: str, domain: str) -> str:
    sld = domain.rsplit(".", 1)[0]

    def clean(string: str, char: str):
        if char in string:
            front, _, tail = string.rpartition(char)
            if sld in tail.casefold():
                string = front.strip()
        return string

    return clean(clean(title, "|"), " - ")


def page_title(soup: BeautifulSoup, domain: str | None = None) -> str:
    title = css.select_one_get_text(soup, "title")
    if domain:
        return sanitize_page_title(title, domain)
    return title


# TODO: Move to css utils
def get_json_ld_date(soup: BeautifulSoup) -> str:
    return get_json_ld_value(soup, "uploadDate")


def get_json_ld(soup: BeautifulSoup, /, contains: str | None = None) -> dict[str, Any]:
    selector = "script[type='application/ld+json']"
    if contains:
        selector += f":contains('{contains}')"

    ld_json = json.loads(css.select_one_get_text(soup, selector))
    return ld_json


def get_json_ld_value(soup: BeautifulSoup, key: str) -> Any:
    ld_json = get_json_ld(soup, key)
    return ld_json[key]
