from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    ALBUM_ITEM = ".hotgrid a"
    _IMAGE = "img[id*=main-image]"
    _VIDEO = "video > source"
    MEDIA = f"{_IMAGE}, {_VIDEO}"


class HotPicCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/...",
        "Image": "/i/...",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "hotpic", "2385290.xyz", "myhostdata.space"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hotpic.cc")
    DOMAIN: ClassVar[str] = "hotpic"
    FOLDER_DOMAIN: ClassVar[str] = "HotPic"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["album", album_id]:
                return await self.album(scrape_item, album_id)
            case ["i", _]:
                return await self.file(scrape_item)
            case ["uploads" | "reddit", _, *_]:
                return await self.direct_file(scrape_item)
            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return _thumb_to_src(super().transform_url(url))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        soup = await self.request_soup(scrape_item.url)
        title = css.select_text(soup, "title").rpartition(" - ")[0]
        title = self.create_title(title, scrape_item.album_id)
        scrape_item.setup_as_profile(title, album_id=album_id)

        for new_item in self.iter_children(scrape_item, soup, Selector.ALBUM_ITEM):
            self.create_task(self.run(new_item, check_referer=True))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        scrape_item.uploaded_at = json_ld.date_published(soup)
        src = css.select(soup, Selector.MEDIA, "src")
        await self.direct_file(scrape_item, _thumb_to_src(self.parse_url(src)))


def _thumb_to_src(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if "thumb" not in url.parts:
        return url
    if (new_ext := ".mp4") != url.suffix:
        new_ext = ".jpg"
    new_path = url.path.replace("/thumb/", "/")
    return url.with_path(new_path).with_suffix(new_ext)
