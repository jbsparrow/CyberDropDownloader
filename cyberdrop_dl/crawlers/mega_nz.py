"""Crawler to download files and folders from mega.nz

This crawler does several CPU intensive operations

It calls checks_complete_by_referer several times even if no request is going to be made, to skip unnecesary compute time
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.downloader import mega_nz as mega
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://mega.nz")


class FileTuple(NamedTuple):
    id: str
    crypto: mega.DecryptData


class MegaNzCrawler(Crawler):
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
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    SKIP_PRE_CHECK: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "mega.nz"
    FOLDER_DOMAIN: ClassVar[str] = "MegaNz"

    def __post_init__(self) -> None:
        self.downloader: mega.MegaDownloader

    @property
    def user(self) -> str | None:
        return self.manager.auth_config.meganz.email or None

    @property
    def password(self) -> str | None:
        return self.manager.auth_config.meganz.password or None

    def _init_downloader(self) -> mega.MegaDownloader:
        self.downloader = dl = mega.MegaDownloader(self.manager, self.DOMAIN)
        dl.startup()
        return dl

    async def async_startup(self) -> None:
        await self.login(PRIMARY_URL)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self.logged_in:
            return

        if frag := scrape_item.url.fragment:  # Mega stores access key in fragment. We can't do anything without the key
            # v1 URLs
            if frag.count("!") == 2:
                if frag.startswith("F!"):
                    folder_id, _, shared_key = frag.removeprefix("F!").partition("!")
                    return await self.folder(scrape_item, folder_id, shared_key)
                if frag.startswith("!"):
                    # https://mega.nz/#!Ue5VRSIQ!kC2E4a4JwfWWCWYNJovGFHlbz8F
                    file_id, _, shared_key = frag.removeprefix("!").partition("!")
                    return await self.file(scrape_item, file_id, shared_key)

            # v2 URLs
            match scrape_item.url.parts[1:]:
                # https://mega.nz/folder/oZZxyBrY#oU4jASLPpJVvqGHJIMRcgQ/file/IYZABDGY
                # https://mega.nz/folder/oZZxyBrY#oU4jASLPpJVvqGHJIMRcgQ
                case ["folder", folder_id]:
                    root_id = file_id = None
                    shared_key, *rest = frag.split("/")
                    if rest:
                        match rest:
                            case ["folder", id_]:
                                root_id = id_
                            case ["file", id_]:
                                file_id = id_
                            case _:
                                raise ValueError
                    return await self.folder(scrape_item, folder_id, shared_key, root_id or None, file_id or None)
                # https://mega.nz/file/cH51DYDR#qH7QOfRcM-7N9riZWdSjsRq
                case ["file", file_id]:
                    return await self.file(scrape_item, file_id, frag)

        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str, shared_key: str) -> None:
        canonical_url = (PRIMARY_URL / "file" / file_id).with_fragment(shared_key)
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url
        full_key = mega.base64_to_a32(shared_key)
        crypto = mega.get_decrypt_data(mega.NodeType.FILE, full_key)
        file = FileTuple(file_id, crypto)
        await self._process_file(scrape_item, file)

    @error_handling_wrapper
    async def _process_file(self, scrape_item: ScrapeItem, file: FileTuple, *, folder_id: str | None = None) -> None:
        file_data = await self._get_file_info(file.id, folder_id)
        decrypt_data = file.crypto._replace(file_size=file_data["s"])
        self.downloader.register(scrape_item.url, decrypt_data)
        file_url = self.parse_url(file_data["g"])
        attribs_bytes = mega.base64_url_decode(file_data["at"])
        filename = mega.decrypt_attr(attribs_bytes, file.crypto.k)["n"]
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=file_url)

    async def _get_file_info(self, file_id: str, folder_id: str | None) -> dict[str, Any]:
        data = {"a": "g", "g": 1}
        if folder_id:
            data = data | {"n": file_id}
            query_params = {"n": folder_id}
        else:
            data = data | {"p": file_id}
            query_params = None

        file_data: dict[str, Any] = await self.downloader.api.request(data, query_params)
        if "g" not in file_data:
            raise ScrapeError(410, "File not accessible anymore")
        return file_data

    @error_handling_wrapper
    async def folder(
        self,
        scrape_item: ScrapeItem,
        folder_id: str,
        shared_key: str,
        root_id: str | None = None,
        single_file_id: str | None = None,
    ) -> None:
        if single_file_id and await self.check_complete_from_referer(scrape_item.url):
            return
        nodes = await self.downloader.api.get_nodes_public_folder(folder_id, shared_key)
        root_id = root_id or next(iter(nodes))
        folder_name = nodes[root_id]["attributes"]["n"]
        filesystem = await self.downloader.api.build_file_system(nodes, [root_id])
        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)
        canonical_url = (PRIMARY_URL / "folder" / folder_id).with_fragment(shared_key)
        scrape_item.url = canonical_url
        await self._process_folder_fs(scrape_item, filesystem, single_file_id)

    async def _process_folder_fs(
        self, scrape_item: ScrapeItem, filesystem: dict[Path, mega.Node], single_file_id: str | None
    ) -> None:
        folder_id, shared_key = scrape_item.url.name, scrape_item.url.fragment
        processed_files = 0
        for path, node in filesystem.items():
            if node["t"] != mega.NodeType.FILE:
                continue

            file = cast("mega.File", node)
            file_id = file["h"]
            if single_file_id and file_id != single_file_id:
                continue
            file_fragment = f"{shared_key}/file/{file_id}"
            canonical_url = scrape_item.url.with_fragment(file_fragment)
            if not single_file_id and await self.check_complete_from_referer(canonical_url):
                continue
            new_scrape_item = scrape_item.create_child(canonical_url, possible_datetime=file["ts"])
            for part in path.parent.parts[1:]:
                new_scrape_item.add_to_parent_title(part)

            file = FileTuple(file_id, mega.DecryptData(file["k_decrypted"], file["iv"], file["meta_mac"]))
            self.manager.task_group.create_task(self._process_file(new_scrape_item, file, folder_id=folder_id))
            processed_files += 1
            if processed_files % 10 == 0:
                await asyncio.sleep(0)
            scrape_item.add_children()

    @error_handling_wrapper
    async def login(self, *_) -> None:
        # This takes a really long time (dozens of seconds)
        # TODO: Add a way to cache this login
        # TODO: Show some logging message / UI about login
        try:
            await self.downloader.api.login(self.user, self.password)
            self.logged_in = True
        except Exception as e:
            self.disabled = True
            raise LoginError(f"[MegaNZ] {e}") from e
