from __future__ import annotations

import time
from dataclasses import field
from datetime import timedelta
from typing import TYPE_CHECKING

from rich.layout import Layout

from cyberdrop_dl.ui.progress.downloads_progress import DownloadsProgress
from cyberdrop_dl.ui.progress.file_progress import FileProgress
from cyberdrop_dl.ui.progress.hash_progress import HashProgress
from cyberdrop_dl.ui.progress.scraping_progress import ScrapingProgress
from cyberdrop_dl.ui.progress.sort_progress import SortProgress
from cyberdrop_dl.ui.progress.statistic_progress import DownloadStatsProgress, ScrapeStatsProgress
from cyberdrop_dl.utils.logger import log, log_spacer, log_with_color
from cyberdrop_dl.utils.utilities import parse_bytes

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class ProgressManager:
    def __init__(self, manager: Manager) -> None:
        # File Download Bars
        self.manager = manager
        self.file_progress: FileProgress = FileProgress(
            manager.config_manager.global_settings_data["UI_Options"]["downloading_item_limit"],
            manager,
        )

        # Scraping Printout
        self.scraping_progress: ScrapingProgress = ScrapingProgress(
            manager.config_manager.global_settings_data["UI_Options"]["scraping_item_limit"],
            manager,
        )

        # Overall Progress Bars & Stats
        self.download_progress: DownloadsProgress = DownloadsProgress(manager)
        self.download_stats_progress: DownloadStatsProgress = DownloadStatsProgress()
        self.scrape_stats_progress: ScrapeStatsProgress = ScrapeStatsProgress()
        self.hash_progress: HashProgress = HashProgress(manager)
        self.sort_progress: SortProgress = SortProgress(1, manager)

        self.ui_refresh_rate = manager.config_manager.global_settings_data["UI_Options"]["refresh_rate"]

        self.layout: Layout = field(init=False)
        self.hash_remove_layout: Layout = field(init=False)
        self.hash_layout: Layout = field(init=False)
        self.sort_layout: Layout = field(init=False)

    def startup(self) -> None:
        """Startup process for the progress manager."""
        progress_layout = Layout()
        progress_layout.split_column(
            Layout(name="upper", ratio=2, minimum_size=8),
            Layout(renderable=self.scraping_progress.get_progress(), name="Scraping", ratio=2),
            Layout(renderable=self.file_progress.get_progress(), name="Downloads", ratio=2),
        )
        progress_layout["upper"].split_row(
            Layout(renderable=self.download_progress.get_progress(), name="Files", ratio=1),
            Layout(renderable=self.scrape_stats_progress.get_progress(), name="Scrape Failures", ratio=1),
            Layout(renderable=self.download_stats_progress.get_progress(), name="Download Failures", ratio=1),
        )

        hash_remove_layout = Layout()
        hash_remove_layout = self.hash_progress.get_removed_progress()

        self.layout = progress_layout
        self.hash_remove_layout = hash_remove_layout
        self.hash_layout = self.hash_progress.get_hash_progress()
        self.sort_layout = self.sort_progress.get_progress()

    def print_stats(self, start_time: timedelta | float) -> None:
        """Prints the stats of the program."""
        end_time = time.perf_counter()
        runtime = timedelta(seconds=int(end_time - start_time))
        downloaded_data, unit = parse_bytes(self.file_progress.downloaded_data)

        log("Printing Stats...\n", 20)
        log_with_color(f"Run Stats (config: {self.manager.config_manager.loaded_config}):", "cyan", 20)
        log_with_color(f"  Total Runtime: {runtime}", "yellow", 20)
        log_with_color(f"  Total Downloaded Data: {downloaded_data:.2f} {unit}", "yellow", 20)

        log_spacer(20, "")
        log_with_color("Download Stats:", "cyan", 20)
        log_with_color(f"  Downloaded: {self.download_progress.completed_files} files", "green", 20)
        log_with_color(
            f"  Skipped (Previously Downloaded): {self.download_progress.previously_completed_files} files",
            "yellow",
            20,
        )
        log_with_color(f"  Skipped (By Config): {self.download_progress.skipped_files} files", "yellow", 20)
        log_with_color(f"  Failed: {self.download_stats_progress.failed_files} files", "red", 20)

        log_spacer(20, "")
        log_with_color("Unsupported URLs Stats:", "cyan", 20)
        log_with_color(f"  Sent to Jdownloader: {self.scrape_stats_progress.sent_to_jdownloader}", "yellow", 20)
        log_with_color(f"  Skipped: {self.scrape_stats_progress.unsupported_urls_skipped}", "yellow", 20)

        log_spacer(20, "")
        log_with_color("Dupe Stats:", "cyan", 20)
        log_with_color(f"  Previously Hashed: {self.hash_progress.prev_hashed_files} files", "yellow", 20)
        log_with_color(f"  Newly Hashed: {self.hash_progress.hashed_files} files", "yellow", 20)
        log_with_color(f"  Removed (Current Downloads): {self.hash_progress.removed_files} files", "yellow", 20)
        log_with_color(f"  Removed (Previous Downloads): {self.hash_progress.removed_prev_files} files", "yellow", 20)

        log_spacer(20, "")
        log_with_color("Sort Stats:", "cyan", 20)
        log_with_color(f"  Organized: {self.sort_progress.audio_count} Audios", "green", 20)
        log_with_color(f"  Organized: {self.sort_progress.image_count} Images", "green", 20)
        log_with_color(f"  Organized: {self.sort_progress.video_count} Videos", "green", 20)
        log_with_color(f"  Organized: {self.sort_progress.other_count} Other Files", "green", 20)

        def log_failures(failures: dict, title: str = "Failures:") -> None:
            log_spacer(20, "")
            log_with_color(title, "cyan", 20)
            if not failures:
                log_with_color("  None", "green", 20)
            for name, count in failures.items():
                log_with_color(f"  ({name}): {count}", "red", 20)

        log_failures(self.scrape_stats_progress.return_totals(), "Scrape Failures:")
        log_failures(self.download_stats_progress.return_totals(), "Download Failures:")
