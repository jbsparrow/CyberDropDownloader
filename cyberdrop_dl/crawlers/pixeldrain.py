from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import BaseModel

from cyberdrop_dl import env
from cyberdrop_dl.crawlers.crawler import Crawler, RateLimit, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import NoExtensionError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://pixeldrain.com")
_BYPASS_HOSTS = "pd.cybar.xyz", "pd.1drv.eu.org"


class File(BaseModel):
    id: str
    name: str
    date_upload: str
    mime_type: str
    hash_sha256: str

    @property
    def download_url(self) -> AbsoluteHttpURL:
        return (_PRIMARY_URL / "api/file" / self.id).with_query("download")


class Folder(BaseModel):
    id: str
    title: str
    files: list[File]


class Node(BaseModel):
    id: str
    type: Literal["file", "dir"]
    path: str
    name: str
    modified: str
    sha256_sum: str
    file_type: str = ""

    @property
    def mime_type(self) -> str:
        return self.file_type

    @property
    def date_upload(self) -> str:
        return self.modified

    @property
    def hash_sha256(self) -> str:
        return self.sha256_sum

    @property
    def download_url(self) -> AbsoluteHttpURL:
        return (_PRIMARY_URL / "api/filesystem" / self.path.removeprefix("/")).with_query("attach")


class FileSystem(BaseModel):
    children: list[Node]
    base_index: int
    path: list[Node]


class PixelDrainCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "pixeldrain.net", "pixeldrain.com", "pixeldra.in", *_BYPASS_HOSTS
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/u/<file_id>",
            "/api/file/<file_id>",
        ),
        "Folder": (
            "/l/<list_id>",
            "/api/list/<list_id>",
        ),
        "Filesystem": (
            "/d/<id>",
            "/api/filesystem/<path>...",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "pixeldrain"
    FOLDER_DOMAIN: ClassVar[str] = "PixelDrain"
    _RATE_LIMIT: ClassVar[RateLimit] = 10, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2

    def __post_init__(self) -> None:
        self.api = PixelDrainAPI(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.host in _BYPASS_HOSTS:
            return await self.file(scrape_item, scrape_item.url.name)

        match scrape_item.url.parts[1:]:
            case ["u", file_id]:
                return await self.file(scrape_item, file_id)
            case ["l", folder_id]:
                return await self.folder(scrape_item, folder_id)
            case ["d", *path] if path:
                return await self.filesystem(scrape_item, "/".join(path))
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        endpoints = {"file": "u", "list": "l"}
        match url.parts[1:]:
            case ["api", type_, id_] if type_ in endpoints:
                return url.origin() / endpoints[type_] / id_
            case ["api", "filesystem", *rest] if rest:
                return (url.origin() / "d").joinpath(*rest)
            case _:
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
    async def filesystem(self, scrape_item: ScrapeItem, path: str) -> None:
        # https://github.com/Fornaxian/pixeldrain_web/blob/8e5ecfc5ce44c0b2b4fafdf9e8201dfc98395e88/svelte/src/filesystem/FilesystemAPI.ts

        origin = scrape_item.url.origin()
        fs = await self.api.filesystem(path, origin)
        base_node = fs.path[fs.base_index]
        root = fs.path[0]
        title = self.create_title(root.name, root.id)
        scrape_item.setup_as_album(title, album_id=root.id)

        if base_node.type == "file":
            files = [base_node]

        else:
            files = (n for n in fs.children if n.type == "file")

        for file in files:
            if file.name == ".search_index.gz":
                continue

            url = scrape_item.url.origin() / "d" / file.path.removeprefix("/")
            new_scrape_item = scrape_item.create_child(url)
            for part in file.path.split("/")[2:-1]:
                new_scrape_item.add_to_parent_title(part)
            self.create_task(self._file_task(new_scrape_item, file))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        debrid_link = None
        if scrape_item.url.host in _BYPASS_HOSTS:
            debrid_link = scrape_item.url
            scrape_item.url = _PRIMARY_URL / "u" / file_id

        elif env.PIXELDRAIN_PROXY:
            debrid_link = AbsoluteHttpURL(f"{env.PIXELDRAIN_PROXY}/{file_id}")

        if await self.check_complete_from_referer(scrape_item):
            return

        file = await self.api.file_info(file_id, scrape_item.url.origin())
        await self._file(scrape_item, file, debrid_link)

    @error_handling_wrapper
    async def _file(
        self, scrape_item: ScrapeItem, file: File | Node, debrid_link: AbsoluteHttpURL | None = None
    ) -> None:
        link = file.download_url.with_host(scrape_item.url.origin().host)
        if await self.check_complete_by_hash(link, "sha256", file.hash_sha256):
            return

        if "text/plain" in file.mime_type:
            return await self._text(scrape_item, file)

        try:
            filename, ext = self.get_filename_and_ext(file.name)
        except NoExtensionError:
            ext = mimetypes.guess_extension(file.mime_type)
            if not ext:
                raise

            filename, ext = self.get_filename_and_ext(f"{file.name}{ext}")

        scrape_item.possible_datetime = self.parse_iso_date(file.date_upload)
        await self.handle_file(link, scrape_item, file.name, ext, debrid_link=debrid_link, custom_filename=filename)

    @error_handling_wrapper
    async def _text(self, scrape_item: ScrapeItem, file: File | Node) -> None:
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

    _file_task = auto_task_id(_file)


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

    async def list(self, list_id: str, origin: AbsoluteHttpURL = _PRIMARY_URL) -> Folder:
        api_url = origin / "api/list" / list_id
        content = await self._crawler.request_text(api_url)
        return Folder.model_validate_json(content)

    async def filesystem(self, path: str, origin: AbsoluteHttpURL = _PRIMARY_URL) -> FileSystem:
        api_url = (origin / "api/filesystem" / path.removeprefix("/")).with_query("stat")
        content = await self._crawler.request_text(api_url)
        return FileSystem.model_validate_json(content)
