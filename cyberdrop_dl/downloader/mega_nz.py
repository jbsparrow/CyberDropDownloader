from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, final, override

from mega.chunker import MegaChunker, get_chunks

from cyberdrop_dl import aio, storage
from cyberdrop_dl.clients.downloads import DownloadClient, make_speed_checker
from cyberdrop_dl.downloader.http import Downloader

if TYPE_CHECKING:
    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.progress import ProgressHook
    from cyberdrop_dl.url_objects import MediaItem


@final
class MegaDownloadClient(DownloadClient):  # pyright: ignore[reportGeneralTypeIssues]
    SUPPORTS_RANGES: ClassVar[bool] = False

    @override
    async def _append_content(self, media_item: MediaItem, hook: ProgressHook, resp: AbstractResponse[Any]) -> None:
        """Appends content to a file."""

        check_free_space = storage.create_free_space_checker(media_item)
        check_download_speed = make_speed_checker(media_item, hook, self.download_speed_threshold)
        await check_free_space(media_item.size)
        await self._pre_download_check(media_item)

        crypto, file_size = media_item.extra_info[media_item.domain]["key"]
        chunk_decryptor = MegaChunker(crypto.key, crypto.iv, crypto.meta_mac)

        aiohttp_resp = resp.aiohttp_resp
        async with self._track_speed(hook), aio.open(media_item.partial_file, mode="ab") as f:
            for _, chunk_size in get_chunks(file_size):
                raw_chunk = await aiohttp_resp.content.readexactly(chunk_size)
                chunk = chunk_decryptor.read(raw_chunk)
                await check_free_space()
                chunk_size = len(chunk)

                await self.speed_limiter.acquire(chunk_size)
                await f.write(chunk)
                hook.advance(chunk_size)
                check_download_speed()

        await self._post_download_check(media_item)
        chunk_decryptor.check_integrity()

    @aio.to_thread
    def _pre_download_check(self, media_item: MediaItem) -> None:
        media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)
        media_item.partial_file.unlink(missing_ok=True)  # We can't resume
        media_item.partial_file.touch()


class MegaDownloader(Downloader):
    def __post_init__(self) -> None:
        super().__post_init__()
        self._client: MegaDownloadClient = MegaDownloadClient(self.manager)  # pyright: ignore[reportUninitializedInstanceVariable]

    @property
    @override
    def client(self) -> MegaDownloadClient:
        return self._client
