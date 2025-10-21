from __future__ import annotations

import json
import mimetypes
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://pixeldrain.com")
_JS_SELECTOR = 'script:-soup-contains("window.initial_node")'
_BYPASS_HOSTS = "pd.cybar.xyz", "pd.1drv.eu.org"


class File(BaseModel):
    id: str
    name: str
    size: int
    date_upload: str
    mime_type: str
    hash_sha256: str


class List(BaseModel):
    id: str
    title: str
    files: list[File]


class PixelDrainCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "pixeldrain.net", "pixeldra.in", *_BYPASS_HOSTS
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/u/<file_id>",
            "/api/file/<file_id>",
        ),
        "List": (
            "/l/<list_id>",
            "/api/list/<list_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "pixeldrain"
    FOLDER_DOMAIN: ClassVar[str] = "PixelDrain"
    _RATE_LIMIT: ClassVar[tuple[float, float]] = 10, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2

    def __post_init__(self) -> None:
        self.api = PixelDrainAPI(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["u", file_id]:
                return await self.file(scrape_item, file_id)
            case ["l", folder_id]:
                return await self.folder(scrape_item, folder_id)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        endpoints = {"file": "u", "list": "l"}
        match url.parts[1:]:
            case ["api", type_, id_] if type_ in endpoints:
                return url.origin() / endpoints[type_] / id_

        return url

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, list_id: str) -> None:
        origin = scrape_item.url.origin()
        folder = await self.api.list(list_id, origin)
        title = self.create_title(folder.title, list_id)
        scrape_item.setup_as_album(title, album_id=list_id)

        results = await self.get_album_results(list_id)
        for file in folder.files:
            api_url = origin / "api/file" / file.id
            if self.check_album_results(api_url, results):
                continue

            url = origin / "u" / file.id
            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self._file_task(new_scrape_item, file))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        debrid_link = None
        if scrape_item.url.host in _BYPASS_HOSTS:
            debrid_link = scrape_item.url
            scrape_item.url = _PRIMARY_URL / "u" / file_id

        if await self.check_complete_from_referer(scrape_item):
            return

        file: File = await self.api.file_info(file_id, scrape_item.url.origin())
        await self._file(scrape_item, file, debrid_link)

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File, debrid_link: AbsoluteHttpURL | None = None) -> None:
        link = (scrape_item.url.origin() / "api/file" / file.id).with_query("download")
        scrape_item.possible_datetime = self.parse_iso_date(file.date_upload)
        if "text/plain" in file.mime_type:
            return await self._text(scrape_item, file)

        try:
            filename, ext = self.get_filename_and_ext(file.name)
        except NoExtensionError:
            ext = mimetypes.guess_extension(file.mime_type)
            if not ext:
                raise

            filename, ext = self.get_filename_and_ext(f"{file.name}{ext}")

        await self.handle_file(link, scrape_item, file.name, ext, debrid_link=debrid_link, custom_filename=filename)

    _file_task = auto_task_id(_file)

    async def _text(self, scrape_item: ScrapeItem, file: File) -> None:
        scrape_item.setup_as_album(self.create_title(file.name, file.id))
        text = await self.api.request_text(file.id)

        for line in text.splitlines():
            try:
                link = self.parse_url(line)
            except Exception:
                continue
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

        js_text = css.select_one_get_text(soup, _JS_SELECTOR)
        json_str = get_text_between(js_text, "window.initial_node =", "window.user = ").removesuffix(";")
        json_data = json.loads(json_str)
        scrape_item.possible_datetime = self.parse_iso_date(json_data["path"][0]["created"])
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)


class PixelDrainAPI:
    def __init__(self, crawler: Crawler) -> None:
        self._crawler = crawler

    async def request_text(self, file_id: str, origin: AbsoluteHttpURL = _PRIMARY_URL) -> str:
        api_url = origin / "api/file" / file_id
        return await self._crawler.request_text(api_url)

    async def file_info(self, file_id: str, origin: AbsoluteHttpURL = _PRIMARY_URL) -> File:
        api_url = origin / "api/file" / file_id
        content = await self._crawler.request_text(api_url / "info")
        return File.model_validate_json(content)

    async def list(self, list_id: str, origin: AbsoluteHttpURL = _PRIMARY_URL) -> List:
        api_url = origin / "api/list" / list_id
        content = await self._crawler.request_text(api_url)
        return List.model_validate_json(content)
