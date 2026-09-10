from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@dataclasses.dataclass(slots=True)
class Video:
    title: str
    uploaded_at: float
    src: AbsoluteHttpURL
    thumbnail: AbsoluteHttpURL


class YTboobCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": "/video/<slug>"}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://ytboob.com")
    DOMAIN: ClassVar[str] = "ytboob.com"
    FOLDER_DOMAIN: ClassVar[str] = "YTboob"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_]:
                return await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        video = await self._request_video(scrape_item.url)
        scrape_item.uploaded_at = video.uploaded_at

        filename = self.create_custom_filename(video.title, ext := ".mp4")
        await self.handle_file(video.src, scrape_item, video.title, ext, custom_filename=filename)
        _, ext = self.get_filename_and_ext(video.thumbnail.name)
        filename = self.create_custom_filename(video.title, ext, file_id="thumbnail")
        await self.handle_file(
            video.thumbnail,
            scrape_item,
            video.thumbnail.name,
            ext,
            custom_filename=filename,
            frag="thumbnail",
        )

    async def _request_video(self, url: AbsoluteHttpURL) -> Video:
        soup = await self.request_soup(url)
        article: dict[str, Any] = json_ld.find_elem(soup, "Article")
        return Video(
            thumbnail=self.parse_url(article["thumbnailUrl"]),
            uploaded_at=self.parse_iso_date(article["datePublished"]),
            src=self.parse_url(css.select(soup, "video-js source", "src")),
            title=css.unescape(article["headline"]),
        )
