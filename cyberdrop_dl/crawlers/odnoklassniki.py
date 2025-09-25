from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, json
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_find_video_ids = re.compile("/video/(\\d+)").finditer

_HEADERS = {
    "Accept-Language": "en-gb, en;q=0.8",
    "Referer": "https://ok.ru/",
    "Origin": "https://ok.ru",
}

_MOBILE_HEADERS = _HEADERS | {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.180 Mobile Safari/537.36",
    "Referer": "https://m.ok.ru/",
    "Origin": "https://m.ok.ru",
}


class VideoProvider:
    # This site also embeds videos from other sources as their own
    OK_RU = "UPLOADED_ODKL"
    YOUTUBE = "USER_YOUTUBE"
    OG = "OPEN_GRAPH"
    LIVESTREAM = "LIVE_TV_APP"


class Selector:
    CHANNEL_NAME = ".album-info_name"
    CHANNEL_HASH = "script:-soup-contains('gwtHash:')"

    CHANNEL_LAST_ELEMENT = css.CssAttributeSelector("[data-last-element]", "data-last-element")
    FLASHVARS = css.CssAttributeSelector("[data-options*='flashvars']", "data-options")


class OdnoklassnikiCrawler(Crawler):
    SUPPORTED_DOMAINS = "ok.ru", "odnoklassniki.ru"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video/<video_id>",
        "Channel": (
            "/video/c<channel_id>",
            "/profile/<username>/c<channel_id>",
        ),
    }
    PRIMARY_URL = AbsoluteHttpURL("https://ok.ru")
    DOMAIN = "odnoklassniki"
    FOLDER_DOMAIN = "ok.ru"

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
    async def channel(self, scrape_item: ScrapeItem, channel_str: str):
        soup = await self.request_soup(scrape_item.url, headers=_HEADERS)

        channel_id = channel_str.removeprefix("c")
        gwt_hash = get_text_between(css.select_one_get_text(soup, Selector.CHANNEL_HASH), 'gwtHash:"', '",')
        last_element_id = css.select_one_get_attr_or_none(soup, *Selector.CHANNEL_LAST_ELEMENT)
        name = css.select_one_get_text(soup, Selector.CHANNEL_NAME)
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
    async def video(self, scrape_item: ScrapeItem, video_id: str):
        mobile_url = AbsoluteHttpURL(f"https://m.ok.ru/video/{video_id}")
        soup = await self.request_soup(mobile_url, headers=_MOBILE_HEADERS)

        _check_video_is_available(soup)
        metadata: dict[str, Any] = json.loads(Selector.FLASHVARS(soup))["flashvars"]["metadata"]

        if (provider := metadata["provider"]) != VideoProvider.OK_RU:
            raise ScrapeError(422, f"Unsupported provider: {provider}")

        if metadata["movie"].get("is_live"):
            raise ScrapeError(422, "Livestreams are not supported")

        resolution, src = _get_best_src(metadata)
        cdn_url = self.parse_url(src)
        # downloads may fail if we have cdn cookies
        self.client.client_manager.cookies.clear_domain(cdn_url.host)
        json_ld = css.get_json_ld(soup)
        title: str = metadata["movie"].get("title") or json_ld["name"]
        scrape_item.possible_datetime = self.parse_iso_date(json_ld["uploadDate"])
        filename = self.create_custom_filename(title, ".mp4", file_id=video_id, resolution=resolution)
        await self.handle_file(
            mobile_url, scrape_item, video_id + ".mp4", custom_filename=filename, debrid_link=cdn_url
        )


def _get_best_src(metadata: dict[str, Any]) -> tuple[Resolution, str]:
    def parse():
        for video in metadata["videos"]:
            if not video["disallowed"]:
                resolution = Resolution.parse(
                    {
                        "ultra": 2160,
                        "quad": 1440,
                        "full": 1080,
                        "hd": 720,
                        "sd": 480,
                        "low": 360,
                        "lowest": 240,
                        "mobile": 144,
                    }[video["name"]]
                )
                yield resolution, video["url"]

    return max(parse())


def _check_video_is_available(soup: BeautifulSoup) -> None:
    soup_text = soup.text
    if "Access to this video is restricted" in soup_text:
        raise ScrapeError(503)

    if "This video is not available in your region" in soup_text:
        raise ScrapeError(403)
