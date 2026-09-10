from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar, final

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, json, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem

_find_video_ids = re.compile("/video/(\\d+)").finditer

_CHROME_ANDROID_USER_AGENT: str = (
    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.180 Mobile Safari/537.36"
)
_HEADERS = {
    "Accept-Language": "en-gb, en;q=0.8",
    "Referer": "https://ok.ru/",
    "Origin": "https://ok.ru",
}

_MOBILE_HEADERS = _HEADERS | {
    "User-Agent": _CHROME_ANDROID_USER_AGENT,
    "Referer": "https://m.ok.ru/",
    "Origin": "https://m.ok.ru",
}


@final
class Selector:
    CHANNEL_NAME = ".album-info_name"
    CHANNEL_HASH = "script:-soup-contains('gwtHash:')"

    CHANNEL_LAST_ELEMENT = css.CssAttributeSelector("[data-last-element]", "data-last-element")


class OdnoklassnikiCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "ok.ru", "odnoklassniki.ru"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video/<video_id>",
        "Channel": (
            "/video/c<channel_id>",
            "/profile/<username>/c<channel_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://ok.ru")
    DOMAIN: ClassVar[str] = "odnoklassniki"
    FOLDER_DOMAIN: ClassVar[str] = "ok.ru"

    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return super()._prepare_headers(scrape_item) | _MOBILE_HEADERS

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["video", id_]:
                if id_.startswith("c"):
                    return await self.channel(scrape_item, id_)
                return await self.video(scrape_item, id_)
            case ["profile", _, channel] if channel.startswith("c"):
                return await self.channel(scrape_item, channel)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def channel(self, scrape_item: ScrapeItem, channel_str: str) -> None:
        soup = await self.request_soup(scrape_item.url, headers=_HEADERS)
        channel_id = channel_str.removeprefix("c")
        gwt_hash = extr_text(css.select_text(soup, Selector.CHANNEL_HASH), 'gwtHash:"', '",')

        try:
            last_element_id = css.select(soup, *Selector.CHANNEL_LAST_ELEMENT)
        except css.SelectorError:
            last_element_id = None

        name = css.select_text(soup, Selector.CHANNEL_NAME)
        scrape_item.setup_as_album(self.create_title(name, channel_id), album_id=channel_id)

        page_url = (self.PRIMARY_URL / "video" / channel_str).with_query(
            {
                "st.cmd": "anonymVideo",
                "st.m": "ALBUM",
                "st.ft": "album",
                "st.aid": channel_str,
                "cmd": "VideoAlbumBlock",
            }
        )
        seen: set[str] = set()
        content = str(soup)
        page = 1
        while True:
            page_had_new_videos = False
            for match in _find_video_ids(content):
                if (video_path := match.group()) not in seen:
                    seen.add(video_path)
                    page_had_new_videos = True
                    video_url = self.PRIMARY_URL.with_path(video_path)
                    new_scrape_item = scrape_item.create_child(video_url)
                    self.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

            if not page_had_new_videos or not last_element_id:
                break

            page += 1
            async with self.request(
                page_url,
                method="POST",
                headers=_HEADERS,
                data={
                    "fetch": "false",
                    "st.page": page,
                    "st.lastelem": last_element_id,
                    "gwt.requested": gwt_hash,
                },
            ) as resp:
                last_element_id = resp.headers.get("lastelem")
                content = await resp.text()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        mobile_url = AbsoluteHttpURL(f"https://m.ok.ru/video/{video_id}")
        soup = await self.request_soup(mobile_url, headers=_MOBILE_HEADERS)

        _check_video_is_available(soup)
        metadata: dict[str, Any] = json.loads(css.select(soup, "a[data-video]", "data-video"))
        src = self.parse_url(metadata["videoSrc"])
        name: str = metadata["videoName"]
        scrape_item.uploaded_at = json_ld.upload_date(soup)

        m3u8, info = await self.request_m3u8_playlist(src, headers=_MOBILE_HEADERS)
        # downloads may fail if we have cdn cookies
        self.client.cookies.clear_domain(info.urls.video.host)
        filename = self.create_custom_filename(
            name,
            ext := ".mp4",
            file_id=video_id,
            resolution=info.resolution,
        )
        await self.handle_file(
            mobile_url,
            scrape_item,
            name,
            ext,
            custom_filename=filename,
            m3u8=m3u8,
            thumbnail=metadata.get("videoPosterSrc"),
        )


def _check_video_is_available(soup: BeautifulSoup) -> None:
    content = soup.get_text()

    for text, code in {
        "Video has not been found": 404,
        "This video has been deleted": 410,
        "Access to this video is restricted": 503,
        "This video is not available in your region": 403,
    }.items():
        if text in content:
            raise ScrapeError(code)
