"""https://docs.pcloud.com"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from pydantic import TypeAdapter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.dates import parse_http_date
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_EU_API_URL = AbsoluteHttpURL("https://eapi.pcloud.com")
_US_API_URL = AbsoluteHttpURL("https://api.pcloud.com")
_EU_PUBLIC_URL = AbsoluteHttpURL("https://e.pcloud.link/publink/show")
_US_PUBLIC_URL = AbsoluteHttpURL("https://u.pcloud.link/publink/show")


@dataclasses.dataclass(frozen=True, slots=True)
class Node:
    name: str
    modified: str
    id: str
    isfolder: bool

    folderid: int | None = None
    fileid: int | None = None
    contenttype: str = ""
    contents: list[Node] = dataclasses.field(default_factory=list)

    @property
    def _id(self) -> str:
        if self.isfolder:
            id_ = self.folderid
        else:
            id_ = self.fileid
        assert id_ is not None
        return str(id_)


class File(Node):
    isfolder: Literal[False]


_parse_node_resp = TypeAdapter(Node).validate_python


class PCloudCrawler(Crawler):
    SUPPORTED_DOMAINS: SupportedDomains = "e.pc.cd", "pc.cd", "pcloud"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public File or folder": (
            "?code=<share_code>",
            "e.pc.cd/<short_code>",
            "u.pc.cd/<short_code>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.pcloud.com")
    DOMAIN: ClassVar[str] = "pcloud"
    FOLDER_DOMAIN: ClassVar[str] = "pCloud"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "pc.cd" in scrape_item.url.host:
            return await self.public_link(scrape_item, scrape_item.url.parts[1])
        if code := scrape_item.url.query.get("code"):
            return await self.public_link(scrape_item, code)
        raise ValueError

    @error_handling_wrapper
    async def public_link(self, scrape_item: ScrapeItem, code: str) -> None:
        # https://docs.pcloud.com/methods/public_links/showpublink.html
        if "e." in scrape_item.url.host:
            api_base = _EU_API_URL
            canonical_url = _EU_PUBLIC_URL
        else:
            api_base = _US_API_URL
            canonical_url = _US_PUBLIC_URL

        api_url = (api_base / "showpublink").with_query(code=code)
        node = _parse_node_resp((await self._api_request(api_url))["metadata"])
        scrape_item.url = canonical_url.with_query(code=code)
        if node.isfolder:
            scrape_item.setup_as_album(self.create_title(node.name, node.id))
            self._iter_nodes(scrape_item, node.contents)
            return

        return await self.file(scrape_item, cast("File", node))

    def _iter_nodes(self, scrape_item: ScrapeItem, nodes: Sequence[Node], *parents: str) -> None:
        folders: list[Node] = []

        for node in nodes:
            if node.isfolder:
                folders.append(node)
                continue

            file = cast("File", node)
            url = scrape_item.url.update_query(file_id=file._id)
            new_scrape_item = scrape_item.create_child(url)
            for parent in parents:
                new_scrape_item.add_to_parent_title(parent)
            self.create_task(self._file_task(new_scrape_item, file))
            scrape_item.add_children()

        for folder in folders:
            self._iter_nodes(scrape_item, folder.contents, *parents, folder.name)

    async def file(self, scrape_item: ScrapeItem, file: File) -> None:
        # https://docs.pcloud.com/methods/public_links/getpublinkdownload.html

        link = await self._request_download_url(scrape_item, file)
        # https://docs.pcloud.com/structures/datetime.html
        scrape_item.possible_datetime = parse_http_date(file.modified)
        filename, ext = self.get_filename_and_ext(file.name)
        # Adding the code as query just for logging messages. It will be discarded in the actual db
        db_url = (scrape_item.url.origin() / "file" / file._id).with_query(code=scrape_item.url.query["code"])
        await self.handle_file(db_url, scrape_item, file.name, ext, debrid_link=link, custom_filename=filename)

    _file_task = auto_task_id(file)

    async def _request_download_url(self, scrape_item: ScrapeItem, file: File) -> AbsoluteHttpURL:
        path = "getmediatranscodepublink" if "video" in file.contenttype else "getpublinkdownload"
        base = _EU_API_URL if "e." in scrape_item.url.host else _US_API_URL
        api_url = (base / path).with_query(
            code=scrape_item.url.query["code"],
            forcedownload=1,
            fileid=file._id,
        )
        resp: dict[str, Any] = await self._api_request(api_url)
        if variants := resp.get("variants"):
            resp = next(v for v in variants if v["transcodetype"] == "original")

        return self.parse_url(f"https://{resp['hosts'][0]}{resp['path']}")

    async def _api_request(self, api_url: AbsoluteHttpURL) -> dict[str, Any]:
        resp: dict[str, Any] = await self.request_json(api_url)
        if (code := resp["result"]) != 0:
            http_code, msg = _ERROR_CODES.get(code, (422, resp["error"]))
            raise ScrapeError(http_code, f"({code}) {msg}")
        return resp


_ERROR_CODES = {
    1000: (401, "Log in required"),
    1004: (422, "No fileid or path provided"),
    1005: (422, "Unknown content-type requested"),
    1028: (422, "Please provide link 'code'"),
    1029: (422, "Please provide 'fileid'"),
    2000: (401, "Log in failed"),
    2002: (422, "A component of parent directory does not exist"),
    2003: (403, "Access denied. You do not have permissions to perform this operation"),
    2009: (404, "File not found"),
    2010: (422, "Invalid path"),
    2011: (422, "Requested speed limit too low, see minspeed for minimum"),
    4000: (429, "Too many login tries from this IP address"),
    5002: (500, "Internal error, no servers available. Try again later"),
    7001: (422, "Invalid link 'code'"),
    7002: (410, "This link is deleted by the owner"),
    7004: (410, "This link has expired"),
    7005: (403, "This link has reached its traffic limit"),
    7006: (403, "This link has reached maximum downloads"),
}
