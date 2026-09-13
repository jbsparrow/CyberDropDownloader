from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Self
from unittest import mock

import pytest
from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl.clients.downloads import DownloadClient
from cyberdrop_dl.clients.response import AbstractResponse
from cyberdrop_dl.exceptions import DownloadError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from cyberdrop_dl.manager import Manager


_PAYLOAD = bytes(range(256)) * 4_000  # 1,024,000 bytes
_DOMAIN = "example"


class _FakeResponse(AbstractResponse[bytes]):
    __slots__ = ()

    async def _read(self) -> bytes:
        return self._resp

    async def _read_text(self, encoding: str | None = None) -> str:
        return self._resp.decode(encoding or "utf-8", errors="replace")

    async def iter_chunked(self, size: int) -> AsyncIterator[bytes]:
        for start in range(0, len(self._resp), size):
            yield self._resp[start : start + size]

    async def aclose(self) -> None:
        return None

    @classmethod
    def partial_content(cls, start: int, *, truncate_to: int | None = None) -> Self:
        body = _PAYLOAD[start:]
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(body)),
            "Content-Range": f"bytes {start}-{len(_PAYLOAD) - 1}/{len(_PAYLOAD)}",
        }
        return cls(
            content_type="video/mp4",
            status=206,
            headers=CIMultiDictProxy(CIMultiDict(headers)),
            url=AbsoluteHttpURL("https://cdn.example.com/video.mp4"),
            location=None,
            _resp=body[:truncate_to],
        )


class _Hook:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def advance(self, _: int) -> None:
        return None

    def get_speed(self) -> float:
        return 0


async def _resumable_item(manager: Manager, tmp_path: Path, resume_point: int) -> MediaItem:
    folder = tmp_path / "downloads"
    folder.mkdir()
    item = MediaItem(
        url=AbsoluteHttpURL("https://cdn.example.com/video.mp4"),
        domain=_DOMAIN,
        download_folder=folder,
        filename="video.mp4",
        db_path="/video.mp4",
        referer=AbsoluteHttpURL("https://example.com/v/1"),
        album_id=None,
        ext=".mp4",
        original_filename="video.mp4",
        uploaded_at=None,
    )
    item.download_filename = "video.mp4"
    await manager.database.history.insert_incompleted(_DOMAIN, item)

    item.partial_file = folder / "video.mp4.part"
    item.partial_file.write_bytes(_PAYLOAD[:resume_point])
    return item


@pytest.mark.parametrize("resume_pct", [0.2, 0.4, 0.6, 0.8])
async def test_resumed_download_keeps_partial_bytes(
    running_manager: Manager, tmp_path: Path, resume_pct: float
) -> None:
    resume_point = int(len(_PAYLOAD) * resume_pct)
    item = await _resumable_item(running_manager, tmp_path, resume_point)
    client = DownloadClient(running_manager)
    resp = _FakeResponse.partial_content(resume_point)
    with mock.patch.object(DownloadClient, "_make_hook", return_value=_Hook()):
        assert await client._process_response(item, _DOMAIN, resume_point, resp)

    data = item.partial_file.read_bytes()
    assert len(data) == len(_PAYLOAD)
    assert hashlib.sha256(data).digest() == hashlib.sha256(_PAYLOAD).digest()


async def test_truncated_resume_is_not_marked_complete(running_manager: Manager, tmp_path: Path) -> None:
    resume_point = int(len(_PAYLOAD) * 0.3)
    truncate_to = int(len(_PAYLOAD) * 0.5)
    item = await _resumable_item(running_manager, tmp_path, resume_point)
    client = DownloadClient(running_manager)
    resp = _FakeResponse.partial_content(resume_point, truncate_to=truncate_to)
    with (
        mock.patch.object(DownloadClient, "_make_hook", return_value=_Hook()),
        pytest.raises(DownloadError, match="Corrupted File"),
    ):
        await client._process_response(item, _DOMAIN, resume_point, resp)
