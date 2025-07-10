from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.downloader import mega_nz as mega
from cyberdrop_dl.downloader.mega_nz import DecryptData, File, MegaDownloader, NodeType
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://mega.nz")


class FileTuple(NamedTuple):
    id: str
    crypto: DecryptData


class MegaNzCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/file/<handle>#<share_key>",
            "/!#<handle>!<share_key>",
        ),
        "Folder": (
            "/folder/<handle>#<share_key>",
            "/F!#<handle>!<share_key>",
        ),
        "**NOTE**": "Downloads can not be resumed. Partial downloads will always be deleted and a new downloads will start over",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    SKIP_PRE_CHECK: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "mega.nz"
    FOLDER_DOMAIN: ClassVar[str] = "MegaNz"

    def __post_init__(self) -> None:
        self.downloader: MegaDownloader

    @property
    def user(self) -> str | None:
        return self.manager.auth_config.meganz.email or None

    @property
    def password(self) -> str | None:
        return self.manager.auth_config.meganz.password or None

    # TODO: define in base crawler
    def _init_downloader(self) -> MegaDownloader:
        self.downloader = dl = MegaDownloader(self.manager, self.DOMAIN)
        dl.startup()
        return dl

    async def startup(self) -> None:
        async with self.startup_lock:
            if self.ready:
                return
            self.client = self.manager.client_manager.scraper_session
            self.downloader = self._init_downloader()
            await self.async_startup()
            self.ready = True

    async def async_startup(self) -> None:
        await self.login(PRIMARY_URL)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if frag := scrape_item.url.fragment:  # Mega stores access key in fragment. We can't do anything without the key
            # v1 URLs
            if frag.count("!") == 2:
                if frag.startswith("F!"):
                    folder_id, shared_key = frag.removeprefix("F!").rsplit("!", 1)
                    return await self.folder(scrape_item, folder_id, shared_key)
                if frag.startswith("!"):
                    # https://mega.nz/#!Ue5VRSIQ!kC2E4a4JwfWWCWYNJovGFHlbz8F
                    file_id, shared_key = frag.removeprefix("!").rsplit("!", 1)
                    return await self.file(scrape_item, file_id, shared_key)

            # v2 URLs
            match scrape_item.url.parts[1:]:
                case ["folder", folder_id]:
                    return await self.folder(scrape_item, folder_id, frag)
                # https://mega.nz/file/cH51DYDR#qH7QOfRcM-7N9riZWdSjsRq
                case ["file", file_id]:
                    return await self.file(scrape_item, file_id, frag)

        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str, shared_key: str) -> None:
        canonical_url = PRIMARY_URL / "file" / file_id / shared_key
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        file_key = mega.base64_to_a32(shared_key)

        k: tuple[int, ...] = (
            file_key[0] ^ file_key[4],
            file_key[1] ^ file_key[5],
            file_key[2] ^ file_key[6],
            file_key[3] ^ file_key[7],
        )
        iv: tuple[int, ...] = (*file_key[4:6], 0, 0)
        meta_mac: tuple[int, ...] = file_key[6:8]
        file = FileTuple(file_id, DecryptData(iv, k, meta_mac))
        await self._process_file(scrape_item, file)

    @error_handling_wrapper
    async def _process_file(self, scrape_item: ScrapeItem, file: FileTuple, *, folder_id: str | None = None) -> None:
        params = {"a": "g", "g": 1}
        add_params = None
        if folder_id is not None:
            params = params | {"n": file.id}
            add_params = {"n": folder_id}
        else:
            params = params | {"p": file.id}
            add_params = None

        file_data: dict[str, Any] = await self.downloader.api.request(params, add_params)
        file_size: int = file_data["s"]
        if "g" not in file_data:
            raise ScrapeError(410, "File not accessible anymore")

        decrypt_data = file.crypto._replace(file_size=file_size)
        self.downloader.register(scrape_item.url, decrypt_data)
        file_url = self.parse_url(file_data["g"])
        attribs_bytes = mega.base64_url_decode(file_data["at"])
        filename = mega.decrypt_attr(attribs_bytes, file.crypto.k)["n"]
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=file_url)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str, shared_key: str) -> None:
        canonical_url = PRIMARY_URL / "folder" / folder_id / shared_key
        scrape_item.url = canonical_url
        nodes = await self.downloader.api.get_nodes_public_folder(folder_id, shared_key)
        root_id = next(iter(nodes))
        folder_name = nodes[root_id]["attributes"]["n"]
        filesystem = await self.downloader.api._build_file_system(nodes, [root_id])
        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)

        processed_files = 0
        for path, node in filesystem.items():
            if node["t"] != NodeType.FILE:
                continue

            file = cast("File", node)
            file_id = file["h"]
            canonical_url = PRIMARY_URL / "file" / file_id / shared_key
            new_scrape_item = scrape_item.create_child(canonical_url)
            for part in path.parent.parts[1:]:
                new_scrape_item.add_to_parent_title(part)

            file = FileTuple(file_id, DecryptData(file["iv"], file["k_decrypted"], file["meta_mac"]))
            self.manager.task_group.create_task(self._process_file(new_scrape_item, file, folder_id=folder_id))
            processed_files += 1
            if processed_files >= 10:
                processed_files = 0
                await asyncio.sleep(0)
            scrape_item.add_children()

    @error_handling_wrapper
    async def login(self, *_) -> None:
        # This takes a really long times (dozens of seconds)
        # TODO: Add a way to cache this login
        # TODO: Show some logging message / UI about login
        try:
            await self.downloader.api.login(self.user, self.password)
        except Exception as e:
            self.disabled = True
            raise LoginError(f"[MegaNZ] {e}") from e
