from __future__ import annotations

import json
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


AJAX_ENTRYPOINT = URL("https://ajax.streamable.com/videos/")

STATUS_OK = 2
VIDEO_STATUS = {
    0: "Video is still being uploaded",
    1: "Video is still being processed",
    2: "Ready",
    3: "Video is unavailable",
}


class StreamableCrawler(Crawler):
    primary_base_domain = URL("https://streamable.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "streamable", "Streamable")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        video_id = scrape_item.url.name or scrape_item.url.parent.name
        canonical_url = self.primary_base_domain / video_id
        scrape_item.url = canonical_url

        if await self.check_complete_from_referer(canonical_url):
            return

        ajax_url = AJAX_ENTRYPOINT / video_id
        async with self.request_limiter:
            json_resp: BeautifulSoup = await self.client.get_json(self.domain, ajax_url)

        status: int = json_resp.get("status")  # type: ignore
        if status != STATUS_OK:
            raise ScrapeError(404, VIDEO_STATUS.get(status))

        title = json_resp.get("reddit_title") or json_resp["title"]
        scrape_item.possible_datetime = json_resp.get("date_added")  # type: ignore

        log_debug(json.dumps(json_resp, indent=4))
        link_str = get_best_quality(json_resp["files"])  # type: ignore
        if not link_str:
            raise ScrapeError(422)

        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_best_quality(info_dict: dict[str, dict[str, str]]) -> str:
    """Returns URL of the best available quality.

    Returns URL as `str`"""
    default = ""
    links = {}
    for name, file in info_dict.items():
        link_str: str | None = file.get("url")
        if not link_str:
            continue
        links[name] = link_str
        if not default:
            default = link_str

    return links.get("mp4") or default
