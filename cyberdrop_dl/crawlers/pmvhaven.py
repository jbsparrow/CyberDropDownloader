from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


JS_VIDEO_INFO_SELECTOR = "script#__NUXT_DATA__"
API_ENTRYPOINT = URL("https://pmvhaven.com/api/v2/")
PRIMARY_BASE_DOMAIN = URL("https://pmvhaven.com")
CATEGORIES = "Hmv", "Pmv", "Hypno", "Tiktok", "KoreanBJ"
INCLUDE_VIDEO_ID_IN_FILENAME = True


class PMVHavenCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pmvhaven", "PMVHaven")

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.parts:
            return await self.video_from_api(scrape_item)
        if "star" in scrape_item.url.parts:
            return await self.model(scrape_item)
        if "tags" in scrape_item.url.parts:
            return await self.tag(scrape_item)
        if "music" in scrape_item.url.parts:
            return await self.music(scrape_item)
        if "search" in scrape_item.url.parts:
            return await self.search(scrape_item)
        if "category" in scrape_item.url.parts:
            return await self.category(scrape_item)
        if "profile" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        if "playlist" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        username = scrape_item.url.name
        api_url = API_ENTRYPOINT / "profileInput"
        title = f"{username} [user]"
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        # Videos
        add_data = {"mode": "GetMoreProfileVideos", "user": username}
        async for json_resp in self.api_pager(api_url, add_data):
            await self.iter_videos(scrape_item, json_resp["data"], "Videos")

        # Favorites
        add_data = {"mode": "GetMoreFavoritedVideos", "user": username, "search": None, "date": "Date", "sort": "Sort"}
        async for json_resp in self.api_pager(api_url, add_data):
            await self.iter_videos(scrape_item, json_resp["data"], "Favorites")

        # Playlist
        # TODO: add pagination support for user playlists
        add_headers = {"Content-Type": "text/plain;charset=UTF-8"}
        add_data = json.dumps({"profile": username, "mode": "GetUser"})
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.domain, api_url, data=add_data, headers_inc=add_headers)

        user_info: dict[str, dict] = json_resp["data"]
        for playlist in user_info["playlists"]:
            playlist_id = playlist["_id"]
            link = PRIMARY_BASE_DOMAIN / "playlist" / playlist_id
            new_scrape_item = scrape_item.create_child(link, new_title_part="Playlists")
            self.manager.task_group.create_task(self.playlist(new_scrape_item, add_suffix=False))
            scrape_item.add_children()

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, add_suffix: bool = True) -> None:
        playlist_id = scrape_item.url.name
        add_data = {"mode": "loadPlaylistVideos", "playlist": playlist_id}
        api_url = API_ENTRYPOINT / "playlists"
        title: str = ""
        async for json_resp in self.api_pager(api_url, add_data, check_key="videos"):
            if not title:
                playlist_name: str = json_resp["playlist"]["name"]
                title = f"{playlist_name} [playlist]" if add_suffix else playlist_name
                title = self.create_title(title, playlist_id)
                scrape_item.setup_as_album(title, album_id=playlist_id)
            await self.iter_videos(scrape_item, json_resp["videos"])

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        model_name = scrape_item.url.name
        add_data = {"mode": "SearchStar", "star": model_name, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, model_name, "model")

    @error_handling_wrapper
    async def creator(self, scrape_item: ScrapeItem) -> None:
        creator_name = scrape_item.url.name
        add_data = {"mode": "SearchCreator", "creator": creator_name, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, creator_name, "creator")

    @error_handling_wrapper
    async def music(self, scrape_item: ScrapeItem) -> None:
        song_name = scrape_item.url.name
        add_data = {"mode": "SearchMusic", "music": song_name, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, song_name, "music")

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_value = scrape_item.url.name
        add_data = {"mode": "DefaultSearch", "data": search_value, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, search_value, "search")

    @error_handling_wrapper
    async def category(self, scrape_item: ScrapeItem) -> None:
        category_name = ""
        for cat in CATEGORIES:  # Search values are case sensitive but the URL for categories is always lowercase
            if cat.casefold() == scrape_item.url.name.casefold():
                category_name = cat
                break
        if not category_name:
            raise ScrapeError(422)
        add_data = {"mode": category_name, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, category_name, "category")

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        tag_name = scrape_item.url.name
        add_data = {"mode": "SearchMoreTag", "tag": tag_name, "profile": None}
        await self._generic_search_pager(scrape_item, add_data, tag_name, "tag")

    @error_handling_wrapper
    async def video_from_api(self, scrape_item: ScrapeItem):
        if await self.check_complete_from_referer(scrape_item):
            return

        video_id: str = scrape_item.url.name.rsplit("_", 1)[-1]
        add_data = {"video": video_id, "mode": "InitVideo", "view": True}
        api_url = API_ENTRYPOINT / "videoInput"
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.domain, api_url, data=add_data)

        videos = json_resp.get("video")
        video_info: dict = videos[0] if videos else {}
        await self.process_video_info(scrape_item, video_info)

    @error_handling_wrapper
    async def video_from_soup(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        video_info = get_video_info_from_js(soup)
        await self.process_video_info(scrape_item, video_info)

    async def _generic_search_pager(self, scrape_item: ScrapeItem, add_data: dict, name: str, type: str = "") -> None:
        title: str = ""
        api_url = API_ENTRYPOINT / "search"
        async for json_resp in self.api_pager(api_url, add_data):
            if not title:
                title = f"{name} [{type}]" if type else name
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            await self.iter_videos(scrape_item, json_resp["data"])

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @error_handling_wrapper
    async def process_video_info(self, scrape_item: ScrapeItem, video_info: dict) -> None:
        log_debug(json.dumps(video_info, indent=4))
        link_str: str = video_info.get("url") or ""
        if not link_str:
            raise ScrapeError(422, message="No video source found")

        video_id: str = video_info["_id"]
        resolution: str = video_info.get("height") or ""
        title: str = video_info.get("title") or video_info["uploadTitle"]
        link_str: str = video_info["url"]
        date = parse_datetime(video_info["isoDate"])

        scrape_item.possible_datetime = date
        link = self.parse_url(link_str)
        resolution = f"{resolution}p" if resolution else "Unknown"
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".mp4")
        include_id = f"[{video_id}]" if INCLUDE_VIDEO_ID_IN_FILENAME else ""
        custom_filename = f"{title} {include_id}[{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def iter_videos(self, scrape_item: ScrapeItem, videos: list[dict], new_title_part: str = "") -> None:
        for video in videos:
            link = create_canonical_video_url(video)
            new_scrape_item = scrape_item.create_child(link, new_title_part=new_title_part)
            await self.process_video_info(new_scrape_item, video)
            scrape_item.add_children()

    async def api_pager(self, api_url: URL, add_data: dict, *, check_key: str = "data") -> AsyncGenerator[dict]:
        """Generator of API pages."""
        page: int = 1
        is_profile = api_url.name == "profileInput"
        add_headers = {"Content-Type": "text/plain;charset=UTF-8"} if is_profile else None

        while True:
            data = {"index": page} | add_data
            if is_profile:
                data = json.dumps(data)
            async with self.request_limiter:
                json_resp: dict = await self.client.post_data(self.domain, api_url, data=data, headers_inc=add_headers)

            has_videos = bool(json_resp[check_key])
            if not has_videos:
                break
            yield json_resp
            page += 1


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def create_canonical_video_url(video_info: dict) -> URL:
    title: str = video_info.get("title") or video_info["uploadTitle"]
    video_id: str = video_info["_id"]
    path = f"{title}_{video_id}"
    return PRIMARY_BASE_DOMAIN / "video" / path


def get_video_info_from_js(soup: BeautifulSoup) -> dict:
    info_js_script = soup.select_one(JS_VIDEO_INFO_SELECTOR)
    js_text = info_js_script.text if info_js_script else None
    if not js_text:
        raise ScrapeError(422)
    json_data: list = javascript.parse_json_to_dict(js_text, use_regex=False)  # type: ignore
    info_dict = {"data": json_data}
    javascript.clean_dict(info_dict)
    indices: dict[str, int] = {}
    video_properties = {}
    for elem in info_dict["data"]:
        if isinstance(elem, dict) and all(p in elem for p in ("uploadTitle", "isoDate")):
            indices = elem
            break
    for name, index in indices.items():
        video_properties[name] = info_dict["data"][index]
    return video_properties


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.fromisoformat(date.replace("Z", "+00.00"))
    return calendar.timegm(parsed_date.timetuple())
