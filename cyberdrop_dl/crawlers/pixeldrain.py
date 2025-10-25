"""https://pixeldrain.com/api"""

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
_PIXELDRAIN_PROXY = AbsoluteHttpURL(env.PIXELDRAIN_PROXY) if env.PIXELDRAIN_PROXY else None


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
            "/l/<list_id>#item=<file_index>",
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
        "**NOTE**": "text files will not be downloaded but their content will be parsed for URLs",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "pixeldrain"
    FOLDER_DOMAIN: ClassVar[str] = "PixelDrain"
    _RATE_LIMIT: ClassVar[RateLimit] = 10, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2

    def __post_init__(self) -> None:
        self._headers: dict[str, str] = {}
        if api_key := self.manager.auth_config.pixeldrain.api_key:
            self._headers["Authorization"] = self.manager.client_manager.basic_auth(
                "Cyberdrop-DL",
                api_key,
            )

    @classmethod
    def _json_response_check(cls, json_resp: dict) -> None:
        # TODO: pass the resp obj to the json check functions
        return
        if not json_resp["success"]:
            msg = f"{json_resp['message']} ({json_resp['value']})"
            raise ValueError(422, msg)

    async def _api_request(self, api_url: AbsoluteHttpURL) -> str:
        return await self.request_text(api_url, headers=self._headers)

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
        match url.parts[1:]:
            case ["api", "file", id_]:
                return url.origin() / "u" / id_
            case ["api", "list", id_]:
                return url.origin() / "l" / id_
            case ["api", "filesystem", *rest] if rest:
                return (url.origin() / "d").joinpath(*rest)
            case _:
                return url

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, list_id: str) -> None:
        origin = scrape_item.url.origin()
        api_url = origin / "api/list" / list_id
        folder = Folder.model_validate_json(await self._api_request(api_url))
        title = self.create_title(folder.title, list_id)
        scrape_item.setup_as_album(title, album_id=list_id)

        files = folder.files
        if scrape_item.url.fragment.startswith(prefix := "item="):
            try:
                item_idx = int(scrape_item.url.fragment.removeprefix(prefix))
                files = [files[item_idx]]
            except (ValueError, IndexError):
                msg = f"Unable to parse item index in folder {scrape_item.url}. Falling back to downloading the entire folder"
                self.log(msg, 30)

        results = await self.get_album_results(list_id)
        for file in files:
            if self.check_album_results(file.download_url, results):
                continue

            url = origin / "u" / file.id
            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self._file_task(new_scrape_item, file))
            scrape_item.add_children()

    @error_handling_wrapper
    async def filesystem(self, scrape_item: ScrapeItem, path: str) -> None:
        # https://github.com/Fornaxian/pixeldrain_web/blob/8e5ecfc5ce44c0b2b4fafdf9e8201dfc98395e88/svelte/src/filesystem/FilesystemAPI.ts

        origin = scrape_item.url.origin()

        async def request_fs(path: str) -> FileSystem:
            api_url = (origin / "api/filesystem" / path).with_query("stat")
            content = await self._api_request(api_url)
            return FileSystem.model_validate_json(content)

        fs = await request_fs(path)
        base_node = fs.path[fs.base_index]
        root = fs.path[0]
        title = self.create_title(root.name, root.id)
        scrape_item.setup_as_album(title, album_id=root.id)

        if base_node.type == "file":
            fs.children = [base_node]

        results = await self.get_album_results(root.id)

        async def walk_task(new_scrape_item: ScrapeItem, path: str) -> None:
            try:
                fs = await request_fs(path)
                scrape_item.add_children(0)
                await walk_filesystem(fs)
            except Exception as e:
                self.raise_exc(new_scrape_item, e)

        async def walk_filesystem(fs: FileSystem) -> None:
            for node in fs.children:
                if node.name == ".search_index.gz":
                    continue

                url = origin / "d" / node.path.removeprefix("/")
                new_scrape_item = scrape_item.create_child(url)

                if node.type == "file":
                    if self.check_album_results(node.download_url, results):
                        continue

                    for part in node.path.split("/")[2:-1]:
                        new_scrape_item.add_to_parent_title(part)

                    self.create_task(self._file_task(new_scrape_item, node))

                elif node.type == "dir":
                    self.create_task(walk_task(new_scrape_item, node.path))

                else:
                    self.raise_exc(new_scrape_item, f"Unknown node type: {node.type}")

                scrape_item.add_children()

        await walk_filesystem(fs)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        debrid_link = None
        if scrape_item.url.host in _BYPASS_HOSTS:
            debrid_link = scrape_item.url
            scrape_item.url = _PRIMARY_URL / "u" / file_id

        elif _PIXELDRAIN_PROXY:
            debrid_link = _PIXELDRAIN_PROXY / file_id

        if await self.check_complete_from_referer(scrape_item):
            return

        api_url = scrape_item.url.origin() / "api/file" / file_id / "info"
        file = File.model_validate_json(await self._api_request(api_url))
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
        api_url = scrape_item.url.origin() / "api/file" / file.id
        text = await self._api_request(api_url)

        for line in text.splitlines():
            try:
                link = self.parse_url(line)
            except Exception:
                continue
            new_scrape_item = scrape_item.create_child(link)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()

    _file_task = auto_task_id(_file)
