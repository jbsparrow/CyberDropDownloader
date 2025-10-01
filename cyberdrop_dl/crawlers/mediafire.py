from __future__ import annotations

import base64
import itertools
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, is_blob_or_svg

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    DOWNLOAD_BUTTON = "a[id=downloadButton]"
    DATE = "ul[class=details] li:-soup-contains(Uploaded) span"


_PRIMARY_URL = AbsoluteHttpURL("https://www.mediafire.com/")
_API_URL = _PRIMARY_URL / "api/1.4"


class FolderInfo(NamedTuple):
    name: str
    has_files: bool
    has_folders: bool


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
    SKIP_PRE_CHECK = True

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
            and (file_id := scrape_item.url.query_string)
            and not ("&" in file_id or "=" in file_id)
        ):
            return await self.file(scrape_item, file_id)

        match scrape_item.url.parts[1:]:
            case ["folder", folder_key, *_]:
                return await self.folder(scrape_item, folder_key)
            case ["file", file_id, *_]:
                return await self.file(scrape_item, file_id)
            case _:
                raise ValueError

    async def _api_request(self, path: str, **params: Any) -> dict[str, Any]:
        params["response_format"] = "json"
        api_url = (_API_URL / path).with_query(params)
        return (await self.request_json(api_url))["response"]

    async def _iter_folder_content(self, folder_key: str, content_type: str) -> AsyncGenerator[list[dict[str, Any]]]:
        async def get_content(chunk: int) -> dict[str, Any]:
            return (
                await self._api_request(
                    "folder/get_content.php",
                    folder_key=folder_key,
                    content_type=content_type,
                    chunk=chunk,
                    chunk_size=1000,
                    filter="public",
                )
            )["folder_content"]

        next_task = self.create_task(get_content(1))

        for chunk in itertools.count(2):
            if next_task is None:
                break
            content = await next_task
            if content["more_chunks"] == "yes":
                next_task = self.create_task(get_content(chunk))
            else:
                next_task = None
            yield content[content_type]

    async def _get_folder_info(self, folder_key: str) -> FolderInfo:
        resp: dict[str, Any] = (
            await self._api_request(
                "folder/get_info.php",
                recursive="yes",
                details="yes",
                folder_key=folder_key,
            )
        )["folder_info"]
        return FolderInfo(
            name=resp["name"],
            has_files=bool(resp["file_count"]),
            has_folders=bool(resp["folder_count"]),
        )

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_key: str) -> None:
        folder = await self._get_folder_info(folder_key)
        title = self.create_title(folder.name, folder_key)
        scrape_item.setup_as_album(title, album_id=folder_key)

        if folder.has_files:
            async for files in self._iter_folder_content(folder_key, "files"):
                for file in files:
                    file_id: str = file["quickkey"]
                    link = self.PRIMARY_URL / "file" / file_id
                    new_scrape_item = scrape_item.create_child(link)
                    new_scrape_item.possible_datetime = self.parse_iso_date(file["created"])
                    self.create_task(self._file_task(new_scrape_item, file_id))
                    scrape_item.add_children()

        if folder.has_folders:
            async for folders in self._iter_folder_content(folder_key, "folders"):
                for folder in folders:
                    link = self.PRIMARY_URL / "folder" / folder["folderkey"]
                    new_scrape_item = scrape_item.create_child(link)
                    self.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        canonical_url = self.PRIMARY_URL / "file" / file_id
        if await self.check_complete_from_referer(canonical_url):
            return

        soup = await self.request_soup(scrape_item.url, impersonate=True)
        if not scrape_item.possible_datetime:
            scrape_item.possible_datetime = self.parse_iso_date(
                css.select_one_get_text(soup, Selector.DATE),
            )

        scrape_item.url = canonical_url
        link = self.parse_url(_extract_download_link(soup))
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    _file_task = auto_task_id(file)


def _extract_download_link(soup: BeautifulSoup) -> str:
    link_tag = soup.select_one(Selector.DOWNLOAD_BUTTON)
    if not link_tag:
        if "Something appears to be missing" in soup.get_text():
            raise ScrapeError(410)
        raise ScrapeError(422)

    if encoded_url := css.get_attr_or_none(link_tag, "data-scrambled-url"):
        return base64.b64decode(encoded_url).decode()

    url = css.get_attr(link_tag, "href")
    if is_blob_or_svg(url):
        raise ScrapeError(422)
    return url
