from __future__ import annotations
from dataclasses import field
from typing import TYPE_CHECKING

from rich.layout import Layout
import time
from datetime import timedelta

from cyberdrop_dl.ui.progress.downloads_progress import DownloadsProgress
from cyberdrop_dl.ui.progress.file_progress import FileProgress
from cyberdrop_dl.ui.progress.hash_progress import HashProgress
from cyberdrop_dl.ui.progress.scraping_progress import ScrapingProgress
from cyberdrop_dl.ui.progress.sort_progress import SortProgress
from cyberdrop_dl.ui.progress.statistic_progress import DownloadStatsProgress, ScrapeStatsProgress
from cyberdrop_dl.utils.utilities import log_with_color, get_log_output_text, log, log_spacer, parse_bytes, parse_rich_text_by_style, STYLE_TO_DIFF_FORMAT_MAP

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from datetime import timedelta


class ProgressManager:
    def __init__(self, manager: Manager):
        # File Download Bars
        self.manager = manager
        self.file_progress: FileProgress = FileProgress(
            manager.config_manager.global_settings_data['UI_Options']['downloading_item_limit'], manager)

        # Scraping Printout
        self.scraping_progress: ScrapingProgress = ScrapingProgress(
            manager.config_manager.global_settings_data['UI_Options']['scraping_item_limit'], manager)

        # Overall Progress Bars & Stats
        self.download_progress: DownloadsProgress = DownloadsProgress(manager)
        self.download_stats_progress: DownloadStatsProgress = DownloadStatsProgress()
        self.scrape_stats_progress: ScrapeStatsProgress = ScrapeStatsProgress()
        self.hash_progress: HashProgress = HashProgress(manager)
        self.sort_progress: SortProgress = SortProgress(1, manager)

        self.ui_refresh_rate = manager.config_manager.global_settings_data['UI_Options']['refresh_rate']

        self.layout: Layout = field(init=False)
        self.hash_remove_layout: Layout = field(init=False)
        self.hash_layout: Layout = field(init=False)
        self.sort_layout: Layout = field(init=False)

    async def startup(self) -> None:
        """Startup process for the progress manager"""
        progress_layout = Layout()
        progress_layout.split_column(
            Layout(name="upper", ratio=2, minimum_size=8),
            Layout(renderable=await self.scraping_progress.get_progress(), name="Scraping", ratio=2),
            Layout(renderable=await self.file_progress.get_progress(), name="Downloads", ratio=2),
        )
        progress_layout["upper"].split_row(
            Layout(renderable=await self.download_progress.get_progress(), name="Files", ratio=1),
            Layout(renderable=await self.scrape_stats_progress.get_progress(), name="Scrape Failures", ratio=1),
            Layout(renderable=await self.download_stats_progress.get_progress(), name="Download Failures", ratio=1),
        )

        hash_remove_layout = Layout()
        hash_remove_layout = await self.hash_progress.get_removed_progress()

        self.layout = progress_layout
        self.hash_remove_layout = hash_remove_layout
        self.hash_layout = await self.hash_progress.get_hash_progress()
        self.sort_layout = await self.sort_progress.get_progress()

    async def print_stats(self, start_time: timedelta) -> None:
        """Prints the stats of the program"""

        end_time = time.perf_counter()
        total_time = timedelta(seconds = int(end_time - start_time))
        downloaded_data , unit = parse_bytes (self.file_progress.downloaded_data)

        await log("Printing Stats...\n", 20)
        await log_with_color("Run Stats:", "cyan", 20)
        await log_with_color(f"  Total Runtime: {total_time}", "yellow", 20)
        await log_with_color(f"  Total Downloaded Data: {downloaded_data:.2f} {unit}", "yellow", 20)

        await log_spacer(20,'')
        await log_with_color("Download Stats:", "cyan", 20)
        await log_with_color(f"  Downloaded {self.download_progress.completed_files} files", "green", 20)
        await log_with_color(f"  Previously Downloaded {self.download_progress.previously_completed_files} files",
                            "yellow", 20)
        await log_with_color(f"  Skipped By Config {self.download_progress.skipped_files} files", "yellow", 20)
        await log_with_color(f"  Failed {self.download_stats_progress.failed_files} files", "red", 20)

        await log_spacer(20,'')
        await log_with_color("Unsupported URLs Stats:", "cyan", 20)
        await log_with_color(f"  Sent to Jdownloader: {self.scrape_stats_progress.sent_to_jdownloader}", "yellow", 20)
        await log_with_color(f"  Skipped: {self.scrape_stats_progress.unsupported_urls_skipped}", "yellow", 20)

        await log_spacer(20,'')
        await log_with_color("Dupe Stats:", "cyan", 20)
        await log_with_color(f"  Previously Hashed {self.hash_progress.prev_hashed_files} files", "yellow", 20)
        await log_with_color(f"  Newly Hashed {self.hash_progress.hashed_files} files", "yellow", 20)
        await log_with_color(f"  Removed From Current Downloads {self.hash_progress.removed_files} files", "yellow", 20)
        await log_with_color(f"  Removed From Previous Downloads {self.hash_progress.removed_prev_files} files", "yellow",
                            20)

        await log_spacer(20,'')
        await log_with_color("Sort Stats:", "cyan", 20)
        await log_with_color(f"  Organized: {self.sort_progress.audio_count} Audios", "green", 20)
        await log_with_color(f"  Organized: {self.sort_progress.image_count} Images", "green", 20)
        await log_with_color(f"  Organized: {self.sort_progress.video_count} Videos", "green", 20)
        await log_with_color(f"  Organized: {self.sort_progress.other_count} Other Files", "green", 20)

        scrape_failures = await self.scrape_stats_progress.return_totals()
        await log_spacer(20,'')
        await log_with_color("Scrape Failures:", "cyan", 20)
        if not scrape_failures:
            await log_with_color(f"  None", "green", 20)
        for key, value in scrape_failures.items():
            await log_with_color(f"  ({key}): {value}", "red", 20)

        download_failures = await self.download_stats_progress.return_totals()
        await log_spacer(20,'')
        await log_with_color("Download Failures:", "cyan", 20)
        if not download_failures:
            await log_with_color(f"  None", "green", 20)
        for key, value in download_failures.items():
            await log_with_color(f"  ({key}): {value}", "red", 20)
