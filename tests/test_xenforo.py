from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from cyberdrop_dl.crawlers.xenforo import xenforo
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.managers.manager import Manager


@pytest.fixture(name="manager")
async def post_startup_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Manager]:
    appdata = str(tmp_path)
    downloads = str(tmp_path / "Downloads")
    monkeypatch.chdir(tmp_path)
    manager = Manager(("--appdata-folder", appdata, "-d", downloads))
    manager.startup()
    manager.path_manager.startup()
    manager.log_manager.startup()
    await manager.async_startup()
    yield manager
    await manager.async_db_close()
    await manager.close()


# "https://simpcity.su/watched/threads"
# "https://simpcity.su/forums/simpcity-news-rules-and-faq.6/""


@pytest.mark.parametrize(
    ("url", "thread_part_name", "result", "canonical_url"),
    [
        [
            "https://simpcity.su/threads/general-support.208041/page-260#post-23934165",
            "threads",
            (
                "general-support",
                208041,
                260,
                23934165,
            ),
            "https://simpcity.su/threads/general-support.208041",
        ],
        [
            "https://celebforum.to/threads/infos-regelaenderungen.18821/page-3",
            "threads",
            (
                "infos-regelaenderungen",
                18821,
                3,
                None,
            ),
            "https://celebforum.to/threads/infos-regelaenderungen.18821",
        ],
        [
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
            "topic",
            (
                "the-official-victorias-secret-thread",
                27120,
                0,
                None,
            ),
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
        ],
        [
            "https://forums.socialmediagirls.com/threads/forum-rules.14/post-34",
            "threads",
            (
                "forum-rules",
                14,
                0,
                34,
            ),
            "https://forums.socialmediagirls.com/threads/forum-rules.14",
        ],
        [
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901/post-3942103",
            "threads",
            (
                "should-we-ban-gofile-76-5-say-no",
                436901,
                0,
                3942103,
            ),
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901",
        ],
        [
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930/page-11/#post-2070848",
            "threads",
            (
                "en-fr-tools-to-download-upload-content-websites-softwares-extensions",
                13930,
                11,
                2070848,
            ),
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930",
        ],
        [
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236/post-2726083",
            "threads",
            (
                "mod-uploading-rules-12-02-2018",
                9236,
                0,
                2726083,
            ),
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236",
        ],
    ],
)
def test_parse_thread_info(
    manager: Manager, url: str, thread_part_name: str, result: tuple[str, int, int, int], canonical_url: str
) -> None:
    url_, canonical_url_ = AbsoluteHttpURL(url), AbsoluteHttpURL(canonical_url)
    result_ = xenforo.ThreadInfo(*result, canonical_url_, url_)
    parsed = xenforo.parse_thread_info(url_, thread_part_name, "page", "post")
    assert result_ == parsed
