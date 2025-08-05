from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, json
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class VideoProvider:
    # This site also embeds videos from other sources as their own
    OK_RU = "UPLOADED_ODKL"
    YOUTUBE = "USER_YOUTUBE"
    OG = "OPEN_GRAPH"
    LIVESTREAM = "LIVE_TV_APP"


class Selector:
    VIDEO_DELETED = "a:contains('видео') div.empty"
    UNAUTHORIZED = "div:contains('Access to this video is restricted')"
    GEO_BLOCKED = "div:contains('This video is not available in your region')"
    FLASHVARS = css.CssAttributeSelector("[data-options*='flashvars']", "data-options")


class OdnoklassnikiCrawler(Crawler):
    SUPPORTED_DOMAINS = "ok.ru", "odnoklassniki"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video/<video_id>",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://ok.ru")
    DOMAIN = "odnoklassniki"
    FOLDER_DOMAIN = "ok.ru"

    def __post_init__(self) -> None:
        self._headers = {
            "Accept-Language": "en-gb, en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.180 Mobile Safari/537.36",
            "Referer": "https://m.ok.ru/",
            "Origin": "https://m.ok.ru",
        }

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["video", video_id]:
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    def _clear_cdn_cookies(self, cdn_url: AbsoluteHttpURL) -> None:
        # downloads will fail if we have cdn cookies
        self.client.client_manager.cookies.clear_domain(".mycdn.me")
        self.client.client_manager.cookies.clear_domain(cdn_url.host)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str):
        mobile_url = AbsoluteHttpURL(f"https://m.ok.ru/video/{video_id}")
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, mobile_url, self._headers)

        _check_video_is_available(soup)
        metadata: dict[str, Any] = json.loads(Selector.FLASHVARS(soup))["flashvars"]["metadata"]

        if (provider := metadata["provider"]) != VideoProvider.OK_RU:
            raise ScrapeError(422, f"Unsupported provider: {provider}")

        resolution, src = _get_best_src(metadata)
        link = self.parse_url(src)
        title: str = metadata["movie"]["title"]
        self._clear_cdn_cookies(link)
        filename = self.create_custom_filename(title, ".mp4", file_id=video_id, resolution=resolution)
        await self.handle_file(mobile_url, scrape_item, title + ".mp4", custom_filename=filename, debrid_link=link)


def _get_best_src(metadata: dict[str, Any]):
    def parse():
        for video in metadata["videos"]:
            resolution = {"full": 1080, "hd": 720, "sd": 480, "low": 360, "lowest": 240, "mobile": 144}.get(
                video["name"], 0
            )
            yield resolution, video["url"]

    return max(parse())


def _check_video_is_available(soup: BeautifulSoup):
    if error := soup.select_one(Selector.VIDEO_DELETED):
        raise ScrapeError(404, css.get_text(error))

    if soup.select_one(Selector.UNAUTHORIZED):
        raise ScrapeError(503)

    if soup.select_one(Selector.GEO_BLOCKED):
        raise ScrapeError(403)
