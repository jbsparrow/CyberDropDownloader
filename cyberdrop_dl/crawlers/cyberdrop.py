from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers import Registry
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.filepath import remove_file_id
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    ALBUM_TITLE = "#title"
    ALBUM_DATE = ".level-item p:-soup-contains(Uploaded) + p"
    ALBUM_ITEM = "a#file"


@Registry.database.fix_referer
@HTTPConfig(rate_limit=(5, 1))
class CyberdropCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "k1-cd.cdn.gigachad-cdn.ru", "cyberdrop"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/<album_id>",
        "File": (
            "/f/<file_id>",
            "/e/<file_id>",
        ),
        "Direct links": "/api/file/d/<file_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://cyberdrop.cr/")
    DOMAIN: ClassVar[str] = "cyberdrop"
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ("cyberdrop.me", "cyberdrop.to")

    def __post_init__(self) -> None:
        self.api: CyberdropAPI = CyberdropAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["a", album_id, *_]:
                return await self.album(scrape_item, album_id)
            case ["api", "file" | "proxy", "d" | "auth" | "thumb", file_id, *_]:
                return await self.file(scrape_item, file_id)
            case ["f" | "e", file_id]:
                return await self.file(scrape_item, file_id)
            case [_]:
                return await self.follow_redirect(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        scrape_item.url = scrape_item.url.with_query("nojs")
        soup = await self.request_soup(scrape_item.url)
        title = css.select_text(soup, Selector.ALBUM_TITLE)
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        date_str = css.select_text(soup, Selector.ALBUM_DATE)
        scrape_item.uploaded_at = self.parse_date(date_str, "%d.%m.%Y")

        for new_scrape_item in self.iter_children(scrape_item, soup, Selector.ALBUM_ITEM):
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        scrape_item.url = self.PRIMARY_URL / "f" / file_id
        if await self.check_complete_from_referer(scrape_item.url):
            return

        info, auth = await aio.gather(self.api.file_info(file_id), self.api.file_auth(file_id), fail_fast=False)

        name: str = info["name"]
        filename, ext = self.get_filename_and_ext(name)
        link = self.parse_url(auth["url"])
        await self.handle_file(
            link,
            scrape_item,
            name,
            ext,
            custom_filename=remove_file_id(filename, ext),
            thumbnail=info.get("thumbnail_url"),
        )


class CyberdropAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.cyberdrop.cr/api")

    async def file_info(self, file_id: str) -> dict[str, str]:
        api_url = self.ENTRYPOINT / "file/info" / file_id
        return await self.request_json(api_url)

    async def file_auth(self, file_id: str) -> dict[str, str]:
        api_url = self.ENTRYPOINT / "file/auth" / file_id
        return await self.request_json(api_url)
