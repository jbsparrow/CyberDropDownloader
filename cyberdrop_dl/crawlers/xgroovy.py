from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://xgroovy.com")

class Selectors:
    VIDEO = "video#main_video"
    UPLOAD_DATE = "script:-soup-contains('uploadDate')"


_SELECTORS = Selectors()


class Format(NamedTuple):
    resolution: str
    link_str: str


class XGroovyCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": ("/<category>/videos/<video_id>/...", "/videos/<video_id>/..."),
    }
    DOMAIN: ClassVar[str] = "xgroovy"
    FOLDER_DOMAIN: ClassVar[str] = "XGroovy"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        video_id: str = scrape_item.url.parts[scrape_item.url.parts.index("videos") + 1]
        soup = await self.request_soup(scrape_item.url)
        best_format: Format = _get_best_format(css.select_one(soup, _SELECTORS.VIDEO))
        link = self.parse_url(best_format.link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        title = open_graph.get_title(soup)
        context = json.loads(css.select_one_get_text(soup, _SELECTORS.UPLOAD_DATE))
        scrape_item.possible_datetime = self.parse_iso_date(context.get("uploadDate"))
        custom_filename = self.create_custom_filename(
            title, ext, file_id=video_id, resolution=best_format.resolution
        )
        return await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def _get_best_format(video_tag):
    options = []
    for src in video_tag.find_all("source"):
        url = src.get("src")
        title = src.get("title", "0p")
        resolution = int(title.replace("p", ""))
        options.append((resolution, url, title))
    best = max(options, key=lambda x: x[0])
    return Format(best[2], best[1])
