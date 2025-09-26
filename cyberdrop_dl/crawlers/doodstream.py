from __future__ import annotations

import random
import string
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEO = "div#video_player video"
    MD5_JS = "script:-soup-contains('/pass_md5/')"
    FILE_ID_JS = "script:-soup-contains('file_id')"


_SELECTORS = Selectors()
API_MD5_ENTRYPOINT = AbsoluteHttpURL("https://doodstream.com/pass_md5/")
TOKEN_CHARS = string.ascii_letters + string.digits

PRIMARY_URL = AbsoluteHttpURL("https://doodstream.com/")


class DoodStreamCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": "/e/<video_id>"}
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (
        "vidply.com",
        "dood.re",
        "doodstream",
        "doodcdn",
        "doodstream.co",
        "dood.yt",
        "do7go.com",
        "all3do.com",
    )
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    UPDATE_UNSUPPORTED: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "doodstream"
    FOLDER_DOMAIN: ClassVar[str] = "DoodStream"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "e" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        canonical_url = scrape_item.url.with_host("doodstream.com")
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request(scrape_item.url, impersonate=True) as resp:
            actual_host = resp.url.host
            soup = await resp.soup()

        title = css.page_title(soup, "DoodStream")
        file_id = _get_file_id(soup)
        debrid_link = await self.get_download_url(actual_host, soup)
        filename, ext = self.get_filename_and_ext(f"{file_id}.mp4")
        custom_filename = self.create_custom_filename(title, ext, file_id=file_id)
        scrape_item.url = canonical_url
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, debrid_link=debrid_link, custom_filename=custom_filename
        )

    async def get_download_url(self, host: str, soup: BeautifulSoup) -> AbsoluteHttpURL:
        md5_path = _get_md5_path(soup)
        api_url = API_MD5_ENTRYPOINT / md5_path
        token = api_url.name

        text = await self.request_text(api_url.with_host(host), impersonate=True)
        random_padding = "".join(random.choice(TOKEN_CHARS) for _ in range(10))
        expire = int(datetime.now(UTC).timestamp() * 1000)
        download_url = self.parse_url(text + random_padding)
        return download_url.with_query(token=token, expiry=expire)


def _get_md5_path(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, _SELECTORS.MD5_JS)
    return get_text_between(js_text, "/pass_md5/", "'")


def _get_file_id(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, _SELECTORS.FILE_ID_JS)
    _, file_id, _ = js_text.split("'file_id'")[-1].split("'", 2)
    return file_id
