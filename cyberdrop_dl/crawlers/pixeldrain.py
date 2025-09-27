from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DownloadError, NoExtensionError, ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

API_ENTRYPOINT = AbsoluteHttpURL("https://pixeldrain.com/api/")
JS_SELECTOR = 'script:-soup-contains("window.initial_node")'
PRIMARY_URL = AbsoluteHttpURL("https://pixeldrain.com")


class PixelDrainCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "pd.cybar.xyz", "pixeldrain.com", "pixeldrain.net", "pixeldra.in"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"File": "/u/...", "Folder": "/l/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "pixeldrain"
    FOLDER_DOMAIN: ClassVar[str] = "PixelDrain"
    _RATE_LIMIT: ClassVar[tuple[float, float]] = 10, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "l" in scrape_item.url.parts:
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)

        api_url = API_ENTRYPOINT / "list" / scrape_item.url.parts[-1]
        json_resp = await self.request_json(api_url)

        log_debug(json_resp)
        title = self.create_title(json_resp["title"], album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for file in json_resp["files"]:
            link = self.create_download_link(file["id"])
            if self.check_album_results(link, results):
                continue

            filename = file["name"]
            date = self.parse_iso_date(file["date_upload"])
            try:
                filename, ext = self.get_filename_and_ext(filename)
            except NoExtensionError:
                mime_type: str = file["mime_type"]
                if not any(media in mime_type for media in ("image", "video")):
                    raise
                filename, ext = self.get_filename_and_ext(f"{filename}.{mime_type.split('/')[-1]}")

            new_scrape_item = scrape_item.create_child(link, possible_datetime=date)
            await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        file_id = scrape_item.url.name
        api_url = API_ENTRYPOINT / "file" / file_id / "info"
        try:
            json_resp: dict[str, Any] = await self.request_json(api_url)
        except DownloadError as e:
            if e.status != 404:
                raise
            return await self.filesystem(scrape_item)

        link = self.create_download_link(json_resp["id"])
        scrape_item.possible_datetime = self.parse_iso_date(json_resp["date_upload"])
        filename: str = json_resp["name"]
        mime_type: str = json_resp["mime_type"]
        try:
            filename, ext = self.get_filename_and_ext(filename)
        except NoExtensionError:
            if "text/plain" in json_resp["mime_type"]:
                new_title = self.create_title(filename)
                scrape_item.setup_as_album(new_title)
                return await self.text(scrape_item)

            if not any(media in mime_type for media in ("image", "video")):
                raise

            filename, ext = self.get_filename_and_ext(f"{filename}.{mime_type.split('/')[-1]}")

        if scrape_item.url.host == "pd.cybar.xyz":
            debrid_link = scrape_item.url
            scrape_item.url = self.PRIMARY_URL / "u" / file_id
        else:
            debrid_link = None
        await self.handle_file(link, scrape_item, filename, ext, debrid_link=debrid_link)

    async def text(self, scrape_item: ScrapeItem) -> None:
        api_url = API_ENTRYPOINT / "file" / scrape_item.url.parts[-1]
        text = await self.request_text(api_url)

        for line in text.splitlines():
            link = self.parse_url(line)
            new_scrape_item = scrape_item.create_child(link)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()

    async def filesystem(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        og_props = open_graph.parse(soup)
        filename = og_props.title
        link_str: str | None = None
        if "video" in og_props.type:
            link_str = og_props.video
        elif "image" in og_props.type:
            link_str = og_props.image

        if not link_str or "filesystem" not in link_str:
            raise ScrapeError(422)

        js_text = css.select_one_get_text(soup, JS_SELECTOR)
        json_str = get_text_between(js_text, "window.initial_node =", "window.user = ").removesuffix(";")
        json_data = json.loads(json_str)
        log_debug(json_data)
        scrape_item.possible_datetime = self.parse_iso_date(json_data["path"][0]["created"])
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)

    def create_download_link(self, file_id: str) -> AbsoluteHttpURL:
        """Creates a download link for a file."""
        return API_ENTRYPOINT.joinpath("file", file_id).with_query("download")
