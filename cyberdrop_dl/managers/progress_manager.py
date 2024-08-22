from dataclasses import field
from typing import TYPE_CHECKING

from rich.layout import Layout

from cyberdrop_dl.ui.progress.downloads_progress import DownloadsProgress
from cyberdrop_dl.ui.progress.hash_progress import HashProgress

from cyberdrop_dl.ui.progress.file_progress import FileProgress
from cyberdrop_dl.ui.progress.scraping_progress import ScrapingProgress
from cyberdrop_dl.ui.progress.statistic_progress import DownloadStatsProgress, ScrapeStatsProgress
from cyberdrop_dl.utils.utilities import log_with_color, get_log_output_text
from aiohttp import ClientSession

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class ProgressManager:
    def __init__(self, manager: 'Manager'):
        # File Download Bars
        self.manager = manager
        self.file_progress: FileProgress = FileProgress(manager.config_manager.global_settings_data['UI_Options']['downloading_item_limit'], manager)

        # Scraping Printout
        self.scraping_progress: ScrapingProgress = ScrapingProgress(manager.config_manager.global_settings_data['UI_Options']['scraping_item_limit'], manager)

        # Overall Progress Bars & Stats
        self.download_progress: DownloadsProgress = DownloadsProgress(manager)
        self.download_stats_progress: DownloadStatsProgress = DownloadStatsProgress()
        self.scrape_stats_progress: ScrapeStatsProgress = ScrapeStatsProgress()
        self.hash_progress: HashProgress = HashProgress(manager)
        
        self.ui_refresh_rate = manager.config_manager.global_settings_data['UI_Options']['refresh_rate']
        
        self.layout: Layout = field(init=False)
        self.hash_remove_layout: Layout = field(init=False)
        self.hash_layout: Layout = field(init=False)

    async def startup(self) -> None:
        """Startup process for the progress manager"""
        progress_layout = Layout()
        progress_layout.split_column(
            Layout(name="upper", ratio=1, minimum_size=8),
            Layout(renderable=await self.scraping_progress.get_progress(), name="Scraping", ratio=2),
            Layout(renderable=await self.file_progress.get_progress(), name="Downloads", ratio=2),
        )
        progress_layout["upper"].split_row(
            Layout(renderable=await self.download_progress.get_progress(), name="Files", ratio=1),
            Layout(renderable=await self.scrape_stats_progress.get_progress(), name="Scrape Failures", ratio=1),
            Layout(renderable=await self.download_stats_progress.get_progress(), name="Download Failures", ratio=1),
        )

        hash_remove_layout =Layout()
        hash_remove_layout=await self.hash_progress.get_removed_progress()
        
        
        self.layout = progress_layout
        self.hash_remove_layout = hash_remove_layout
        self.hash_layout=await self.hash_progress.get_hash_progress()

    async def print_stats(self) -> None:
        """Prints the stats of the program"""
        await log_with_color("\nDownload Stats:", "cyan", 20)
        await log_with_color(f"Downloaded {self.download_progress.completed_files} files", "green", 20)
        await log_with_color(f"Previously Downloaded {self.download_progress.previously_completed_files} files", "yellow", 20)
        

        await log_with_color(f"Skipped By Config {self.download_progress.skipped_files} files", "yellow", 20)
        await log_with_color(f"Failed {self.download_stats_progress.failed_files} files", "red", 20)

        await log_with_color("\nDupe Stats:", "cyan", 20)
        await log_with_color(f"Previously Hashed {self.hash_progress.prev_hashed_files} files", "yellow", 20)
        await log_with_color(f"Newly Hashed {self.hash_progress.hashed_files} files", "yellow", 20)
        await log_with_color(f"Removed From Current Downloads {self.hash_progress.removed_files} files", "yellow", 20)
        await log_with_color(f"Removed From Previous Downloads {self.hash_progress.removed_prev_files} files", "yellow", 20)





        scrape_failures = await self.scrape_stats_progress.return_totals()
        await log_with_color("\nScrape Failures:", "cyan", 20)
        for key, value in scrape_failures.items():
            await log_with_color(f"Scrape Failures ({key}): {value}", "red", 20)

        download_failures = await self.download_stats_progress.return_totals()
        await log_with_color("\nDownload Failures:", "cyan", 20)
        for key, value in download_failures.items():
            await log_with_color(f"Download Failures ({key}): {value}", "red", 20)

        await self.send_webhook_message(self.manager.config_manager.settings_data['Logs']['webhook_url'])

    async def send_webhook_message(self, webhook_url: str) -> None:
        """Outputs the stats to a code block for webhook messages"""
        log = await get_log_output_text()
        log_message = log.replace('[cyan]', '').replace('[cyan]\n', '\n')
        log_message = log_message.replace('[green]', '+ ').replace('[green]\n', '\n+ ')
        log_message = log_message.replace('[red]', '- ').replace('[red]\n', '\n- ')
        log_message = log_message.replace('[yellow]', '*** ').replace('[yellow]\n', '\n*** ')
        data = {
            "content": log_message,
            "username": "CyberDrop-DL",
        }
        # Make an asynchronous POST request to the webhook
        if webhook_url:
            async with ClientSession() as session:
                async with session.post(webhook_url, json=data) as response:
                    await response.text()
