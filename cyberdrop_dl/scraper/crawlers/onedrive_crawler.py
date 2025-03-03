# Only works with public share links (AKA "anyone can access")
# Adapted from microsoft API docs
# See: https://learn.microsoft.com/en-us/onedrive/developer/rest-api/api/driveitem_list_children?view=odsp-graph-online

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, Self

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


API_ENTRYPOINT = URL("https://api.onedrive.com/v1.0/drives/")
SHARE_LINK_HOST = "1drv.ms"


@dataclass(frozen=True, slots=True)
class AccessDetails:
    container_id: str
    resid: str
    auth_key: str

    @classmethod
    def from_url(cls, direct_url: URL) -> AccessDetails:
        resid = direct_url.query.get("resid") or ""  # ex: ABCXYZ000!12345
        auth_key = direct_url.query.get("authkey") or ""
        id_ = direct_url.query.get("id") or ""
        container_id = direct_url.query.get("cid")
        if not resid and "!" in id_:
            resid = id_
        if not container_id:
            container_id = resid.split("!")[0]

        return AccessDetails(container_id, resid, auth_key)


@dataclass(frozen=True, slots=True)
class OneDriveItem:
    id: str
    url: URL
    web_url: URL
    name: str
    date: int
    access_details: AccessDetails


@dataclass(frozen=True, slots=True)
class OneDriveFile(OneDriveItem):
    download_url: URL

    @classmethod
    def from_api_response(cls, json_resp: dict, access_details: AccessDetails) -> Self:
        info = parse_api_response(json_resp, access_details)
        download_url_str = json_resp["@content.downloadUrl"]
        info["download_url"] = URL(download_url_str, encoded="%" in download_url_str)
        return cls(**info)


@dataclass(frozen=True, slots=True)
class OneDriveFolder(OneDriveItem):
    children: list[dict[str, Any]]

    @classmethod
    def from_api_response(cls, json_resp: dict, access_details: AccessDetails) -> Self:
        info = parse_api_response(json_resp, access_details)
        info["children"] = json_resp["children"]
        return cls(**info)


class OneDriveCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"onedrive": [SHARE_LINK_HOST, "onedrive.live.com"]}
    primary_base_domain = URL("https://onedrive.com/")
    skip_pre_check = True  # URLs with not path could be valid

    def __init__(self, manager: Manager, _) -> None:
        super().__init__(manager, "onedrive", "OneDrive")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_share_link(scrape_item.url):  # ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123
            return await self.share_link(scrape_item)

        # ex: https://onedrive.live.com/?authkey=!AUTHXXX-12345&id=ABCXYZ!12345&cid=ABC0123BVC
        await self.link_with_credentials(scrape_item)

    @error_handling_wrapper
    async def share_link(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            headers: dict = await self.client.get_head(self.domain, scrape_item.url)
        location = headers.get("location")
        if not location:
            raise ScrapeError(400)
        scrape_item.url = self.parse_url(location)
        await self.link_with_credentials(scrape_item)

    @error_handling_wrapper
    async def link_with_credentials(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        access_details = AccessDetails.from_url(scrape_item.url)
        await self.process_access_details(scrape_item, access_details)

    @error_handling_wrapper
    async def process_access_details(self, scrape_item: ScrapeItem, access_details: AccessDetails) -> None:
        if not access_details.resid or not access_details.auth_key:
            raise ScrapeError(401)

        api_url = get_api_url(access_details)
        json_resp: dict = await self.make_api_request(api_url)

        if not is_folder(json_resp):
            file = OneDriveFile.from_api_response(json_resp, access_details)
            scrape_item.url = file.web_url
            return await self.process_file(scrape_item, file)

        folder = OneDriveFolder.from_api_response(json_resp, access_details)
        await self.process_folder(scrape_item, folder)

    @error_handling_wrapper
    async def process_folder(self, scrape_item: ScrapeItem, folder: OneDriveFolder) -> None:
        title = self.create_title(folder.name)
        scrape_item.setup_as_album(title)

        subfolders: list[AccessDetails] = []
        new_access_details = partial(AccessDetails, auth_key=folder.access_details.auth_key)

        for item in folder.children:
            if is_folder(item):
                container_id: str = item["parentReference"]["driveId"]
                resid: str = item["id"]
                access_details = new_access_details(container_id, resid)
                subfolders.append(access_details)
                continue

            file = OneDriveFile.from_api_response(item, folder.access_details)
            new_scrape_item = scrape_item.create_child(file.web_url)
            await self.process_file(new_scrape_item, file)
            scrape_item.add_children()

        for access_details in subfolders:
            api_url = get_api_url(access_details)
            new_scrape_item = scrape_item.create_child(api_url)
            self.manager.task_group.create_task(self.process_access_details(new_scrape_item, access_details))
            scrape_item.add_children()

    @error_handling_wrapper
    async def process_file(self, scrape_item: ScrapeItem, file: OneDriveFile) -> None:
        # scrape_item.url should be web URL aka share link, ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123
        # file.url should be API URL, ex: https://api.onedrive.com/v1.0/drives/<container_id>/items/<resid>?authkey=<auth_key>
        # Auth key will be removed in database but a new one can be generated from scrape_item.url
        filename, ext = self.get_filename_and_ext(file.name)
        scrape_item.possible_datetime = file.date
        await self.handle_file(file.url, scrape_item, filename, ext, debrid_link=file.download_url)

    async def make_api_request(self, api_url: URL) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, api_url, headers_inc=headers)

        return json_resp


def is_share_link(url: URL) -> bool:
    return bool(url.host and url.host == SHARE_LINK_HOST) and any(p in url.parts for p in ("f", "t"))


def is_folder(json_resp: dict[str, Any]) -> bool:
    return bool(json_resp.get("folder"))


def parse_api_response(json_resp: dict, access_details: AccessDetails) -> dict[str, Any]:
    web_url_str: str = json_resp["webUrl"]
    item_id = json_resp["id"]
    date_str = json_resp["fileSystemInfo"]["lastModifiedDateTime"]
    drive_id = json_resp["parentReference"]["driveId"]
    new_access_details = AccessDetails(drive_id, item_id, access_details.auth_key)
    return {
        "id": item_id,
        "url": get_api_url(new_access_details),
        "web_url": URL(web_url_str, encoded="%" in web_url_str),
        "name": json_resp["name"],
        "date": parse_datetime(date_str),
        "access_details": new_access_details,
    }


def get_api_url(access_details: AccessDetails) -> URL:
    api_url = API_ENTRYPOINT / access_details.container_id / "items" / access_details.resid
    return api_url.with_query(authkey=access_details.auth_key, expand="children", orderby="folder,name")


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.fromisoformat(date)
    return calendar.timegm(parsed_date.timetuple())
