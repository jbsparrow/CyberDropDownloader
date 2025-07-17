from __future__ import annotations

import json
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class ItemType(StrEnum):
    folder = "folder"
    file = "file"


class Item(AliasModel):
    name: str
    type: str
    id: str = Field(validation_alias="itemID", coerce_numbers_to_str=True)
    typed_id: str = Field("hola", validation_alias="typedID")
    date: int | None = Field(default=None, validation_alias="contentUpdated")
    parent_id: str = Field(validation_alias="parentFolderID", coerce_numbers_to_str=True)


class SharedFolder(AliasModel):
    name: str = Field(validation_alias="currentFolderName")
    id: str = Field(validation_alias="currentFolderID", coerce_numbers_to_str=True)
    items: list[Item]


APP_DOMAIN = "app.box.com"
DOWNLOAD_URL_BASE = AbsoluteHttpURL("https://app.box.com/index.php?rm=box_download_shared_file")
JS_SELECTOR = "script:contains('Box.postStreamData')"

PRIMARY_URL = AbsoluteHttpURL("https://www.box.com")


class BoxDotComCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (APP_DOMAIN,)
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File or Folder": "app.box.com/s?sh=<share_code>",
        "Embeded File or Folder": (
            "app.box.com/embed/s?sh=<share_code>",
            "app.box.com/embed_widget/s?sh=<share_code>",
        ),
    }
    DOMAIN: ClassVar[str] = "box.com"
    FOLDER_DOMAIN: ClassVar[str] = "Box"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.host == APP_DOMAIN and ("s" in scrape_item.url.parts or scrape_item.url.query.get("s")):
            return await self.file_or_folder(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file_or_folder(self, scrape_item: ScrapeItem) -> None:
        canonical_path = scrape_item.url.path
        for trash in ("/embed_widget/", "/embed/"):
            canonical_path = canonical_path.replace(trash, "")
        scrape_item.url = scrape_item.url.with_path(canonical_path, keep_query=True, keep_fragment=True)
        if "file" in scrape_item.url.parts and await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if "file or folder link has been removed" in soup.text:
            raise ScrapeError(410)

        js_text: str = css.select_one_get_text(soup, JS_SELECTOR)
        data = js_text.removesuffix(";").partition("=")[-1]
        if not data:
            raise ScrapeError(422)

        info: dict[str, Any] = json.loads(data)
        shared_name: str = info["/app-api/enduserapp/shared-item"]["sharedName"]
        shared_folder_data: dict[str, Any] | None = info.get("/app-api/enduserapp/shared-folder")
        if not shared_folder_data:
            # This is a file direct URL, ex: https://app.box.com/s/f30ss109euq3r2yhsuics35acxmnm
            # only the /file/ URL returns all the info about the file
            # We need to re make the request
            file_key = next(key for key in info if key.startswith("/app-api/enduserapp/item/f_"))
            _, file_id = file_key.rsplit("f_", 1)
            canonical_url = get_canonical_url(shared_name, file_id)
            scrape_item.url = canonical_url
            self.manager.task_group.create_task(self.run(scrape_item))
            return

        shared_folder = SharedFolder(**shared_folder_data)
        if "file" not in scrape_item.url.parts:
            # Proccess folder
            return await self.folder(scrape_item, shared_name, shared_folder)

        # Proccess individual file
        assert len(scrape_item.url.parts) >= 5
        file_id = scrape_item.url.parts[4]
        file = next(item for item in shared_folder.items if item.id == file_id)
        scrape_item.url = get_canonical_url(shared_name, file_id)
        await self.file(scrape_item, shared_name, file)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, shared_name: str, folder: SharedFolder) -> None:
        title = self.create_title(folder.name, folder.id)
        scrape_item.setup_as_album(title, album_id=folder.id)
        scrape_item.url = get_canonical_url(shared_name, folder.id, is_folder=True)

        file_system = self.build_file_system(folder.items, folder.id)
        for path, item in file_system.items():
            if item.type != ItemType.file:
                continue
            link = get_canonical_url(shared_name, item.id)
            new_scrape_item = scrape_item.create_child(link)
            for part in path.parts:
                new_scrape_item.add_to_parent_title(part)
            await self.file(new_scrape_item, shared_name, item)
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, shared_name: str, file: Item) -> None:
        assert file.type == ItemType.file
        filename, ext = self.get_filename_and_ext(file.name)
        link = DOWNLOAD_URL_BASE.update_query(shared_name=shared_name, file_id=file.typed_id)
        scrape_item.possible_datetime = file.date
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=link)

    def build_file_system(self, items: list[Item], root_id: str) -> dict[Path, Item]:
        """Builds a flattened dictionary representing a file system from a list of items.

        Returns:
            A 1-level dictionary where the each keys is the full path to a file/folder, and each value is the actual file/folder
        """

        path_mapping: dict[Path, Item] = {}
        parents_mapping: dict[str, list[Item]] = defaultdict(list)

        for item in items:
            parents_mapping[item.parent_id].append(item)

        def build_tree(parent_id: str, current_path: Path) -> None:
            for item in parents_mapping.get(parent_id, []):
                item_path = current_path / item.name
                path_mapping[item_path] = item

                if item.type == ItemType.folder:
                    build_tree(item.id, item_path)

        root_item = next(item for item in items if item.id == root_id)
        path = Path()
        path_mapping[path] = root_item
        build_tree(root_id, path)
        sorted_mapping = dict(sorted(path_mapping.items()))
        return sorted_mapping


def get_canonical_url(shared_name: str, id: str, is_folder: bool = False) -> AbsoluteHttpURL:
    base = AbsoluteHttpURL(f"https://app.box.com/s/{shared_name}")
    if is_folder:
        return base / "folder" / id
    return base / "file" / id
