from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl import scrape_source

if TYPE_CHECKING:
    from pathlib import Path


async def _parse(file: Path) -> list[str]:
    return [str(url) async for _, urls in scrape_source._parse_input_file_groups(file) for url in urls]


@pytest.mark.parametrize(
    ("lines", "expected_urls", "expected_warning"),
    [
        (
            ["https://a.com/1", "#", "https://a.com/2", "#", "https://a.com/3"],
            ["https://a.com/1", "https://a.com/3"],
            None,
        ),
        (["# header", "#", "# more header", "https://a.com/1", "https://a.com/2"], [], "2 URL(s)"),
        (["https://a.com/1", "#", "# just a comment"], ["https://a.com/1"], None),
        (["# header", "https://a.com/1"], ["https://a.com/1"], None),
    ],
)
async def test_unclosed_block_comment_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    lines: list[str],
    expected_urls: list[str],
    expected_warning: str | None,
) -> None:
    file = tmp_path / "URLs.txt"
    file.write_text("\n".join(lines) + "\n", encoding="utf8")
    with caplog.at_level(logging.WARNING):
        assert await _parse(file) == expected_urls

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    warnings = [msg for msg in messages if "never closed" in msg]
    if expected_warning is None:
        assert not warnings
    else:
        assert len(warnings) == 1
        assert expected_warning in warnings[0]
