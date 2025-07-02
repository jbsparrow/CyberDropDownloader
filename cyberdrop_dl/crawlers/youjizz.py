from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://www.youjizz.com/")
DEFAULT_QUALITY = "Auto"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)


JS_SELECTOR = "div#content > script:contains('var dataEncodings')"
DATE_SELECTOR = "span.pretty-date"


class Format(NamedTuple):
    resolution: str | None
    link_str: str


## TODO: convert to global dataclass with constructor from dict to use in multiple crawlers
class VideoInfo(dict): ...


class YouJizzCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": ("/video/embed/<video_id>", "/video/<video_id>/...")}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "youjizz"
    FOLDER_DOMAIN: ClassVar[str] = "YouJizz"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in ("videos", "embed")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id = get_video_id(scrape_item.url)
        canonical_url = PRIMARY_URL / "videos" / "embed" / video_id

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.url = canonical_url
        info = get_info(soup)
        v_format = get_best_quality(info)
        if not v_format:
            raise ScrapeError(422)

        resolution, link_str = v_format
        link = self.parse_url(link_str)
        scrape_item.possible_datetime = self.parse_date(info["date"])
        filename, ext = self.get_filename_and_ext(link.name)
        if ext == ".m3u8":
            raise ScrapeError(422)
        custom_filename = self.create_custom_filename(info["title"], ext, file_id=video_id, resolution=resolution)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_video_id(url: URL) -> str:
    if "embed" in url.parts:
        embed_index = url.parts.index("embed")
        return url.parts[embed_index + 1]

    video_id = url.parts[2].rsplit("-", 1)[-1]
    return video_id.removesuffix(".html")


def get_info(soup: BeautifulSoup) -> VideoInfo:
    info_js_script_text: str = css.select_one_get_text(soup, JS_SELECTOR)
    info: dict[str, str | None | dict] = javascript.parse_js_vars(info_js_script_text)
    info["title"] = css.get_attr(soup, "title").replace("\n", "").strip()
    date_tag = soup.select_one(DATE_SELECTOR)
    date_str: str | None = date_tag.text if date_tag else None
    info["date"] = date_str.replace("(s)", "s").strip() if date_str else None
    javascript.clean_dict(info, "stream_data")
    log_debug(json.dumps(info, indent=4))
    return VideoInfo(**info)


def get_best_quality(info_dict: dict) -> Format | None:
    qualities: dict = info_dict["dataEncodings"]
    for res in RESOLUTIONS:
        avaliable_formats = [f for f in qualities if f["name"] == res]
        for format_info in avaliable_formats:
            link_str = format_info["filename"]
            if "/_hls/" not in link_str:
                return Format(res, link_str)
    default_quality: dict = next((f for f in qualities if f["name"] == DEFAULT_QUALITY), {})
    if default_quality:
        default_link_str = default_quality.get("filename") or ""
        return Format(None, default_link_str)
