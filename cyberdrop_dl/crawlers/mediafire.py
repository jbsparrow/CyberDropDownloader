"""https://www.mediafire.com/developers/core_api"""

from __future__ import annotations

import base64
import dataclasses
import itertools
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, is_blob_or_svg, type_adapter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


@dataclasses.dataclass(slots=True, frozen=True)
class Folder:
    name: str
    has_files: bool
    has_folders: bool

    @property
    def is_empty(self) -> bool:
        return not (self.has_files or self.has_folders)


@dataclasses.dataclass(slots=True, frozen=True)
class File:
    quickkey: str
    filename: str
    created: str
    size: int
    hash: str


_PRIMARY_URL = AbsoluteHttpURL("https://www.mediafire.com/")
_API_URL = _PRIMARY_URL / "api/1.4"


class MediaFireCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/file/<quick_key>",
            "?<quick_key>",
        ),
        "Folder": "/folder/<folder_key>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "mediafire"
    SKIP_PRE_CHECK: ClassVar[bool] = True

    def __post_init__(self) -> None:
        self.api = MediaFireAPI(self)

    @classmethod
    def _json_response_check(cls, json_resp: Any) -> None:
        if not isinstance(json_resp, dict) or "response" not in json_resp:
            return
        resp: dict[str, Any] = json_resp["response"]
        if resp["result"] != "Success":
            code: int = resp["error"]
            ui_failure = f"MediaFire Error ({code})"
            raise ScrapeError(ui_failure, resp["message"])

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if (
            scrape_item.url.path == "/"
            and (quick_key := scrape_item.url.query_string)
            and not ("&" in quick_key or "=" in quick_key)
        ):
            return await self.file(scrape_item, quick_key)

        match scrape_item.url.parts[1:]:
            case ["folder", folder_key, *_]:
                return await self.folder(scrape_item, folder_key)
            case ["file", quick_key, *_]:
                return await self.file(scrape_item, quick_key)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_key: str) -> None:
        folder = await self.api.folder_info(folder_key)
        title = self.create_title(folder.name, folder_key)
        scrape_item.setup_as_album(title, album_id=folder_key)

        if folder.is_empty:
            # Make a request anyway to try to get a descriptive error from MediaFire
            async for _ in self.api.folder_content(folder_key, "folders"):
                break
            raise ScrapeError(204, "Folder is empty")

        if folder.has_files:
            async for files in self.api.folder_content(folder_key, "files"):
                for file in files:
                    file_ = self.api.parse_file(file)
                    url = _PRIMARY_URL / "file" / file_.quickkey
                    new_scrape_item = scrape_item.create_child(url)
                    self.create_task(self._file_task(new_scrape_item, file_))
                    scrape_item.add_children()

        if folder.has_folders:
            async for folders in self.api.folder_content(folder_key, "folders"):
                for folder in folders:
                    link = self.PRIMARY_URL / "folder" / folder["folderkey"]
                    new_scrape_item = scrape_item.create_child(link)
                    self.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, quick_key: str) -> None:
        canonical_url = self.PRIMARY_URL / "file" / quick_key
        if await self.check_complete_from_referer(canonical_url):
            return
        file = await self.api.file_info(quick_key)
        scrape_item.url = canonical_url
        await self._file(scrape_item, file, check_referer=False)

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File, *, check_referer: bool = True) -> None:
        if check_referer and await self.check_complete_from_referer(scrape_item):
            return

        hash_algo = "sha256" if len(file.hash) == 64 else "md5"
        if await self.check_complete_by_hash(scrape_item, hash_algo, file.hash):
            return

        soup = await self.request_soup(scrape_item.url, impersonate=True)
        scrape_item.possible_datetime = self.parse_iso_date(file.created)
        link = self.parse_url(_extract_download_link(soup))
        filename, ext = self.get_filename_and_ext(file.filename)
        await self.handle_file(link, scrape_item, file.filename, ext, custom_filename=filename)

    _file_task = auto_task_id(_file)


class MediaFireAPI:
    def __init__(self, crawler: Crawler) -> None:
        self._crawler = crawler
        self.parse_file = type_adapter(File)

    async def _api_request(self, path: str, **params: int | str) -> dict[str, Any]:
        assert params
        params["response_format"] = "json"
        api_url = (_API_URL / path).with_query(params)
        return (await self._crawler.request_json(api_url))["response"]

    async def folder_content(
        self, folder_key: str, content_type: Literal["files", "folders"]
    ) -> AsyncGenerator[list[dict[str, Any]]]:
        for chunk in itertools.count(1):
            content = (
                await self._api_request(
                    "folder/get_content.php",
                    folder_key=folder_key,
                    content_type=content_type,
                    chunk=chunk,
                    chunk_size=1000,
                    filter="public",
                )
            )["folder_content"]
            yield content[content_type]
            if content["more_chunks"] != "yes":
                break

    async def folder_info(self, folder_key: str) -> Folder:
        resp: dict[str, Any] = (
            await self._api_request(
                "folder/get_info.php",
                folder_key=folder_key,
            )
        )["folder_info"]

        return Folder(
            name=resp["name"],
            has_files=bool(int(resp["file_count"])),
            has_folders=bool(
                int(resp["folder_count"]),
            ),
        )

    async def file_info(self, quick_key: str) -> File:
        resp: dict[str, Any] = (
            await self._api_request(
                "file/get_info.php",
                quick_key=quick_key,
            )
        )["file_info"]
        return self.parse_file(resp)


def _extract_download_link(soup: BeautifulSoup) -> str:
    download_button = soup.select_one("a#downloadButton")
    if not download_button:
        if "Something appears to be missing" in soup.get_text():
            raise ScrapeError(410)
        raise ScrapeError(422)

    if encoded_url := css.get_attr_or_none(download_button, "data-scrambled-url"):
        return base64.b64decode(encoded_url).decode()

    url = css.get_attr(download_button, "href")
    if is_blob_or_svg(url):
        raise ScrapeError(422)
    return url
