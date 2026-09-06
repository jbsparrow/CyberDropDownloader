"""Crawler to download files and folders from mega.nz

This crawler does several CPU intensive operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from mega.api import MegaAPI
from mega.core import MegaCore
from mega.crypto import b64_to_a32
from mega.data_structures import Crypto

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.constants import CDL_USER_AGENT
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, URLConfig, auto_task_id
from cyberdrop_dl.downloader.mega_nz import MegaDownloader
from cyberdrop_dl.exceptions import LoginError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.progress.scraping import show_msg
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from mega.filesystem import FileSystem

    from cyberdrop_dl.url_objects import ScrapeItem


@HTTPConfig.default_headers(user_agent=CDL_USER_AGENT)
@URLConfig(allow_empty_path=True)
@Crawler.db_path_builder("path_qs_frag")
class MegaNzCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "mega.io", "mega.nz"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/file/<file_id>#<share_key>",
            "/folder/<folder_id>#<share_key>/file/<file_id>",
            "/!#<file_id>!<share_key>",
        ),
        "Folder": (
            "/folder/<folder_id>#<share_key>",
            "/F!#<folder_id>!<share_key>",
        ),
        "Subfolder": "/folder/<folder_id>#<share_key>/folder/<subfolder_id>",
        "**NOTE**": "Downloads can not be resumed. Partial downloads will always be deleted and new downloads will start over",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://mega.nz")
    DOMAIN: ClassVar[str] = "mega.nz"
    FOLDER_DOMAIN: ClassVar[str] = "MegaNz"
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ("mega.co.nz",)

    core: MegaCore
    downloader: MegaDownloader

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return AbsoluteHttpURL(MegaCore.ensure_v2_url(super().transform_url(url)))

    @property
    def user(self) -> str | None:
        return self.config.auth.mega_nz.email

    @property
    def password(self) -> str | None:
        return self.config.auth.mega_nz.password

    def __post_init__(self) -> None:
        self._decryption_keys: dict[AbsoluteHttpURL, tuple[Crypto, int]] = {}
        api = MegaAPI(self.client._session)
        api.user_agent = CDL_USER_AGENT
        self.core = MegaCore(api)
        speed_limiter = self.downloader.client.speed_limiter
        self.downloader = MegaDownloader(self.manager)  # pyright: ignore[reportIncompatibleVariableOverride]
        self.downloader.client.speed_limiter = speed_limiter

    async def __async_post_init__(self) -> None:
        await self._login()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self._logged_in:
            return None

        info = self.core.parse_url(scrape_item.url, check_key=False)
        if not info.public_key and scrape_item.password:
            with scrape_item.track_changes:
                scrape_item.url = _add_password(scrape_item.url, scrape_item.password)
                info = self.core.parse_url(scrape_item.url, check_key=False)

        if not info.public_key:
            self.raise_exc(scrape_item, PasswordProtectedError("Public key missing from URL"))
            return None

        if not info.is_folder:
            return await self.file(scrape_item, info.public_handle, info.public_key)

        await self.folder(scrape_item, info.public_handle, info.public_key, info.selected_folder, info.selected_file)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, handle: str, public_key: str) -> None:
        canonical_url = (self.PRIMARY_URL / "file" / handle).with_fragment(public_key)
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        full_key = b64_to_a32(public_key)
        await self._file(scrape_item, handle, Crypto.decompose(full_key))  # pyright: ignore[reportArgumentType]

    @error_handling_wrapper
    async def _file(
        self,
        scrape_item: ScrapeItem,
        handle: str,
        crypto: Crypto,
        *,
        folder_id: str | None = None,
    ) -> None:
        resp = await self.core.request_file_info(handle, folder_id, is_public=not folder_id)
        if not resp.url:
            raise ScrapeError(410, "File not accessible anymore")

        name = self.core.decrypt_attrs(resp._at, crypto.key, handle).name
        self._decryption_keys[scrape_item.url] = crypto, resp.size
        file_url = self.parse_url(resp.url)
        filename, ext = self.get_filename_and_ext(name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=file_url)

    _file_task = auto_task_id(_file)

    @error_handling_wrapper
    async def folder(
        self,
        scrape_item: ScrapeItem,
        handle: str,
        public_key: str,
        root_id: str | None = None,
        single_file_id: str | None = None,
    ) -> None:
        if single_file_id and await self.check_complete_from_referer(scrape_item.url):
            return

        selected_node = root_id or single_file_id
        fs = await self.core.get_public_filesystem(handle, public_key)
        root = next(iter(fs))
        title = self.create_title(root.attributes.name, handle)
        scrape_item.setup_as_album(title, album_id=handle)
        canonical_url = (self.PRIMARY_URL / "folder" / handle).with_fragment(public_key)
        scrape_item.url = canonical_url
        await self._filesystem(scrape_item, fs, selected_node)

    async def _filesystem(self, scrape_item: ScrapeItem, filesystem: FileSystem, selected_node_id: str | None) -> None:
        folder_id, public_key = scrape_item.url.name, scrape_item.url.fragment

        for file in filesystem.files_from(selected_node_id):
            path = filesystem.relative_path(file.id)
            file_fragment = f"{public_key}/file/{file.id}"
            canonical_url = scrape_item.url.with_fragment(file_fragment)
            if await self.check_complete_from_referer(canonical_url):
                continue

            child_item = scrape_item.create_child(canonical_url)
            child_item.uploaded_at = file.created_at
            for part in path.parent.parts[1:]:
                child_item.append_folders(part)

            self.create_eager_task(self._file_task(child_item, file.id, file._crypto, folder_id=folder_id))
            scrape_item.add_children()

    @override
    def _prepare_media_item(self, media_item: MediaItem) -> None:
        media_item.extra_info.setdefault(self.DOMAIN, {})["key"] = self._decryption_keys.pop(media_item.url)
        media_item.extra_info["impersonate"] = False  # We need aiohttp for precise chunks reads

    async def _login(self) -> None:
        # This takes a really long time (dozens of seconds)
        # TODO: Add a way to cache this login
        # TODO: Show some logging message / UI about login
        with self.catch_errors(self.PRIMARY_URL), self.disable_on_error("Unable to log into mega.nz"):
            try:
                with show_msg("Login into mega.nz"):
                    await self.core.login(self.user, self.password)
            except Exception as e:
                raise LoginError(f"[MegaNZ] {e}") from e
            else:
                self._logged_in = True


def _add_password(url: AbsoluteHttpURL, password: str) -> AbsoluteHttpURL:
    frag = url.fragment.lstrip("/")
    if not frag:
        return url.with_fragment(password)
    return url.with_fragment(f"{password}/{frag}")
