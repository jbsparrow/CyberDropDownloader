# Only works with public share links (AKA "anyone can access")
# Adapted from microsoft API docs
# See: https://learn.microsoft.com/en-us/onedrive/developer/rest-api/api/driveitem_list_children?view=odsp-graph-online

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, Self

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


API_ENTRYPOINT = AbsoluteHttpURL("https://api.onedrive.com/v1.0/drives/")
PERSONAL_API_ENTRYPOINT = AbsoluteHttpURL("https://my.microsoftpersonalcontent.com/_api/v2.0/shares/")
BADGER_URL = AbsoluteHttpURL("https://api-badgerp.svc.ms/v1.0/token")
SHARE_LINK_HOST = "1drv.ms"
SHARE_LINK_PARTS = "f", "t", "u", "b"

# Default app details used in browsers by unautenticated sessions
APP_ID = "1141147648"
APP_UUID = "5cbed6ac-a083-4e14-b191-b4ba07653de2"


@dataclass(frozen=True, slots=True)
class AccessDetails:
    container_id: str
    resid: str
    auth_key: str
    redeem: str

    @classmethod
    def from_url(cls, direct_url: AbsoluteHttpURL) -> AccessDetails:
        resid = direct_url.query.get("resid") or ""  # ex: ABCXYZ000!12345
        auth_key = direct_url.query.get("authkey") or ""
        redeem = direct_url.query.get("redeem") or ""
        id_ = direct_url.query.get("id") or ""
        container_id = direct_url.query.get("cid")
        if not resid and "!" in id_:
            resid = id_
        if not container_id:
            container_id = resid.split("!")[0]

        return AccessDetails(container_id, resid, auth_key, redeem)


@dataclass(frozen=True, slots=True)
class OneDriveItem:
    id: str
    url: AbsoluteHttpURL
    web_url: AbsoluteHttpURL
    name: str
    date: int
    access_details: AccessDetails


@dataclass(frozen=True, slots=True)
class OneDriveFile(OneDriveItem):
    download_url: AbsoluteHttpURL

    @classmethod
    def from_api_response(cls, json_resp: dict, access_details: AccessDetails) -> Self:
        info = parse_api_response(json_resp, access_details)
        download_url_str = json_resp["@content.downloadUrl"]
        info["download_url"] = AbsoluteHttpURL(download_url_str, encoded="%" in download_url_str)
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
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Access Link": "https://onedrive.live.com/?authkey=<KEY>&id=<ID>&cid=<CID>",
        "Share Link (anyone can access)": (
            "https://1drv.ms/t/<KEY>",
            "https://1drv.ms/f/<KEY>",
            "https://1drv.ms/b/<KEY>",
            "https://1drv.ms/u/<KEY>",
        ),
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = SHARE_LINK_HOST, "onedrive.live.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://onedrive.com/")
    SKIP_PRE_CHECK: ClassVar[bool] = True  # URLs with not path could be valid
    DOMAIN: ClassVar[str] = "onedrive"
    FOLDER_DOMAIN: ClassVar[str] = "OneDrive"

    def __post_init__(self) -> None:
        badger_token: str = self.manager.cache_manager.get("onedrive_badger_token") or ""
        badger_token_expires: str = self.manager.cache_manager.get("onedrive_badger_token_expires") or ""
        self.auth_headers = {}
        expired = True
        if badger_token_expires:
            if badger_token_expires.endswith("Z"):
                badger_token_expires = badger_token_expires.replace("Z", "+00:00")
            expire_datetime = datetime.fromisoformat(badger_token_expires)
            t_delta = expire_datetime - datetime.now(UTC)
            if t_delta > timedelta(hours=12):
                expired = False
        if badger_token and not expired:
            self.auth_headers = {"Prefer": "autoredeem", "Authorization": f"Badger {badger_token}"}

    async def async_startup(self) -> None:
        if self.auth_headers:
            return
        await self.get_badger_token(BADGER_URL)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123 or  https://1drv.ms/t/c/a12345678/aTOKEN?e=ABC123
        if is_share_link(scrape_item.url):
            return await self.share_link(scrape_item)

        # ex: https://onedrive.live.com/?authkey=!AUTHXXX-12345&id=ABCXYZ!12345&cid=ABC0123BVC
        await self.link_with_credentials(scrape_item)

    @error_handling_wrapper
    async def share_link(self, scrape_item: ScrapeItem) -> None:
        og_share_link = scrape_item.url
        scrape_item.url = await self._get_redirect_url(scrape_item.url)
        await self.link_with_credentials(scrape_item, og_share_link)

    @error_handling_wrapper
    async def link_with_credentials(
        self, scrape_item: ScrapeItem, og_share_link: AbsoluteHttpURL | None = None
    ) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        if og_share_link and await self.check_complete_from_referer(og_share_link):
            return

        access_details = AccessDetails.from_url(scrape_item.url)
        await self.process_access_details(scrape_item, access_details, og_share_link)

    @error_handling_wrapper
    async def process_access_details(
        self, scrape_item: ScrapeItem, access_details: AccessDetails, og_share_link: AbsoluteHttpURL | None = None
    ) -> None:
        if not (access_details.resid and access_details.auth_key) and not access_details.redeem:
            raise ScrapeError(401)

        if access_details.redeem and not self.auth_headers:
            raise ScrapeError(401)

        api_url = create_api_url(access_details)
        json_resp: dict = await self.make_api_request(api_url)

        if not is_folder(json_resp):
            file = OneDriveFile.from_api_response(json_resp, access_details)
            scrape_item.url = og_share_link or file.web_url
            return await self.process_file(scrape_item, file)

        folder = OneDriveFolder.from_api_response(json_resp, access_details)
        await self.process_folder(scrape_item, folder)

    @error_handling_wrapper
    async def process_folder(self, scrape_item: ScrapeItem, folder: OneDriveFolder) -> None:
        title = self.create_title(folder.name)
        scrape_item.setup_as_album(title)

        subfolders: list[AccessDetails] = []
        old_ad = folder.access_details
        new_access_details = partial(AccessDetails, auth_key=old_ad.auth_key, redeem=old_ad.redeem)

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
            api_url = create_api_url(access_details)
            new_scrape_item = scrape_item.create_child(api_url)
            self.create_task(self.process_access_details(new_scrape_item, access_details))
            scrape_item.add_children()

    @error_handling_wrapper
    async def process_file(self, scrape_item: ScrapeItem, file: OneDriveFile) -> None:
        # scrape_item.url should be web URL aka share link, ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123
        # file.url should be API URL, ex: https://api.onedrive.com/v1.0/drives/<container_id>/items/<resid>?authkey=<auth_key>
        # Auth key will be removed in database but a new one can be generated from scrape_item.url
        filename, ext = self.get_filename_and_ext(file.name)
        scrape_item.possible_datetime = file.date
        await self.handle_file(file.url, scrape_item, filename, ext, debrid_link=file.download_url)

    async def make_api_request(self, api_url: AbsoluteHttpURL) -> dict[str, Any]:
        return await self.request_json(
            api_url,
            headers={
                "Content-Type": "application/json",
            }
            | self.auth_headers,
        )

    @error_handling_wrapper
    async def get_badger_token(self, badger_url: AbsoluteHttpURL = BADGER_URL) -> None:
        json_resp: dict[str, Any] = await self.request_json(
            badger_url,
            method="POST",
            headers={"Content-Type": "application/json", "AppId": APP_ID},
            json={"appId": APP_UUID},
        )
        badger_token: str = json_resp["token"]
        badger_token_expires: str = json_resp["expiryTimeUtc"]
        self.auth_headers = {"Prefer": "autoredeem", "Authorization": f"Badger {badger_token}"}
        self.manager.cache_manager.save("onedrive_badger_token", badger_token)
        self.manager.cache_manager.save("onedrive_badger_token_expires", badger_token_expires)


def is_share_link(url: AbsoluteHttpURL) -> bool:
    return bool(url.host and url.host == SHARE_LINK_HOST) and any(p in url.parts for p in SHARE_LINK_PARTS)


def is_folder(json_resp: dict[str, Any]) -> bool:
    return bool(json_resp.get("folder"))


def parse_api_response(json_resp: dict, access_details: AccessDetails) -> dict[str, Any]:
    web_url_str: str = json_resp["webUrl"]
    item_id = json_resp["id"]
    date_str = json_resp["fileSystemInfo"]["lastModifiedDateTime"]
    drive_id = json_resp["parentReference"]["driveId"]
    new_access_details = AccessDetails(drive_id, item_id, access_details.auth_key, access_details.redeem)
    return {
        "id": item_id,
        "url": create_api_url(new_access_details),
        "web_url": AbsoluteHttpURL(web_url_str, encoded="%" in web_url_str),
        "name": json_resp["name"],
        "date": to_timestamp(datetime.fromisoformat(date_str)),
        "access_details": new_access_details,
    }


def create_api_url(access_details: AccessDetails) -> AbsoluteHttpURL:
    if access_details.redeem:
        api_url = PERSONAL_API_ENTRYPOINT / f"u!{access_details.redeem}" / "driveitem"
    else:
        api_url = API_ENTRYPOINT / access_details.container_id / "items" / access_details.resid

    api_url = api_url.with_query(expand="children", orderby="folder,name")
    if access_details.auth_key:
        return api_url.update_query(authkey=access_details.auth_key)
    return api_url
