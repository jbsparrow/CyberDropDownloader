from __future__ import annotations

import hashlib
import itertools
import time
from typing import TYPE_CHECKING, Any, ClassVar, Literal, NotRequired, TypedDict, TypeGuard

from typing_extensions import ReadOnly

from cyberdrop_dl import aio, env
from cyberdrop_dl.cache import disk_cached_method
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.exceptions import PasswordProtectedError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem, ScrapeItemType
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable


@HTTPConfig(rate_limit=(4, 10))
class GoFileCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Folder / File": "/d/<content_id>",
        "Direct link": (
            "/download/<content_id>/<filename>",
            "/download/web/<content_id>/<filename>",
        ),
        "Direct link (Premium)": ("/download/direct/<content_id>/<filename>",),
        "**NOTE**": (
            "Use `password` as a query param to download password protected folders",
            "ex: https://gofile.io/d/ABC654?password=1234",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://gofile.io")
    DOMAIN: ClassVar[str] = "gofile"
    FOLDER_DOMAIN: ClassVar[str] = "GoFile"

    def __post_init__(self) -> None:
        self.api: GoFileAPI = GoFileAPI.from_crawler(self)

    def __json_resp_check__(self, resp: dict[str, Any], _=None) -> None:
        self.api.check_resp(resp)

    async def __async_post_init__(self) -> None:
        with self.catch_errors(self.api.ENTRYPOINT), self.disable_on_error("Unable create temp account"):
            self.api.key = self.config.auth.gofile.api_key or await self.api.create_temp_account()
            self.update_cookies({"accountToken": self.api.key})

    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return super()._prepare_headers(scrape_item) | {"Authorization": f"Bearer {self.api.key}"}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["d", content_id]:
                await self.folder(scrape_item, content_id)
            case ["download", "direct", file_id, _]:
                await self.direct_file(scrape_item)
            case ["download", "web", file_id, _] | ["download", file_id, _]:
                await self.single_file(scrape_item, file_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def single_file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        url = await self.request_redirect(scrape_item.url)
        scrape_item.url = url.with_fragment(file_id)
        assert "d" in url.parts
        return await self.folder(scrape_item, url.name, file_id)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, content_id: str, selected_node_id: str | None = None) -> None:
        first_node, pages = await aio.peek_first(self.api.content(content_id, scrape_item.password))
        if _has_single_not_nested_file(scrape_item, first_node):
            title = ""
            part_of_album = False
        else:
            title = self.create_title(
                name := first_node["name"],
                content_id,
                force_album_id=name.casefold() == "root",
            )
            part_of_album = True

        scrape_item.setup_as_album(title, album_id=content_id)
        scrape_item.part_of_album = part_of_album
        scrape_item.url = scrape_item.url.with_query(None)

        async for node in pages:
            nodes = {node["id"]: node} if node["type"] == "file" else node["children"]

            if selected_node_id:
                target_node = nodes.get(selected_node_id)
                if not target_node:
                    continue

                self._iter_nodes(scrape_item, [target_node])
                return

            self._iter_nodes(scrape_item, nodes.values())

    def _iter_nodes(self, scrape_item: ScrapeItem, nodes: Iterable[Node]) -> None:
        def web_url(node: Node) -> AbsoluteHttpURL:
            node_id = node["id"]
            if node["type"] == "folder":
                return self.PRIMARY_URL / "d" / (node.get("code") or node_id)
            return scrape_item.url.with_fragment(node_id)

        for node in nodes:
            new_scrape_item = scrape_item.create_new(web_url(node), add_parent=True)
            self._handle_node(new_scrape_item, node)
            scrape_item.add_children()

    @error_handling_wrapper
    def _handle_node(self, scrape_item: ScrapeItem, node: Node) -> None:
        if not _check_node_is_accessible(node):
            return

        if node["type"] == "folder":
            self.create_task(self.run(scrape_item))
            return

        self.create_eager_task(self._file(scrape_item, node))

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File) -> None:
        link_str: str = file["link"]
        if (not link_str or link_str == "overloaded") and "directLink" in file:
            link_str = file["directLink"]

        assert link_str
        link = self.parse_url(link_str)

        if await self.check_complete_by_hash(link, "md5", file["md5"]):
            return

        if file.get("isFrozen"):
            self.log.warning(f"{link} is marked as frozen, download may fail")

        filename, ext = self.get_filename_and_ext(file["name"], mime_type=file.get("mimetype"))
        scrape_item.uploaded_at = file["createTime"]
        await self.handle_file(
            link,
            scrape_item,
            file["name"],
            ext,
            custom_filename=filename,
            metadata=file,
            thumbnail=self.parse_url(thumb) if (thumb := file.get("thumbnail")) else None,
        )


class Node(TypedDict):
    canAccess: ReadOnly[bool]
    id: str
    type: ReadOnly[Literal["folder", "file"]]
    name: str
    createTime: int


class File(Node):
    type: Literal["file"]
    link: str
    directLink: NotRequired[str]
    isFrozen: NotRequired[bool]  # Only present in files uploaded by free accounts and older than 30 days
    viruses: NotRequired[bool]
    md5: str


class Folder(Node):
    type: Literal["folder"]
    code: str
    childrenCount: int
    children: dict[str, Node]
    password: NotRequired[str]
    passwordStatus: NotRequired[str]


class GoFileAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.gofile.io")
    BROWSER_LANG: ClassVar[str] = "en-US"
    SALT: ClassVar[str] = env.GOFILE_SALT or "12af056dacea0b"
    key: str = ""

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": (ua := self.config.network.user_agent),
            "Origin": "https://gofile.io",
            "Referer": "https://gofile.io/",
            "Priority": "u=0",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        if self.key:
            headers |= {
                "Authorization": f"Bearer {self.key}",
                "X-BL": self.BROWSER_LANG,
                "X-Website-Token": _create_web_token(
                    ua,
                    self.BROWSER_LANG,
                    self.key,
                    self.SALT,
                ),
            }

        return headers

    @disk_cached_method(key="account_token", ttl=86400)
    async def create_temp_account(self) -> str:
        self.log.info("Creating temp account")
        api_url = self.ENTRYPOINT / "accounts"
        resp = await self.request_json(api_url, method="POST", data={}, headers=self.headers)
        if resp["status"] != "ok":
            raise ScrapeError(401, "Couldn't generate GoFile temp account", origin=api_url)

        return resp["data"]["token"]

    def check_resp(self, resp: dict[str, Any]) -> None:
        status = resp.get("status", "")
        if "notFound" in status:
            raise ScrapeError(404)
        if "wrongToken" in status:
            self.create_temp_account.clear()
            msg = "Invalid API key" if self.config.auth.gofile.api_key else "token expired, please retry"
            raise ScrapeError(401, msg)

    def content(self, content_id: str, password: str | None = None) -> AsyncGenerator[Folder | File]:
        url = (self.ENTRYPOINT / "contents" / content_id).with_query(
            sortField="createTime",
            sortDirection=1,
            pageSize=100,
        )

        if password:
            url = url.update_query(password=hashlib.sha256(password.encode(), usedforsecurity=False).hexdigest())

        return self.pager(url)

    async def pager(self, url: AbsoluteHttpURL) -> AsyncGenerator[Folder | File]:
        for page in itertools.count(1):
            resp = await self.request_json(url.update_query(page=page), headers=self.headers)
            self.check_resp(resp)
            node = resp["data"]
            _check_node_is_accessible(node)
            yield node
            if not resp["metadata"].get("hasNextPage"):
                break


def _check_node_is_accessible(node: Node) -> TypeGuard[File | Folder]:
    if (type_ := node["type"]) not in {"file", "folder"}:
        raise ScrapeError(f"Unknown node type: {type_}")

    if node.get("viruses"):
        raise ScrapeError("Dangerous File")

    if node["canAccess"]:
        return True

    if node.get("password"):
        status = node.get("passwordStatus", "")
        error_msg = {
            "passwordRequired": "Folder is password protected",
            "passwordWrong": "Wrong folder password",
        }.get(status)
        raise PasswordProtectedError(error_msg)

    raise ScrapeError(403, "Folder is private")


def _has_single_not_nested_file(scrape_item: ScrapeItem, node: Folder | File) -> bool:
    return node["type"] == "file" or (
        node["childrenCount"] == 1 and node["name"] == node["code"] and scrape_item.type != ScrapeItemType.ALBUM
    )


def _create_web_token(user_agent: str, brower_lang: str, api_key: str, salt: str) -> str:
    # https://gofile.io/dist/js/wt.obf.js
    token = f"{user_agent}::{brower_lang}::{api_key}::{int(time.time() // 14400)}::{salt}"
    return hashlib.sha256(token.encode()).hexdigest()
