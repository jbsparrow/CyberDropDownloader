from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import dataclasses

from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import DownloadError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils.errors import error_handling_wrapper

_APP_URL = AbsoluteHttpURL("https://app.koofr.net")
_PRIMARY_URL = AbsoluteHttpURL("https://koofr.eu")
_SHORT_LINK_CDN = AbsoluteHttpURL("https://k00.fr")


@dataclasses.dataclass(slots=True)
class Node:
    name: str
    type: Literal["file", "dir"]
    modified: int
    size: int
    path: str = "/"
    hash: str = ""  # md5


@Crawler.db_path_builder("path_qs_frag")
class KooFrCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "koofr.net", "koofr.eu", _SHORT_LINK_CDN.host
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public Share": (
            "/links/<content_id>",
            f"{_SHORT_LINK_CDN}/<short_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "koofr"

    def __post_init__(self) -> None:
        self.api: KooFrAPI = KooFrAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.host == _SHORT_LINK_CDN.host:
            return await self.follow_redirect(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["links", content_id]:
                return await self.share(scrape_item, content_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def share(self, scrape_item: ScrapeItem, content_id: str) -> None:
        path = scrape_item.url.query.get("path") or "/"
        root = await self.api.get_info(content_id, path, scrape_item.password)
        if root.type == "file":
            return await self._file(scrape_item, root)

        title = self.create_title(root.name, content_id)
        scrape_item.setup_as_album(title, album_id=content_id)
        await self._walk_folder(scrape_item, content_id, path)

    @error_handling_wrapper
    async def _walk_folder(self, scrape_item: ScrapeItem, content_id: str, path: str) -> None:
        children = await self.api.get_children(content_id, path, scrape_item.password)
        async with self.new_task_group() as tg:
            for node in children:
                if node.type == "file":
                    tg.create_task(self._file(scrape_item, node))
                    continue

                url = scrape_item.url.update_query(path=node.path)
                new_scrape_item = scrape_item.create_child(url)
                new_scrape_item.append_folders(node.name)
                tg.create_task(self._walk_folder(new_scrape_item, content_id, node.path))

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: Node) -> None:
        content_id = scrape_item.url.name
        link = _APP_URL / "content/links" / content_id / "files/get" / file.name
        link = link.with_query(scrape_item.url.query).update_query(path=file.path)
        if await self.check_complete_by_hash(link, "md5", file.hash):
            return

        filename, ext = self.get_filename_and_ext(file.name)
        scrape_item.uploaded_at = file.modified // 1000
        await self.handle_file(link, scrape_item, file.name, ext, custom_filename=filename)


class KooFrAPI(API):
    ENDPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://app.koofr.net/api/v2/public/links")

    async def get_info(self, content_id: str, path: str, password: str | None) -> Node:
        password = password or ""
        api_url = (self.ENDPOINT / content_id).with_query(path=path, password=password)
        try:
            resp: dict[str, Any] = await self.request_json(api_url)
        except DownloadError as e:
            if e.status == 401:
                msg = "Incorrect password" if password else None
                raise PasswordProtectedError(msg) from e
            raise

        if not resp.get("isOnline"):
            raise ScrapeError(404)

        return Node(**resp["file"])

    async def get_children(self, content_id: str, path: str, password: str | None) -> list[Node]:
        password = password or ""
        api_url = (self.ENDPOINT / content_id / "bundle").with_query(path=path, password=password)
        nodes: list[dict[str, Any]] = (await self.request_json(api_url))["files"]
        base = path.removesuffix("/")
        return [Node(path=f"{base}/{node['name']}", **node) for node in nodes]
