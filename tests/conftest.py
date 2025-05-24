from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scrape_mapper import ScrapeMapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator
    from pathlib import Path

    from _pytest.nodes import Node  # type: ignore


@pytest.fixture
def unique_tmp_dir(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    node: pytest.Function = request.node
    test_name = node.originalname
    num = 0
    test_specific_dir = tmp_path.parent / f"cdl_{test_name}.{num}"
    while test_specific_dir.exists():
        num += 1
        test_specific_dir = test_specific_dir.with_suffix(f".{num}")

    test_specific_dir.mkdir(exist_ok=True)
    return test_specific_dir


@pytest.fixture
def tmp_cwd(unique_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(unique_tmp_dir)
    return unique_tmp_dir


@pytest.fixture
def custom_sys_argv(request: pytest.FixtureRequest) -> list[str]:
    args = ["pytest"]
    node: Node = request.node
    if marker := node.get_closest_marker("sys_args"):
        assert marker.args
        assert isinstance(marker.args[0], list)
        return args + marker.args[0]

    return args


@pytest.fixture
def bare_manager(tmp_cwd, custom_sys_argv: list[str]) -> Generator[Manager]:
    with pytest.MonkeyPatch.context() as mocker:
        mocker.setattr("sys.argv", custom_sys_argv)
        manager = Manager()
        yield manager


@pytest.fixture()
def sync_manager(bare_manager: Manager) -> Generator[Manager]:
    bare_manager.startup()
    bare_manager.path_manager.startup()
    bare_manager.log_manager.startup()
    assert not bare_manager.log_manager.main_log.exists()
    yield bare_manager


@pytest.fixture
async def async_manager(sync_manager: Manager) -> AsyncGenerator[Manager]:
    await sync_manager.async_startup()
    yield sync_manager
    await sync_manager.close()


@pytest.fixture
async def scrape_and_manager(async_manager: Manager) -> AsyncGenerator[tuple[ScrapeMapper, Manager]]:
    async_manager.states.RUNNING.set()
    scrape_mapper = ScrapeMapper(async_manager)
    async with asyncio.TaskGroup() as task_group:
        async_manager.task_group = task_group
        yield scrape_mapper, async_manager


@pytest.fixture
async def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(10)
    return caplog
