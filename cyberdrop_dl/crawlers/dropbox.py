from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, type_adapter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_PRIMARY_URL = AbsoluteHttpURL("https://www.dropbox.com")
_FOLDERS_API_ENDPOINT = _PRIMARY_URL / "list_shared_link_folder_entries"


@dataclasses.dataclass(slots=True)
class Node:
    is_dir: bool
    href: str
    filename: str
    secureHash: str = ""  # noqa: N815


_parse_node = type_adapter(Node)


class DropboxCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/s/...",
            "/scl/fi/<link_key>?rlkey=...",
            "/scl/fo/<link_key>/<secure_hash>?preview=<filename>&rlkey=...",
        ),
        "Folder": (
            "/sh/...",
            "/scl/fo/<link_key>/<secure_hash>?rlkey=...",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "dropbox"

    async def async_startup(self) -> None:
        await self._get_web_token(self.PRIMARY_URL)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["s" | "sh", _, *_]:
                return await self.follow_redirect(scrape_item)
            case ["scl", "fi", _, *_]:
                return await self.file(scrape_item)
            case ["scl", "fo", link_key, secure_hash]:
                return await self.folder(scrape_item, link_key, secure_hash)
            case ["scl", "fo", link_key, secure_hash, _]:
                return await self.file(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def follow_redirect(self, scrape_item: ScrapeItem) -> None:
        async with self.request(scrape_item.url) as resp:
            if "s" in resp.url.parts or "sh" in resp.url.parts:
                if "error_pages/no_access" in await resp.text():
                    raise ScrapeError(401)
                raise ScrapeError(422, "Infinite redirect")
        scrape_item.url = resp.url
        await self.fetch(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, link_key: str, secure_hash: str) -> None:
        scrape_item.url = await self._ensure_rlkey(scrape_item.url)
        rlkey = scrape_item.url.query["rlkey"]
        scrape_item.setup_as_album("")
        await self._walk_folder(scrape_item, link_key, secure_hash, rlkey)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = await self._ensure_rlkey(scrape_item.url)
        async with self.request(scrape_item.url.update_query(dl=1)) as resp:
            self._file(scrape_item, resp.filename)

    def _file(self, scrape_item: ScrapeItem, filename: str) -> None:
        scrape_item.url = view_url = scrape_item.url.with_query(rlkey=scrape_item.url.query["rlkey"], dl=0)
        download_url = view_url.update_query(dl=1)
        custom_filename, ext = self.get_filename_and_ext(filename)
        self.create_task(
            self.handle_file(
                view_url,
                scrape_item,
                filename,
                ext,
                debrid_link=download_url,
                custom_filename=custom_filename,
            )
        )

    async def _ensure_rlkey(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if url.query.get("rlkey"):
            return url
        async with self.request(url) as resp:
            url = resp.url
        if url.query.get("rlkey"):
            return url
        raise ScrapeError(401)

    async def _walk_folder(
        self,
        scrape_item: ScrapeItem,
        link_key: str,
        secure_hash: str,
        rlkey: str,
        subpath: str = "",
    ) -> None:
        async for resp in self._web_api_pager(link_key, secure_hash, rlkey, subpath):
            if "folder" not in resp:
                return await self.file(scrape_item)
            folder_name: str = resp["folder"]["filename"]
            scrape_item.add_to_parent_title(self.create_title(folder_name))

            for entry, token in zip(resp["entries"], resp["share_tokens"], strict=True):
                node = _parse_node(token | entry)
                view_url = self.parse_url(node.href)
                new_scrape_item = scrape_item.create_child(view_url)
                if node.is_dir:
                    self.create_task(
                        self._walk_folder(
                            new_scrape_item,
                            link_key,
                            node.secureHash,
                            rlkey,
                            f"{subpath}/{node.filename}",
                        )
                    )
                    continue

                self._file(new_scrape_item, node.filename)
                scrape_item.add_children()

    async def _web_api_pager(
        self, link_key: str, secure_hash: str, rlkey: str, subpath: str = ""
    ) -> AsyncGenerator[dict[str, Any]]:
        payload = {
            "is_xhr": "true",
            "t": self._token,
            "sub_path": subpath,
            "link_key": link_key,
            "secure_hash": secure_hash,
            "rlkey": rlkey,
            "link_type": "s",
        }
        while True:
            resp: dict[str, Any] = await self.request_json(
                _FOLDERS_API_ENDPOINT,
                method="POST",
                data=payload,
                headers={
                    "Origin": str(self.PRIMARY_URL),
                },
            )

            yield resp
            if not resp["has_more_entries"]:
                break
            payload["voucher"] = resp["next_request_voucher"]

    @error_handling_wrapper
    async def _get_web_token(self, *_):
        async with self.request(self.PRIMARY_URL, method="HEAD", cache_disabled=True):
            token = self.get_cookie_value("t")
            if not token:
                self.disabled = True
                msg = "Unable to get token from dropbox. Crawler has been disabled"
                raise LoginError(msg)
            self._token = token
