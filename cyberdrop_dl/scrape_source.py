from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cyberdrop_dl import aio
from cyberdrop_dl.url_objects import AbsoluteHttpURL, RetryInfo, ScrapeItem
from cyberdrop_dl.utils.dataclass import deserialize

if TYPE_CHECKING:
    import datetime
    from collections.abc import AsyncGenerator, Generator, Iterable, Mapping

    import aiosqlite

logger = logging.getLogger(__name__)

_FETCH_MANY_SIZE = 1000
_REGEX_LINKS = re.compile(r"(?:http.*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]))")

type URLsSource = Path | Iterable[AbsoluteHttpURL | Path]


class RetryQuery(StrEnum):
    FAILED = """
    SELECT domain, url_path, referer, download_path, download_filename FROM media
    WHERE
      completed = 0 AND created_at BETWEEN ? AND ?
    ORDER BY
      created_at DESC;
    """

    ALL = """
    SELECT domain, url_path, referer, download_path, download_filename FROM media
    WHERE
      created_at BETWEEN ? AND ?
    ORDER BY
      created_at DESC;
    """


class RetrySource(StrEnum):
    FAILED = "retry failed"
    ALL = "retry all"


@dataclasses.dataclass(slots=True, frozen=True)
class RetryScrapeSource:
    source: RetrySource
    after: datetime.date
    before: datetime.date


async def load_items_from_path(path: Path) -> AsyncGenerator[ScrapeItem]:
    gen_fn = load_items_from_file if await aio.is_file(path) else load_items_from_folder
    async with contextlib.aclosing(gen_fn(path)) as items:
        async for item in items:
            yield item


async def load_items_from_folder(path: Path) -> AsyncGenerator[ScrapeItem]:
    files = sorted(
        [f async for f in aio.glob(path, "*.txt") if not f.name.startswith(".")], key=lambda x: str(x).casefold()
    )
    for file in files:
        async with contextlib.aclosing(_parse_input_file_groups(file)) as lines:
            async for group_name, urls in lines:
                for url in urls:
                    item = ScrapeItem.from_url(url)
                    item.append_folders(file.stem)
                    item.part_of_album = True
                    if group_name:
                        item.append_folders(group_name)
                    yield item


async def load_items_from_file(file: Path) -> AsyncGenerator[ScrapeItem]:
    async with contextlib.aclosing(_parse_input_file_groups(file)) as lines:
        async for group_name, urls in lines:
            for url in urls:
                item = ScrapeItem.from_url(url)
                if group_name:
                    item.append_folders(group_name)
                    item.part_of_album = True
                yield item


async def _parse_input_file_groups(input_file: Path) -> AsyncGenerator[tuple[str, list[AbsoluteHttpURL]]]:
    if not await aio.is_file(input_file):
        yield ("", [])
        return

    block_quote = False
    ignored_urls = 0
    current_group_name = ""
    async with aio.open(input_file, encoding="utf8") as f:
        async for line in f:
            if line.startswith(("---", "===")):  # New group begins here
                current_group_name = line.replace("---", "").replace("===", "").strip()

            if current_group_name:
                yield (current_group_name, list(_regex_links(line)))
                continue

            if line == "#\n":  # A block quote begins or ends here
                block_quote = not block_quote
                ignored_urls = 0

            if not block_quote:
                yield ("", list(_regex_links(line)))
            else:
                ignored_urls += sum(1 for _ in _regex_links(line))

    if block_quote and ignored_urls:
        logger.warning(
            "Block comment in %s was never closed: %s URL(s) after its opening '#' line were ignored. "
            "Add a line with only '#' where the comment should end",
            input_file,
            ignored_urls,
        )


async def load_items_from_iterable(items: Iterable[AbsoluteHttpURL | Path]) -> AsyncGenerator[ScrapeItem]:
    paths: list[Path] = []
    for url in items:
        if isinstance(url, Path):
            paths.append(url)
            continue
        yield ScrapeItem.from_url(url)

    if not paths:
        return

    for path in sorted(paths, key=lambda x: str(x).casefold()):
        async with contextlib.aclosing(load_items_from_file(path)) as p_items:
            async for item in p_items:
                yield item


def _regex_links(line: str) -> Generator[AbsoluteHttpURL]:
    """Regex grab the links from the URLs.txt file.

    This allows code blocks or full paragraphs to be copy and pasted into the URLs.txt.
    """

    line = line.strip()
    if line.startswith("#"):
        return

    http_urls = (url.group().replace(".md.", ".") for url in re.finditer(_REGEX_LINKS, line))
    for link in http_urls:
        try:
            encoded = "%" in link
            yield AbsoluteHttpURL(link, encoded=encoded)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unable to parse URL from input file: {link} {e:!r}")


async def load_items_from_db(
    db_conn: aiosqlite.Connection,
    query: RetryQuery,
    *,
    after: datetime.date,
    before: datetime.date,
) -> AsyncGenerator[ScrapeItem]:
    cursor = await db_conn.execute(query, (after.isoformat(), before.isoformat()))
    while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
        for row in rows:
            yield _create_item_from_row(dict(row))


def _create_item_from_row(row: Mapping[str, Any]) -> ScrapeItem:
    referer: str = row["referer"]
    url = AbsoluteHttpURL(referer, encoded="%" in referer)
    item = ScrapeItem.from_url(url)
    item.part_of_album = True
    item.retry_info = deserialize(RetryInfo, dict(row), referer=url, download_path=Path(row["download_path"]))
    return item
