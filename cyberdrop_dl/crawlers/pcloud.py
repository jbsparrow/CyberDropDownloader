"""https://docs.pcloud.com"""

from __future__ import annotations

import dataclasses
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from pydantic import TypeAdapter
from typing_extensions import TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_EU_API_URL = AbsoluteHttpURL("https://eapi.pcloud.com")
_US_API_URL = AbsoluteHttpURL("https://api.pcloud.com")
_UE_PUBLIC_URL = AbsoluteHttpURL("https://e.pcloud.link/publink/show")
_US_PUBLIC_URL = AbsoluteHttpURL("https://u.pcloud.link/publink/show")


@dataclasses.dataclass(frozen=True, slots=True)
class Node:
    name: str
    modified: str
    id: str
    isfolder: bool

    folderid: int | None = None
    fileid: int | None = None
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


class PublicLinkResponse(TypedDict):
    metadata: Node


_parse_public_link_resp = TypeAdapter(PublicLinkResponse).validate_json


class PCloudCrawler(Crawler):
    SUPPORTED_DOMAINS: SupportedDomains = "e.pc.cd", "pc.cd", "pcloud"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public File or folder": "?code=<share_code>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.pcloud.com")
    DOMAIN: ClassVar[str] = "pcloud"
    FOLDER_DOMAIN: ClassVar[str] = "pCloud"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if code := scrape_item.url.query.get("code"):
            return await self.public_link(scrape_item, code)
        raise ValueError

    @error_handling_wrapper
    async def public_link(self, scrape_item: ScrapeItem, code: str) -> None:
        # https://docs.pcloud.com/methods/public_links/showpublink.html
        if "e." in scrape_item.url.host:
            api_url = _EU_API_URL / "showpublink"
            canonical_url = _UE_PUBLIC_URL.with_query(code=code)
        else:
            api_url = _US_API_URL / "showpublink"
            canonical_url = _US_PUBLIC_URL.with_query(code=code)

        resp_text = await self.request_text(api_url.with_query(code=code))
        node = _parse_public_link_resp(resp_text)["metadata"]
        scrape_item.url = canonical_url
        if not node.isfolder:
            return await self.file(scrape_item, cast("File", node))

        scrape_item.setup_as_album(self.create_title(node.name, node.id))
        self._iter_nodes(scrape_item, node.contents)

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

        base = _EU_API_URL if "e." in scrape_item.url.host else _US_API_URL
        api_url = (base / "getpublinkdownload").with_query(
            code=scrape_item.url.query["code"],
            forcedownload=1,
            fileid=file._id,
        )
        resp: dict[str, Any] = await self.request_json(api_url)
        link = self.parse_url(f"https://{resp['hosts'][0]}{resp['path']}")
        scrape_item.possible_datetime = to_timestamp(parsedate_to_datetime(file.modified))
        filename, ext = self.get_filename_and_ext(file.name)
        db_url = scrape_item.url.origin() / "file" / file._id
        await self.handle_file(db_url, scrape_item, file.name, ext, debrid_link=link, custom_filename=filename)

    _file_task = auto_task_id(file)
