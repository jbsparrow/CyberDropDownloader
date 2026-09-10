# Only works with public share links (AKA "anyone can access")
# Adapted from microsoft API docs
# See: https://learn.microsoft.com/en-us/onedrive/developer/rest-api/api/driveitem_list_children?view=odsp-graph-online

from __future__ import annotations

import dataclasses
from collections import deque
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from cyberdrop_dl.cache import disk_cached_method
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedDomains, SupportedPaths, URLConfig
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import dates, parse_url
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem

SHARE_URL: ContextVar[AbsoluteHttpURL] = ContextVar("SHARE_URL")


@URLConfig(allow_empty_path=True)
@Crawler.db_path_builder("path_qs")
class OneDriveCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Access Link": "https://onedrive.live.com/?authkey=<KEY>&id=<ID>&cid=<CID>",
        "Share Link (anyone can access)": ("https://1drv.ms/<path>",),
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "1drv.ms", "onedrive.live.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://onedrive.com/")
    DOMAIN: ClassVar[str] = "onedrive"
    FOLDER_DOMAIN: ClassVar[str] = "OneDrive"

    def __post_init__(self) -> None:
        self.api: OneDriveAPI = OneDriveAPI.from_crawler(self)

    async def __async_post_init__(self) -> None:
        with self.disable_on_error("Unable to get badger token"):
            await self.api.auth()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123 or  https://1drv.ms/t/c/a12345678/aTOKEN?e=ABC123
        if scrape_item.url.host == "1drv.ms":
            return await self.share_link(scrape_item)

        # ex: https://onedrive.live.com/?authkey=!AUTHXXX-12345&id=ABCXYZ!12345&cid=ABC0123BVC
        await self.resource(scrape_item)

    @error_handling_wrapper
    async def share_link(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        SHARE_URL.set(scrape_item.url)
        scrape_item.url = await self.request_redirect(scrape_item.url)
        await self.resource(scrape_item)

    @error_handling_wrapper
    async def resource(self, scrape_item: ScrapeItem) -> None:
        resource_id, drive_id, cred = _parse_resource(scrape_item.url)
        if await self.check_complete_from_referer(scrape_item.url):
            return

        resource = await self.api.resource(resource_id, drive_id, cred)
        if resource.type == "file":
            await self._file(scrape_item, resource, cred)
            return

        scrape_item.setup_as_album(self.create_title(resource.name))
        await self._walk_fs(scrape_item, resource, cred)

    async def _walk_fs(self, scrape_item: ScrapeItem, folder: Folder, cred: Credentials) -> None:
        subfolders: deque[tuple[tuple[str, ...], Folder]] = deque()
        path = ()

        while True:
            children = await self.api.children(folder.id, folder.drive_id, cred)
            for node in children:
                if node.type == "folder":
                    subfolders.append(((*path, node.name), node))
                    continue

                new_item = scrape_item.create_child(node.web_url)
                new_item.append_folders(*path)
                self.create_eager_task(self._file(new_item, node, cred))
                scrape_item.add_children()

            if not subfolders:
                return

            path, folder = subfolders.popleft()

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File, cred: Credentials) -> None:
        # scrape_item.url should be web URL aka share link, ex: https://1drv.ms/t/s!ABCJKL-ABCJKL?e=ABC123
        # file.url should be API URL, ex: https://api.onedrive.com/v1.0/drives/<container_id>/items/<resid>?authkey=<auth_key>
        # Auth key will be removed in database but a new one can be generated from scrape_item.url
        if file.sha256 and await self.check_complete_by_hash(scrape_item.url, "sha256", file.sha256):
            return

        filename, ext = self.get_filename_and_ext(file.name)
        scrape_item.uploaded_at = file.date
        await self.handle_file(
            self.api.resolve(file.id, file.drive_id, cred),
            scrape_item,
            file.name,
            ext,
            custom_filename=filename,
            debrid_link=file.download_url,
            referer=SHARE_URL.get(scrape_item.url),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Credentials:
    auth_key: str
    redeem: str


@dataclasses.dataclass(frozen=True, slots=True)
class Resource:
    id: str
    drive_id: str
    name: str
    date: float
    web_url: AbsoluteHttpURL


@dataclasses.dataclass(frozen=True, slots=True)
class File(Resource):
    type: Literal["file"]
    download_url: AbsoluteHttpURL
    sha256: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Folder(Resource):
    type: Literal["folder"]


class OneDriveAPI(API):
    # Default app details used in browsers by unautenticated sessions
    APP_ID: ClassVar[str] = "1141147648"
    APP_UUID: ClassVar[str] = "5cbed6ac-a083-4e14-b191-b4ba07653de2"

    BADGER_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api-badgerp.svc.ms/v1.0/token")
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.onedrive.com/v1.0/drives/")
    PERSONAL_ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL(
        "https://my.microsoftpersonalcontent.com/_api/v2.0/shares/"
    )

    async def auth(self) -> None:
        token = await self._get_badger_token()
        self.__http_ctx__.headers.update({"Prefer": "autoredeem", "Authorization": f"Badger {token}"})

    @disk_cached_method("badger_token", ttl=3600 * 20)
    async def _get_badger_token(self) -> str:
        resp: dict[str, Any] = await self.request_json(
            self.BADGER_URL,
            method="POST",
            headers={"AppId": self.APP_ID},
            json={"appId": self.APP_UUID},
        )
        return resp["token"]

    @classmethod
    def resolve(cls, resource_id: str, drive_id: str, cred: Credentials) -> AbsoluteHttpURL:
        if cred.redeem:
            api_url = cls.PERSONAL_ENTRYPOINT / f"u!{cred.redeem}" / "driveitem"
        else:
            api_url = cls.ENTRYPOINT / drive_id / "items" / resource_id

        if cred.auth_key:
            return api_url.update_query(authkey=cred.auth_key)
        return api_url

    async def resource(self, resource_id: str, drive_id: str, cred: Credentials) -> File | Folder:
        url = self.resolve(resource_id, drive_id, cred)
        resp = await self.request_json(url)
        return normalize_resource(resp)

    async def children(self, resource_id: str, drive_id: str, cred: Credentials) -> list[File | Folder]:
        url = self.resolve(resource_id, drive_id, cred)
        resp = await self.request_json(url.with_query(expand="children", orderby="folder,name"))
        return [normalize_resource(c) for c in resp.get("children", ())]


def normalize_resource(resp: dict[str, Any]) -> File | Folder:
    dl_url = resp.get("@content.downloadUrl")
    is_folder = bool(resp.get("folder"))
    try:
        sha256 = resp["hashes"]["sha256Hash"]
    except LookupError:
        sha256 = None

    data = {
        "id": resp["id"],
        "drive_id": resp["parentReference"]["driveId"],
        "web_url": parse_url(resp["webUrl"]),
        "name": resp["name"],
        "type": "folder" if is_folder else "file",
        "date": dates.parse_iso(resp["fileSystemInfo"]["lastModifiedDateTime"]).timestamp(),
        "download_url": parse_url(dl_url) if dl_url else None,
        "sha256": sha256,
    }
    return deserialize(Folder if is_folder else File, data)


def _parse_resource(url: AbsoluteHttpURL) -> tuple[str, str, Credentials]:
    get = url.query.get
    cred = Credentials(get("authkey") or "", get("redeem") or "")
    if not (cred.auth_key or cred.redeem):
        raise ScrapeError.unsupported()

    resource_id = get("id") or ""
    resid = get("resid") or ""  # ex: ABCXYZ000!12345
    if not resid and "!" in resource_id:
        resid = resource_id

    if not (resid and cred.auth_key) and not cred.redeem:
        raise ScrapeError(401)

    container_id = get("cid") or resid.partition("!")[0]
    return resid, container_id, cred
