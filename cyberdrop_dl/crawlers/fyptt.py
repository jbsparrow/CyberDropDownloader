from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, URLConfig
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@URLConfig(trim=False)
class FYPTTCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[dict[str, str | tuple[str, ...]]] = {"Post": "/<post_id>/..."}
    DOMAIN: ClassVar[str] = "fyptt"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fyptt.to")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [post_id, *_] if post_id.isdecimal():
                await self.post(scrape_item, post_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        article = json_ld.find_elem(soup, "Article")
        name: str = article["headline"]

        scrape_item.uploaded_at = self.parse_iso_date(article["datePublished"])
        iframe = self.parse_url(css.select(soup, "iframe", "src"))
        headers = {"Referer": str(scrape_item.url)}

        async with self.request(iframe, headers=headers) as resp:
            try:
                src = extr_text(await resp.text(), 'player.setup({file:"', '",')
            except ValueError:
                src = css.select(await resp.soup(), "video source", "src")

        src = self.parse_url(src)
        m3u8 = info = None
        if src.suffix == ".m3u8":
            m3u8, info = await self.request_m3u8(src, headers=headers)

        filename = self.create_custom_filename(
            name,
            ext := ".mp4",
            file_id=post_id,
            resolution=info and info.resolution,
        )

        await self.handle_file(
            src,
            scrape_item,
            name,
            ext,
            custom_filename=filename,
            thumbnail=self.parse_url(article["thumbnailUrl"]),
            m3u8=m3u8,
        )
