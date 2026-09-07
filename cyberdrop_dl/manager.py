from __future__ import annotations

import contextlib
import datetime
import logging
import os
import sys
import time
from typing import TYPE_CHECKING, Any, Self, final

from cyberdrop_dl import __version__, aio, dependencies, env, ffmpeg, stats
from cyberdrop_dl.cache import cache_context
from cyberdrop_dl.clients.downloads import DownloadClient
from cyberdrop_dl.clients.http import HTTPClient
from cyberdrop_dl.config import Config
from cyberdrop_dl.config.appdata import AppData
from cyberdrop_dl.database import Database
from cyberdrop_dl.dedupe import Czkawka
from cyberdrop_dl.hasher import Hasher
from cyberdrop_dl.logs import LoggerAdapter, capture_logs, log_spacer
from cyberdrop_dl.models.validators import bytesize_to_str
from cyberdrop_dl.progress import REFRESH_RATE, TUI_DISABLED
from cyberdrop_dl.signature import simple_repr
from cyberdrop_dl.sorter import Sorter
from cyberdrop_dl.utils import enter_context, get_system_information

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from cyberdrop_dl.commands import CLIarguments
    from cyberdrop_dl.scrape_mapper import ScrapeMapper, ScrapeStats
    from cyberdrop_dl.url_objects import MediaItem


logger = LoggerAdapter(logging.getLogger(__name__), extra={"cdl_no_truncate": True})


@final
class Manager:
    def __init__(
        self,
        cli_args: CLIarguments | None = None,
        appdata: AppData | None = None,
        config: Config | None = None,
    ) -> None:
        from cyberdrop_dl.commands import CLIarguments

        self.cache: dict[str, Any] = {}
        self._appdata: AppData | None = appdata
        self.cli_args: CLIarguments = cli_args or CLIarguments()
        self._config: Config | None = config

        self._completed_downloads: list[MediaItem] = []
        self._hasher: Hasher | None = None

        self.http_client = HTTPClient(self.config)

        self.download_client: DownloadClient = DownloadClient(self)
        self.scrape_mapper: ScrapeMapper
        self.database: Database
        self.deduper: Czkawka
        self.sorter: Sorter
        self.exit_stack: contextlib.ExitStack = contextlib.ExitStack()

    __repr__ = simple_repr("cli_args", "_config", "http_client", "download_client")

    @property
    def hasher(self) -> Hasher:
        if self._hasher is None:
            self._hasher = self.exit_stack.enter_context(Hasher.create(self.config, self.database))
        return self._hasher

    @property
    def appdata(self) -> AppData:
        if self._appdata is None:
            self._appdata = AppData.default()
        return self._appdata

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = Config.from_file(self.appdata.config_file)
        return self._config

    def __resolve_paths(self) -> None:
        self.appdata.mkdirs()
        self.config.resolve_paths()

    @contextlib.contextmanager
    def __call__(self) -> Generator[Self]:
        self.__resolve_paths()
        self.database = Database(self.appdata.db_file, self.config.ignore_history)
        self.deduper = Czkawka.from_manager(self)
        self.sorter = Sorter.from_config(self.config)
        with (
            self.exit_stack,
            cache_context(self.appdata.cache_file, self.cache),
            enter_context(REFRESH_RATE, self.config.ui.refresh_rate),
            enter_context(TUI_DISABLED, self.config.ui.mode.is_disabled),
        ):
            try:
                yield self
            finally:
                del self.deduper
                del self.sorter

    def add_completed(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        self._completed_downloads.append(media_item)

    @property
    def completed_downloads(self) -> list[MediaItem]:
        return self._completed_downloads

    def log_config_settings(self) -> None:
        logger.info(f"Running cyberdrop-dl v{__version__}")
        _log_enviroment()
        logger.debug({"CLI options": self.cli_args.__json__()})
        _log_config(self.config)
        _log_ffmpeg()
        _log_database(self.appdata.db_file)
        _log_dependencies()

    def print_stats(self, stats: ScrapeStats) -> str:
        if not self.config.ui.show_stats:
            return ""

        log_spacer()

        with capture_logs() as stream:
            self.__print_stats(stats)

        return stream.getvalue()

    def __print_stats(self, scrape_stats: ScrapeStats) -> None:

        elapsed = datetime.timedelta(seconds=int(time.monotonic() - scrape_stats.start_time))
        total_data_written = bytesize_to_str(self.scrape_mapper.tui.downloads.bytes_downloaded)

        logger.info("Run Stats:", extra={"color": "cyan"})
        logger.info(f"  Config file: {self.config.source}")
        logger.info(f"  URLs source: {scrape_stats.source}")
        logger.info(f"  URLs: {scrape_stats.count:,}")
        logger.info(f"  URL groups: {len(scrape_stats.unique_groups):,}")
        logger.info(f"  Logs folder: {self.config.logs.effective_log_folder}")
        logger.info(f"  Total runtime: {elapsed}")
        logger.info(f"  Total downloaded data: {total_data_written}")

        if scrape_stats.domain_stats:
            log_spacer()
            logger.info("URLs by domain (includes children):", extra={"color": "cyan"})

            def lines() -> Generator[str]:
                for domain, count in sorted(scrape_stats.domain_stats.items()):
                    yield f" - {domain}: {count:,}"

            logger.info("\n".join(lines()))

        stats.print(self.scrape_mapper.tui.files.stats)
        stats.print(self.scrape_mapper.tui.scrape_errors)
        stats.print(self.hasher.stats)
        stats.print(self.deduper.stats)
        stats.print(self.sorter.stats)
        stats.print_errors(
            tuple(self.scrape_mapper.tui.scrape_errors),
            tuple(self.scrape_mapper.tui.download_errors),
        )

    async def get_cookie_files(self) -> list[Path]:
        path = self.config.cookies
        if not path:
            return []

        if await aio.is_file(path):
            return [path]

        if await aio.is_dir(path):
            return [f async for f in aio.glob(path, "*.txt")]

        return []


def _log_dependencies() -> None:
    if not env.DEBUG_MODE:
        return
    logger.debug({"dependencies": dict(dependencies())})


def _log_database(path: Path) -> None:
    try:
        db_size = path.stat().st_size
    except FileNotFoundError:
        db_size = 0

    logger.debug("Database file: %s (%s)", path, bytesize_to_str(db_size))


def _log_enviroment() -> None:
    logger.debug(
        {
            "System": get_system_information(),
            "Enviroment": env.ALL_VARS,
            "Enviroment resolved": env.ALL_VARS_RESOLVED,
            "argv": sys.argv[1:],
        }
    )


def _log_config(config: Config) -> None:
    logger.debug("Config file: %s", config.source)
    logger.debug("Auth: \n%s", config.auth.censored_dump())
    logger.debug(config.model_dump_json(exclude={"auth"}, indent=2))


def _log_ffmpeg() -> None:
    if not ffmpeg.is_installed():
        msg = "ffmpeg is not installed. HLS downloads will fail"
        if os.name == "nt":
            msg += ". Get it from: https://www.gyan.dev/ffmpeg/builds/"

        logger.warning(msg)
        return

    logger.debug(
        {
            "ffmpeg": {"binary": ffmpeg.which_ffmpeg(), "version": ffmpeg.version()},
            "ffprobe": {"binary": ffmpeg.which_ffprobe(), "version": ffmpeg.ffprobe_version()},
        }
    )
