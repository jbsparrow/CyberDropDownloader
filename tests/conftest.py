from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl.config.appdata import AppData, AppDirs
from cyberdrop_dl.manager import Manager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator
    from pathlib import Path

if TYPE_CHECKING:

    class PyTestConfig(pytest.Config):  # pyright: ignore[reportGeneralTypeIssues]
        test_crawlers_domains: set[str]  # pyright: ignore[reportUninitializedInstanceVariable]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--test-crawlers",
        action="store",
        help="A comma-separated list of crawlers' domains (e.g., 'dropbox.com,jpg5.su').",
        default="",
    )


def pytest_configure(config: PyTestConfig) -> None:
    config.test_crawlers_domains = {
        domain for item in (config.getoption("--test-crawlers") or "").split(",") if (domain := item.strip())
    }


def pytest_collection_modifyitems(config: PyTestConfig, items: list[pytest.Item]) -> None:
    """When running with --test-crawlers, disable all other tests"""
    if not config.test_crawlers_domains:
        return

    selected_tests: list[pytest.Item] = []
    deselected_tests: list[pytest.Item] = []
    for item in items:
        markers = {marker.name for marker in item.iter_markers()}

        if "crawler_test_case" in markers:
            selected_tests.append(item)
        else:
            deselected_tests.append(item)

    if deselected_tests:
        config.hook.pytest_deselected(items=deselected_tests)
        items[:] = selected_tests


@pytest.fixture(autouse=True)
def tmp_cwd(tmp_path: Path) -> Generator[Path]:
    with pytest.MonkeyPatch.context() as m:
        m.chdir(tmp_path)
        yield tmp_path


@pytest.fixture
async def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(10)
    return caplog


@pytest.fixture
def appdata(tmp_cwd: Path) -> AppData:
    return AppData.from_dirs(AppDirs.from_path(tmp_cwd / "pytest_appdata"))


@pytest.fixture
def manager(appdata: AppData) -> Generator[Manager]:
    with Manager(appdata=appdata)() as manager:
        yield manager


@pytest.fixture
async def running_manager(manager: Manager) -> AsyncGenerator[Manager]:
    async with manager.database:
        yield manager
