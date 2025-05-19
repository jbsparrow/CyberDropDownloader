from __future__ import annotations

import random
import string
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    VIDEO = "div#video_player video"
    MD5_JS = "script:contains('/pass_md5/')"
    FILE_ID_JS = "script:contains('file_id')"


_SELECTORS = Selectors()
API_MD5_ENTRYPOINT = URL("https://doodstream.com/pass_md5/")
TOKEN_CHARS = string.ascii_letters + string.digits
SUPPORTED_DOMAINS = [
    "vidply.com",
    "dood.re",
    "doodstream",
    "doodcdn",
    "doodstream.co",
    "dood.yt",
    "do7go.com",
    "all3do.com",
]


class DoodStreamCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"doodstream": SUPPORTED_DOMAINS}
    primary_base_domain = URL("https://doodstream.com/")
    update_unsupported = True

    def __init__(self, manager: Manager, _=None) -> None:
        super().__init__(manager, "doodstream", "DoodStream")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "e" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        canonical_url = scrape_item.url.with_host("doodstream.com")
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            response, soup = await self.client._get_response_and_soup_cffi(self.domain, scrape_item.url)

        host = self.parse_url(response.url).host
        assert host
        del response

        title: str = soup.select_one("title").text  # type: ignore
        title = title.split("- DoodStream")[0].strip()

        file_id = get_file_id(soup)
        debrid_link = await self.get_download_url(host, soup)
        filename, ext = self.get_filename_and_ext(f"{file_id}.mp4")
        custom_filename, _ = self.get_filename_and_ext(f"{title}{ext}")
        scrape_item.url = canonical_url
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, debrid_link=debrid_link, custom_filename=custom_filename
        )

    async def get_download_url(self, host: str, soup: BeautifulSoup) -> URL:
        md5_path = get_md5_path(soup)
        api_url = API_MD5_ENTRYPOINT / md5_path
        token = api_url.name
        async with self.request_limiter:
            new_soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, api_url.with_host(host))

        text = new_soup.get_text(strip=True)
        random_padding = "".join(random.choice(TOKEN_CHARS) for _ in range(10))
        expire = int(datetime.now(UTC).timestamp() * 1000)  # remove decimals
        download_url = self.parse_url(text + random_padding)
        return download_url.with_query(token=token, expiry=expire)


def get_md5_path(soup: BeautifulSoup) -> str:
    js_text: str = js_info.text if (js_info := soup.select_one(_SELECTORS.MD5_JS)) else ""
    if not js_info:
        raise ScrapeError(422)

    return get_text_between(js_text, "/pass_md5/", "'")


def get_file_id(soup: BeautifulSoup) -> str:
    js_text: str = js_info.text if (js_info := soup.select_one(_SELECTORS.FILE_ID_JS)) else ""
    if not js_info:
        raise ScrapeError(422)

    _, file_id, _ = js_text.split("'file_id'")[-1].split("'", 2)
    return file_id
