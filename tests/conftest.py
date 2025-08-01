from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper import scrape_mapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    class Config(pytest.Config):  # type: ignore
        test_crawlers_domains: set[str]


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--test-crawlers",
        action="store",
        help="A comma-separated list of crawlers' domains (e.g., 'dropbox.com,jpg5.su').",
        default="",
    )


def pytest_configure(config: Config):
    config.test_crawlers_domains = {
        domain for item in config.getoption("--test-crawlers").split(",") if (domain := item.strip())
    }


def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]) -> None:
    """When running with --test-crawlers, disable all other tests"""
    if not config.test_crawlers_domains:
        return

    selected_tests = []
    deselected_tests = []
    for item in items:
        markers = {marker.name for marker in item.iter_markers()}

        if "crawler_test_case" in markers:
            selected_tests.append(item)
        else:
            deselected_tests.append(item)

    if deselected_tests:
        config.hook.pytest_deselected(items=deselected_tests)
        items[:] = selected_tests


@pytest.fixture
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
async def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(10)
    return caplog


@pytest.fixture(scope="function", name="manager")
def post_startup_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Manager:
    appdata = str(tmp_path)
    downloads = str(tmp_path / "Downloads")
    monkeypatch.chdir(tmp_path)
    bare_manager = Manager(("--appdata-folder", appdata, "-d", downloads))
    bare_manager.startup()
    bare_manager.path_manager.startup()
    bare_manager.log_manager.startup()
    return bare_manager


@pytest.fixture(scope="function")
async def running_manager(manager: Manager) -> AsyncGenerator[Manager]:
    scrape_mapper.existing_crawlers.clear()
    await manager.async_startup()
    manager.states.RUNNING.set()
    yield manager
    manager.states.RUNNING.clear()
    await manager.close()
