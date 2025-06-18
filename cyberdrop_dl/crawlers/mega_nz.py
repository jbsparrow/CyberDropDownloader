from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.downloader.mega_nz import (
    DecryptData,
    File,
    MegaApi,
    MegaDownloader,
    NodeType,
    base64_to_a32,
    base64_url_decode,
    decrypt_attr,
)
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://mega.nz")


class FileTuple(NamedTuple):
    id: str
    crypto: DecryptData


class MegaNzCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": ("/file/<handle>#<share_key>", "/!#<handle>!<share_key>"),
        "Folder": ("/folder/<handle>#<share_key>", "/!F#<handle>!<share_key>"),
        "**NOTE**": "Downloads can not be resumed. Partial downloads will always be deleted ans a new downloa dwill start from 0",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    SKIP_PRE_CHECK: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "mega.nz"
    FOLDER_DOMAIN: ClassVar[str] = "MegaNz"

    def __post_init__(self) -> None:
        self.api = MegaApi(self.manager)
        self.user = self.manager.config_manager.authentication_data.meganz.email or None
        self.password = self.manager.config_manager.authentication_data.meganz.password or None
        self.downloader: MegaDownloader

    async def startup(self) -> None:
        """Starts the crawler."""
        async with self.startup_lock:
            if self.ready:
                return
            self.client = self.manager.client_manager.scraper_session
            self.downloader = MegaDownloader(self.api, self.DOMAIN)
            self.downloader.startup()
            await self.async_startup()
            self.ready = True

    async def async_startup(self) -> None:
        await self.login(PRIMARY_URL)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.fragment:  # Mega stores access key in fragment. We can't do anything without the key
            if "file" in scrape_item.url.parts or scrape_item.url.fragment.startswith("!"):
                return await self.file(scrape_item)
            if "folder" in scrape_item.url.parts or scrape_item.url.fragment.startswith("F!"):
                return await self.folder(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if "file" in scrape_item.url.parts:
            # V2 URL structure, ex: https://mega.nz/file/cH51DYDR#qH7QOfRcM-7N9riZWdSjsRq
            file_id = scrape_item.url.name
            shared_key = scrape_item.url.fragment

        elif scrape_item.url.fragment.startswith("!"):
            # V1 URL structure, ex: https://mega.nz/#!Ue5VRSIQ!kC2E4a4JwfWWCWYNJovGFHlbz8F
            file_id, shared_key = scrape_item.url.fragment.rsplit("!", 1)
        else:
            raise ScrapeError(422)

        canonical_url = PRIMARY_URL / "file" / file_id / shared_key
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        file_key = base64_to_a32(shared_key)

        k: tuple[int, ...] = (
            file_key[0] ^ file_key[4],
            file_key[1] ^ file_key[5],
            file_key[2] ^ file_key[6],
            file_key[3] ^ file_key[7],
        )
        iv: tuple[int, ...] = (*file_key[4:6], 0, 0)
        meta_mac: tuple[int, ...] = file_key[6:8]
        file = FileTuple(file_id, DecryptData(iv, k, meta_mac))
        await self.proccess_file(scrape_item, file)

    async def proccess_file(self, scrape_item: ScrapeItem, file: FileTuple) -> None:
        file_data: dict[str, Any] = await self.api.request({"a": "g", "g": 1, "p": file.id})
        file_size: int = file_data["s"]
        if "g" not in file_data:
            raise ScrapeError(410, "File not accessible anymore")

        self.downloader.register(scrape_item.url, file.crypto.iv, file.crypto.k, file.crypto.meta_mac, file_size)
        file_url = self.parse_url(file_data["g"])
        attribs_bytes = base64_url_decode(file_data["at"])
        filename = decrypt_attr(attribs_bytes, file.crypto.k)["n"]
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=file_url)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        if "folder" in scrape_item.url.parts:
            folder_id = scrape_item.url.name
            shared_key = scrape_item.url.fragment

        elif scrape_item.url.fragment.startswith("!F"):
            folder_id, shared_key = scrape_item.url.fragment.removeprefix("F").rsplit("!", 1)
        else:
            raise ScrapeError(422)

        canonical_url = PRIMARY_URL / "folder" / folder_id / shared_key
        scrape_item.url = canonical_url
        nodes = await self.api.get_nodes_public_folder(folder_id, shared_key)
        root_id = next(iter(nodes))
        folder_name = nodes[root_id]["attributes"]["n"]
        filesystem = await self.api._build_file_system(nodes, [root_id])

        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)

        for path, node in filesystem.items():
            if node["t"] != NodeType.FILE:
                continue

            file = cast("File", node)
            file_id = file["h"]
            canonical_url = PRIMARY_URL / "file" / file_id / shared_key
            new_scrape_item = scrape_item.create_child(canonical_url)
            for part in path.parent.parts:
                if part != folder_name:
                    new_scrape_item.add_to_parent_title(part)

            file = FileTuple(file_id, DecryptData(file["iv"], file["k_decrypted"], file["meta_mac"]))
            await self.proccess_file(new_scrape_item, file)
            scrape_item.add_children()

    @error_handling_wrapper
    async def login(self, *_):
        await self.api.login(self.user, self.password)
