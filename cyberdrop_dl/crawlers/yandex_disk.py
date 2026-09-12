from __future__ import annotations

import contextlib
import dataclasses
import json
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dataclass import DictDataclass
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


_PRIMARY_URL = AbsoluteHttpURL("https://disk.yandex.com.tr/")
_DOWNLOAD_API_ENTRYPOINT = AbsoluteHttpURL("https://disk.yandex.com.tr/public/api/download-url")
_KEYS_TO_KEEP = "currentResourceId", "resources", "environment"
_DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "DNT": "1",
    "Sec-GPC": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site: same-originPriority": "u=0",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}


class YandexDiskCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "disk.yandex", "yadi.sk"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Folder": "/d/<folder_id>",
        "File": (
            "/d/<folder_id>/<file_name>",
            "/i/<file_id>",
        ),
        "**NOTE**": "Does NOT support nested folders",
    }

    DOMAIN: ClassVar[str] = "disk.yandex"
    FOLDER_DOMAIN: ClassVar[str] = "YandexDisk"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["d", folder_id, file_name]:
                return await self.folder(scrape_item, folder_id, file_name)
            case ["d", folder_id]:
                return await self.folder(scrape_item, folder_id)
            case ["i", _]:
                return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        with self._request_context():
            soup = await self.request_soup(scrape_item.url, headers=_DEFAULT_HEADERS)

        item_info = _get_item_info(soup)
        assert _is_single_item(item_info)
        item_info["sk"] = item_info["environment"]["sk"]
        item_info["file_url"] = scrape_item.url
        file = YandexFile.from_json(item_info)
        return await self._process_file(scrape_item, file)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str, single_file_name: str | None = None) -> None:
        canonical_url = _PRIMARY_URL / "d" / folder_id
        if single_file_name and await self.check_complete_from_referer(scrape_item.url):
            return None

        scrape_item.url = canonical_url
        with self._request_context():
            soup = await self.request_soup(scrape_item.url, headers=_DEFAULT_HEADERS)

        item_info = _get_item_info(soup)
        del soup
        if _is_single_item(item_info):
            item_info["sk"] = item_info["environment"]["sk"]
            item_info["file_url"] = scrape_item.url
            file = YandexFile.from_json(item_info)
            return await self._process_file(scrape_item, file)

        folder = YandexFolder.from_json(item_info)
        title = self.create_title(folder.name, folder.id)
        scrape_item.setup_as_album(title, album_id=folder.id)

        for file in folder.files:
            if single_file_name and file.name != single_file_name:
                continue
            new_scrape_item = scrape_item.create_child(file.url)
            await self._process_file(new_scrape_item, file)
            scrape_item.add_children()
            if single_file_name:
                return None

    @contextlib.contextmanager
    def _request_context(self) -> Generator[None]:
        try:
            yield
        except DownloadError as e:
            if e.status in {400, 403}:
                raise DDOSGuardError from None
            raise

    @error_handling_wrapper
    async def _process_file(self, scrape_item: ScrapeItem, file: YandexFile) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        headers = _download_url_headers(scrape_item.url, file.url)

        api_url = _DOWNLOAD_API_ENTRYPOINT.with_host(scrape_item.url.host)
        with self._request_context():
            json_resp: dict[str, Any] = await self.request_json(
                api_url,
                method="POST",
                headers=headers,
                data=file.post_data,
            )

        new_sk = json_resp.get("new_sk")
        if new_sk:
            new_file = file.with_sk(new_sk)
            return await self._process_file(scrape_item, new_file)

        error = json_resp.get("error")
        if error:
            raise ScrapeError(422, message=json.dumps(json_resp)[:50])

        self.log.debug(json_resp)
        scrape_item.uploaded_at = file.modified
        link_str: str = json_resp["data"]["url"]
        link = self.parse_url(link_str)

        filename = link.query.get("filename") or file.name
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(file.url, scrape_item, filename, ext, debrid_link=link)


def _download_url_headers(url: AbsoluteHttpURL, referer: AbsoluteHttpURL) -> dict[str, str]:
    return _DEFAULT_HEADERS | {
        "Content-Type": "text/plain",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": str(url.origin()),
        "Referer": str(referer),
        "X-Retpath-Y": str(referer),
    }


def _get_item_info(soup: BeautifulSoup) -> dict[str, Any]:
    js_text: str = css.select_text(soup, "script#store-prefetch")
    info_json: dict[str, dict[str, Any]] = json.loads(js_text)
    info_json = {k: v for k, v in info_json.items() if k in _KEYS_TO_KEEP}
    env: dict[str, str] = info_json["environment"]
    info_json["environment"] = {"sk": env["sk"]}  # We don't need any other info from env
    return info_json


@dataclasses.dataclass(frozen=True, kw_only=True)
class YandexItem(DictDataclass):
    name: str
    modified: int
    type: Literal["file", "dir"]
    id: str
    path: str
    sk: str
    short_url: AbsoluteHttpURL  # https://yadi.sk/d/<id>

    @property
    def post_data(self) -> str:
        return json.dumps({"hash": self.path, "sk": self.sk})

    def with_sk(self, new_sk: str) -> Self:
        return dataclasses.replace(self, sk=new_sk)


@dataclasses.dataclass(frozen=True, kw_only=True)
class YandexFolder(YandexItem):
    resources: dict[str, Any]
    children_ids: list[str]

    @property
    def public_id(self) -> str:
        return self.short_url.name

    @property
    def files(self) -> Generator[YandexFile]:
        for child_id in self.children_ids:
            item_info: dict[str, Any] = self.resources[child_id]
            if item_info["type"] != "file":
                continue  # TODO handle subfolders

            yield YandexFile.from_dict(
                YandexFile.filter_dict(item_info),
                parent_folder_public_id=self.public_id,
                sk=self.sk,
            )

    @property
    def subfolders(self) -> Generator[YandexFolder]:
        for child_id in self.children_ids:
            item_info: dict[str, Any] = self.resources[child_id]
            if item_info["type"] != "folder":
                continue
        raise NotImplementedError

    @property
    def url(self) -> AbsoluteHttpURL:
        return _PRIMARY_URL / "d" / self.id

    @classmethod
    def from_json(cls, json_resp: dict[str, Any]) -> Self:
        resources: dict[str, dict[str, Any]] = json_resp["resources"]
        folder_id: str = json_resp["currentResourceId"]
        sk: str = json_resp["environment"]["sk"]

        folder_details = resources[folder_id]
        short_url = AbsoluteHttpURL(folder_details["meta"]["short_url"])
        children_ids: list[str] = folder_details["children"]
        return cls.from_dict(
            cls.filter_dict(folder_details),
            resources=resources,
            sk=sk,
            short_url=short_url,
            children_ids=children_ids,
        )


@dataclasses.dataclass(frozen=True, kw_only=True)
class YandexFile(YandexItem):
    parent_folder_public_id: str = ""
    file_url: AbsoluteHttpURL | None = None

    @property
    def url(self) -> AbsoluteHttpURL:
        if self.parent_folder_public_id:
            return _PRIMARY_URL / "d" / self.parent_folder_public_id / self.name
        if self.file_url:
            return self.file_url
        return self.short_url

    @classmethod
    def from_json(cls, json_resp: dict[str, Any]) -> Self:
        resources: dict[str, dict[str, Any]] = json_resp["resources"]
        assert len(resources) == 1
        file_details = next(iter(resources.items()))[1]
        sk: str = json_resp["environment"]["sk"]

        short_url = AbsoluteHttpURL(file_details["meta"]["short_url"])
        valid_dict: dict[str, Any] = cls.filter_dict(file_details)
        return cls.from_dict(valid_dict, sk=sk, short_url=short_url)


def _is_single_item(json_resp: dict[str, Any]) -> bool:
    return len(json_resp["resources"]) == 1 and not bool(json_resp["currentResourceId"])
