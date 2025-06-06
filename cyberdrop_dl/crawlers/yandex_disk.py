from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.downloader.mega_nz import AnyDict


JS_SELECTOR = "script#store-prefetch"
DOWNLOAD_API_ENTRYPOINT = AbsoluteHttpURL("https://disk.yandex.com.tr/public/api/download-url")
PRIMARY_URL = AbsoluteHttpURL("https://disk.yandex.com.tr/")
KEYS_TO_KEEP = "currentResourceId", "resources", "environment"


class YandexDiskCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "disk.yandex", "yadi.sk"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Folder": "/d/<folder_id>",
        "Files": "/d/<folder_id>/<file_name>",
        "**NOTE**": "Does NOT support nested folders",
    }

    DOMAIN: ClassVar[str] = "disk.yandex"
    FOLDER_DOMAIN: ClassVar[str] = "YandexDisk"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "d" in scrape_item.url.parts:
            return await self.folder(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        single_file_name = scrape_item.url.parts[3] if len(scrape_item.url.parts) > 3 else None
        canonical_url = get_canonical_url(scrape_item.url)
        if single_file_name and await self.check_complete_from_referer(scrape_item.url):
            return

        scrape_item.url = canonical_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        item_info = get_item_info(soup)
        del soup
        if is_single_item(item_info):
            item_info["sk"] = item_info["environment"]["sk"]
            item_info["file_url"] = scrape_item.url
            file = YandexFile.from_json(item_info)
            return await self.file(scrape_item, file)

        folder = YandexFolder.from_json(item_info)
        title = self.create_title(folder.name, folder.id)
        scrape_item.setup_as_album(title, album_id=folder.id)

        for file in folder.files:
            if single_file_name and file.name != single_file_name:
                continue
            new_scrape_item = scrape_item.create_child(file.url)
            await self.file(new_scrape_item, file)
            scrape_item.add_children()
            if single_file_name:
                return

        # TODO: Handle subfolders
        # #for subfolder in folder.subfolders:
        #    new_scrape_item = scrape_item.create_child(subfolder.url)
        #    pass

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file: YandexFile) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        referer = str(file.url)
        headers = {
            "Content-Type": "text/plain",
            "Referer": referer,
            "X-Retpath-Y": referer,
        }
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.post_data(
                self.DOMAIN, DOWNLOAD_API_ENTRYPOINT, data=file.post_data, headers=headers
            )

        new_sk = json_resp.get("new_sk")
        if new_sk:
            new_file = file.with_sk(new_sk)
            return await self.file(scrape_item, new_file)

        error = json_resp.get("error")
        if error:
            # The error format is dynamic but they are short
            # We can log them to the main file
            raise ScrapeError(422, message=json.dumps(json_resp))

        self.log_debug(json_resp)
        scrape_item.possible_datetime = file.modified
        link_str: str = json_resp["data"]["url"]
        link = self.parse_url(link_str)

        filename = link.query.get("filename") or file.name
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(file.url, scrape_item, filename, ext, debrid_link=link)


def get_item_info(soup: BeautifulSoup) -> dict:
    js_text: str = css.select_one_get_text(soup, JS_SELECTOR)
    info_json: dict[str, AnyDict] = json.loads(js_text)
    info_json = {k: v for k, v in info_json.items() if k in KEYS_TO_KEEP}
    env: dict[str, str] = info_json["environment"]
    info_json["environment"] = {"sk": env["sk"]}  # We don't need any other info from env
    return info_json


@dataclass(frozen=True, kw_only=True)
class YandexItem:
    name: str
    modified: int
    type: Literal["file", "dir"]
    id: str
    path: str
    sk: str
    short_url: URL  # https://yadi.sk/d/<id>

    @classmethod
    def get_valid_dict(cls, info: dict) -> dict[str, Any]:
        valid_fields = {f.name for f in fields(cls)}
        return {k: v for k, v in info.items() if k in valid_fields}

    @property
    def post_data(self) -> str:
        return json.dumps({"hash": self.path, "sk": self.sk})

    def with_sk(self, new_sk) -> Self:
        values = asdict(self)
        values["sk"] = new_sk
        return self.__class__(**values)


@dataclass(frozen=True, kw_only=True)
class YandexFolder(YandexItem):
    resources: dict[str, Any]
    children_ids: list[str]

    @cached_property
    def public_id(self) -> str:
        return self.short_url.name

    @property
    def files(self) -> Generator[YandexFile]:
        for child_id in self.children_ids:
            item_info: dict[str, Any] = self.resources[child_id]
            if item_info["type"] != "file":
                continue  # TODO handle subfolders
            valid_dict = YandexFile.get_valid_dict(item_info)
            yield YandexFile(**valid_dict, parent_folder_public_id=self.public_id, sk=self.sk)

    @property
    def subfolders(self) -> Generator[YandexFolder]:
        for child_id in self.children_ids:
            item_info: dict[str, Any] = self.resources[child_id]
            if item_info["type"] != "folder":
                continue
        raise NotImplementedError

    @cached_property
    def url(self) -> URL:
        return PRIMARY_URL / "d" / self.id

    @classmethod
    def from_json(cls, json_resp: dict) -> Self:
        resources: dict[str, dict] = json_resp["resources"]
        folder_id: str = json_resp["currentResourceId"]
        sk: str = json_resp["environment"]["sk"]

        folder_details = resources[folder_id]
        short_url = URL(folder_details["meta"]["short_url"])
        children_ids: list[str] = folder_details["children"]
        valid_dict: dict[str, Any] = cls.get_valid_dict(folder_details)
        return cls(**valid_dict, resources=resources, sk=sk, short_url=short_url, children_ids=children_ids)


@dataclass(frozen=True, kw_only=True)
class YandexFile(YandexItem):
    parent_folder_public_id: str = ""
    file_url: URL | None = None

    @cached_property
    def url(self) -> URL:
        if self.parent_folder_public_id:
            return PRIMARY_URL / "d" / self.parent_folder_public_id / self.name
        if self.file_url:
            return self.file_url
        return self.short_url

    @classmethod
    def from_json(cls, json_resp: dict) -> Self:
        resources: dict[str, dict] = json_resp["resources"]
        assert len(resources) == 1
        file_details = next(iter(resources.items()))[1]
        sk: str = json_resp["environment"]["sk"]

        short_url = URL(file_details["meta"]["short_url"])
        valid_dict: dict[str, Any] = cls.get_valid_dict(file_details)
        return cls(**valid_dict, sk=sk, short_url=short_url)


def get_canonical_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    folder_id_index = url.parts.index("d") + 1
    folder_id = url.parts[folder_id_index]
    return PRIMARY_URL / "d" / folder_id


def is_single_item(json_resp: dict) -> bool:
    return len(json_resp["resources"]) == 1 and not bool(json_resp["currentResourceId"])
