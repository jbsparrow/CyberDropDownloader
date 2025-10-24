from __future__ import annotations

import dataclasses
from typing import ClassVar, Literal

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import DownloadError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, type_adapter

_APP_URL = AbsoluteHttpURL("https://app.koofr.net")
_PRIMARY_URL = AbsoluteHttpURL("https://koofr.eu")
_SHORT_LINK_CDN = AbsoluteHttpURL("https://k00.fr")


@dataclasses.dataclass(slots=True)
class Node:
    name: str
    type: Literal["file", "dir"]
    modified: int
    size: int
    contentType: str  # noqa: N815
    hash: str  # md5


@dataclasses.dataclass(slots=True)
class Folder:
    id: str
    name: str
    isOnline: bool  # noqa: N815
    file: Node
    path: str = ""
    children: list[Node] = dataclasses.field(default_factory=list)


_parse_folder = type_adapter(Folder)
_parse_node = type_adapter(Node)


class KooFrCrawler(Crawler):
    SUPPORTED_DOMAIN = "koofr.net", "koofr.eu", _SHORT_LINK_CDN.host
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/links/<content_id>",
            f"{_SHORT_LINK_CDN}/<short_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "koofr"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.host == _SHORT_LINK_CDN.host:
            return await self.follow_redirect(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["links", content_id]:
                return await self.content(scrape_item, content_id)
            case _:
                raise ValueError

    async def _get_redirect_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        async with self.request(url) as resp:
            if password := url.query.get("password"):
                return resp.url.update_query(password=password)
            return resp.url

    async def _request_folder_info(self, content_id: str, path: str, password: str | None) -> Folder:
        api_url = (_APP_URL / "api/v2/public/links" / content_id).with_query(path=path, password=password or "")
        try:
            resp = await self.request_json(api_url)
        except DownloadError as e:
            if e.status == 401:
                msg = "Incorrect password" if password else None
                raise PasswordProtectedError(msg) from e
            raise

        folder = _parse_folder(resp)
        if not folder.isOnline:
            raise ScrapeError(404)

        if folder.file.type == "dir":
            api_url = (api_url / "bundle").with_query(api_url.query)
            nodes = (await self.request_json(api_url))["files"]
            folder.children = [_parse_node(node) for node in nodes]
        folder.path = path
        return folder

    @error_handling_wrapper
    async def content(self, scrape_item: ScrapeItem, content_id: str) -> None:
        password = scrape_item.url.query.get("password", "")
        root_path = scrape_item.url.query.get("path", "/")
        scrape_item.url = scrape_item.url.update_query(path=root_path)

        def new_item(path: str) -> ScrapeItem:
            content_url = scrape_item.url.update_query(path=path)
            return scrape_item.create_child(content_url)

        async def get_folder(path: str) -> Folder:
            return await self._request_folder_info(content_id, path, password)

        def walk_folder(folder: Folder) -> None:
            for node in folder.children:
                if node.type == "dir":
                    new_path = f"{folder.path}/{node.name}"
                    self.create_task(walk_task(new_path))
                else:
                    self.create_task(self._file(new_item(folder.path), node))
                scrape_item.add_children()

        async def walk_task(path: str) -> None:
            try:
                subfolder = await get_folder(path)
                scrape_item.add_children(0)
            except Exception as e:
                self.raise_exc(new_item(path), e)
            else:
                walk_folder(subfolder)

        root_folder = await get_folder(root_path)
        if not root_folder.children:
            return await self._file(scrape_item, root_folder.file)

        title = self.create_title(root_folder.file.name, content_id)
        scrape_item.setup_as_album(title, album_id=content_id)
        walk_folder(root_folder)

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: Node) -> None:
        content_id = scrape_item.url.name
        link = (_APP_URL / "content/links" / content_id / "files/get" / file.name).with_query(scrape_item.url.query)

        if await self.check_complete_by_hash(link, "md5", file.hash):
            return

        if path := scrape_item.url.query["path"].removeprefix("/"):
            for part in path.split("/"):
                scrape_item.add_to_parent_title(part)

        filename, ext = self.get_filename_and_ext(file.name)
        scrape_item.possible_datetime = file.modified
        await self.handle_file(link, scrape_item, file.name, ext, custom_filename=filename)
