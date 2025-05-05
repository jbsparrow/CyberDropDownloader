import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

import pytest

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scrape_mapper import ScrapeMapper

if TYPE_CHECKING:
    from _pytest.nodes import Node  # type: ignore

ScrapeAndManager: TypeAlias = tuple[ScrapeMapper, Manager]


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
def bare_manager(tmp_path: Path, custom_sys_argv: list[str]) -> Generator[Manager]:
    with pytest.MonkeyPatch.context() as mocker:
        mocker.chdir(tmp_path)
        mocker.setattr("sys.argv", custom_sys_argv)
        manager = Manager()
        yield manager


@pytest.fixture()
def sync_manager(bare_manager: Manager) -> Generator[Manager]:
    bare_manager.startup()
    bare_manager.path_manager.startup()
    bare_manager.log_manager.startup()
    yield bare_manager


@pytest.fixture
async def async_manager(sync_manager: Manager) -> AsyncGenerator[Manager]:
    await sync_manager.async_startup()
    yield sync_manager
    await sync_manager.close()


@pytest.fixture
async def scrape_and_manager(async_manager: Manager) -> AsyncGenerator[ScrapeAndManager]:
    async_manager.states.RUNNING.set()
    scrape_mapper = ScrapeMapper(async_manager)
    async with asyncio.TaskGroup() as task_group:
        async_manager.task_group = task_group
        yield scrape_mapper, async_manager


@pytest.fixture
async def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(10)
    return caplog
