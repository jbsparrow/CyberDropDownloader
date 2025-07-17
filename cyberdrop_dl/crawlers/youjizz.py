from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from collections.abc import Iterable

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://www.youjizz.com/")
JS_SELECTOR = "div#content > script:contains('var dataEncodings')"
DATE_SELECTOR = "span.pretty-date"


class VideoSource(NamedTuple):
    resolution: int
    url: str


@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    date: str  # Human date
    title: str
    best_src: VideoSource


class YouJizzCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/videos/embed/<video_id>",
            "/videos/<video_name>",
        )
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "youjizz"
    FOLDER_DOMAIN: ClassVar[str] = "YouJizz"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["videos", "embed", video_id]:
                return await self.video(scrape_item, video_id)
            case ["videos", video_name]:
                video_id = video_name.rsplit("-", 1)[-1].removesuffix(".html")
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        canonical_url = PRIMARY_URL / "videos" / "embed" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.url = canonical_url
        video = _parse_video(soup)
        link = self.parse_url(video.best_src.url)
        scrape_item.possible_datetime = self.parse_date(video.date)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(
            video.title, ext, file_id=video_id, resolution=video.best_src.resolution
        )
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )


def _parse_video(soup: BeautifulSoup) -> Video:
    js_text = css.select_one_get_text(soup, JS_SELECTOR)
    encodings_text = get_text_between(js_text, "var dataEncodings =", "var encodings").strip().removesuffix(";")
    data_encodings = json.loads(encodings_text)
    return Video(
        title=open_graph.title(soup),
        date=css.select_one_get_text(soup, DATE_SELECTOR),
        best_src=_get_best_src(data_encodings),
    )


def _get_best_src(data_encodings: list[dict[str, Any]]) -> VideoSource:
    def parse() -> Iterable[VideoSource]:
        for format_info in data_encodings:
            try:
                res = int(format_info["quality"])
            except ValueError:
                continue
            if "/_hls/" not in (link_str := format_info["filename"]):
                yield VideoSource(res, link_str)

    return max(parse())
