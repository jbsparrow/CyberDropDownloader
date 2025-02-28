from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import field
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING

from pydantic import ByteSize
from rich.columns import Columns
from rich.console import Group
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from cyberdrop_dl.ui.progress.downloads_progress import DownloadsProgress
from cyberdrop_dl.ui.progress.file_progress import FileProgress
from cyberdrop_dl.ui.progress.hash_progress import HashProgress
from cyberdrop_dl.ui.progress.scraping_progress import ScrapingProgress
from cyberdrop_dl.ui.progress.sort_progress import SortProgress
from cyberdrop_dl.ui.progress.statistic_progress import DownloadStatsProgress, ScrapeStatsProgress
from cyberdrop_dl.utils.logger import log, log_spacer, log_with_color

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from rich.console import RenderableType

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.ui.progress.statistic_progress import UiFailureTotal

log_cyan = partial(log_with_color, style="cyan", level=20)
log_yellow = partial(log_with_color, style="yellow", level=20)
log_green = partial(log_with_color, style="green", level=20)
log_red = partial(log_with_color, style="red", level=20)


class ProgressManager:
    def __init__(self, manager: Manager) -> None:
        # File Download Bars
        self.manager = manager
        ui_options = manager.config_manager.global_settings_data.ui_options
        self.portrait = manager.parsed_args.cli_only_args.portrait
        self.file_progress = FileProgress(manager)
        self.scraping_progress = ScrapingProgress(manager)

        # Overall Progress Bars & Stats
        self.download_progress = DownloadsProgress(manager)
        self.download_stats_progress = DownloadStatsProgress()
        self.scrape_stats_progress = ScrapeStatsProgress()
        self.hash_progress = HashProgress(manager)
        self.sort_progress = SortProgress(1, manager)

        self.ui_refresh_rate = ui_options.refresh_rate

        self.hash_remove_layout: RenderableType = field(init=False)
        self.hash_layout: RenderableType = field(init=False)
        self.sort_layout: RenderableType = field(init=False)
        self.status_message: Progress = field(init=False)
        self.status_message_task_id: TaskID = field(init=False)

    @asynccontextmanager
    async def show_status_msg(self, msg: str | None) -> AsyncGenerator:
        try:
            self.status_message.update(self.status_message_task_id, description=msg, visible=bool(msg))
            yield
        finally:
            self.status_message.update(self.status_message_task_id, visible=False)

    def startup(self) -> None:
        """Startup process for the progress manager."""
        spinner = SpinnerColumn(style="green", spinner_name="dots")
        text_placeholder = TextColumn("Running Cyberdrop-DL")
        activity_placeholder = Progress(spinner, text_placeholder)
        activity_placeholder.add_task("running with no UI", total=100, completed=0)
        self.status_message = Progress(spinner, "[progress.description]{task.description}")

        self.status_message_task_id = self.status_message.add_task("", total=100, completed=0, visible=False)

        simple_layout = Group(activity_placeholder, self.download_progress.simple_progress)

        status_message_columns = Columns([activity_placeholder, self.status_message], expand=False)

        horizontal_layout = Layout()
        vertical_layout = Layout()

        upper_layouts = (
            Layout(renderable=self.download_progress.get_progress(), name="Files", ratio=1, minimum_size=9),
            Layout(renderable=self.scrape_stats_progress.get_progress(), name="Scrape Failures", ratio=1),
            Layout(renderable=self.download_stats_progress.get_progress(), name="Download Failures", ratio=1),
        )

        lower_layouts = (
            Layout(renderable=self.scraping_progress.get_renderable(), name="Scraping", ratio=20),
            Layout(renderable=self.file_progress.get_renderable(), name="Downloads", ratio=20),
            Layout(renderable=status_message_columns, name="status_message", ratio=2),
        )

        horizontal_layout.split_column(Layout(name="upper", ratio=20), *lower_layouts)
        vertical_layout.split_column(Layout(name="upper", ratio=60), *lower_layouts)

        horizontal_layout["upper"].split_row(*upper_layouts)
        vertical_layout["upper"].split_column(*upper_layouts)

        self.horizontal_layout = horizontal_layout
        self.vertical_layout = vertical_layout
        self.activity_layout = activity_placeholder
        self.simple_layout = simple_layout
        self.hash_remove_layout = self.hash_progress.get_removed_progress()
        self.hash_layout = self.hash_progress.get_renderable()
        self.sort_layout = self.sort_progress.get_renderable()

    @property
    def fullscreen_layout(self) -> Layout:
        if self.portrait:
            return self.vertical_layout
        return self.horizontal_layout

    def print_stats(self, start_time: float) -> None:
        """Prints the stats of the program."""
        if not self.manager.parsed_args.cli_only_args.print_stats:
            return
        end_time = time.perf_counter()
        runtime = timedelta(seconds=int(end_time - start_time))
        data_size = ByteSize(self.file_progress.downloaded_data).human_readable(decimal=True)

        log_spacer(20)
        log("Printing Stats...\n", 20)
        config_path = self.manager.path_manager.config_folder / self.manager.config_manager.loaded_config
        config_path_text = get_console_hyperlink(config_path, text=self.manager.config_manager.loaded_config)
        input_file_text = get_input(self.manager)
        log_folder_text = get_console_hyperlink(self.manager.path_manager.log_folder)
        log_cyan(f"Run Stats (config: {config_path_text}):", markup=True)
        log_yellow(f"  Log Folder: {log_folder_text}", markup=True)
        log_yellow(f"  Input File: {input_file_text}", markup=True)
        log_yellow(f"  Input URLs: {self.manager.scrape_mapper.count:,}")
        log_yellow(f"  Input URL Groups: {self.manager.scrape_mapper.group_count:,}")
        log_yellow(f"  Total Runtime: {runtime}")
        log_yellow(f"  Total Downloaded Data: {data_size}")

        log_spacer(20, "")
        log_cyan("Download Stats:")
        log_green(f"  Downloaded: {self.download_progress.completed_files:,} files")
        log_yellow(f"  Skipped (By Config): {self.download_progress.skipped_files:,} files")
        log_yellow(f"  Skipped (Previously Downloaded): {self.download_progress.previously_completed_files:,} files")
        log_red(f"  Failed: {self.download_stats_progress.failed_files:,} files")

        log_spacer(20, "")
        log_cyan("Unsupported URLs Stats:")
        log_yellow(f"  Sent to Jdownloader: {self.scrape_stats_progress.sent_to_jdownloader:,}")
        log_yellow(f"  Skipped: {self.scrape_stats_progress.unsupported_urls_skipped:,}")

        log_spacer(20, "")
        log_cyan("Dupe Stats:")
        log_yellow(f"  Newly Hashed: {self.hash_progress.hashed_files:,} files")
        log_yellow(f"  Previously Hashed: {self.hash_progress.prev_hashed_files:,} files")
        log_yellow(f"  Removed (Downloads): {self.hash_progress.removed_files:,} files")

        log_spacer(20, "")
        log_cyan("Sort Stats:")
        log_green(f"  Audios: {self.sort_progress.audio_count:,}")
        log_green(f"  Images: {self.sort_progress.image_count:,}")
        log_green(f"  Videos: {self.sort_progress.video_count:,}")
        log_green(f"  Other Files: {self.sort_progress.other_count:,}")

        last_padding = log_failures(self.scrape_stats_progress.return_totals(), "Scrape Failures:")
        log_failures(self.download_stats_progress.return_totals(), "Download Failures:", last_padding)


def log_failures(failures: list[UiFailureTotal], title: str = "Failures:", last_padding: int = 0) -> int:
    log_spacer(20, "")
    log_cyan(title)
    if not failures:
        log_green("  None")
        return 0
    error_padding = last_padding
    error_codes = [f.error_code for f in failures if f.error_code is not None]
    if error_codes:
        error_padding = max(len(str(max(error_codes))), error_padding)
    for f in failures:
        error = f.error_code if f.error_code is not None else ""
        log_red(f"  {error:>{error_padding}}{' ' if error_padding else ''}{f.msg}: {f.count:,}")
    return error_padding


def get_input(manager: Manager) -> str:
    if manager.parsed_args.cli_only_args.retry_all:
        return "--retry-all"
    if manager.parsed_args.cli_only_args.retry_failed:
        return "--retry-failed"
    if manager.parsed_args.cli_only_args.retry_maintenance:
        return "--retry-maintenance"
    if manager.scrape_mapper.using_input_file:
        return get_console_hyperlink(manager.path_manager.input_file)
    return "--links (CLI args)"


def get_console_hyperlink(file_path: Path, text: str = "") -> str:
    full_path = file_path.resolve()
    show_text = text or full_path
    return f"[link=file://{full_path}]{show_text}[/link]"
