from __future__ import annotations

from dataclasses import field
from pathlib import Path

import arrow

from cyberdrop_dl.utils.args.args import parse_args


class ArgsManager:
    def __init__(self) -> None:
        self.parsed_args = {}

        self.proxy = ""
        self.flaresolverr = ""

        self.all_configs = False
        self.sort_all_configs = False
        self.retry_failed = False
        self.retry_all = False
        self.retry_any = False
        self.retry_maintenance = False
        self.webhook_url = ""
        self.max_items = None

        self.immediate_download = False
        self.no_ui = False
        self.load_config_from_args = False
        self.load_config_name = ""
        self.other_links: list = []
        self.additive_args = ["skip_hosts", "only_hosts"]

        # Files
        self.input_file = None
        self.download_dir = None
        self.config_file = None
        self.appdata_dir = None
        self.log_dir = None

        # Sorting
        self.sort_downloads = field(init=False)
        self.sort_cdl_only = field(init=True)
        self.sort_folder = None
        self.scan_folder = None

        # Logs
        self.main_log_filename = None
        self.last_forum_post_filename = None
        self.unsupported_urls_filename = None
        self.download_error_urls_filename = None
        self.scrape_error_urls_filename = None

        # UI
        self.vi_mode = None
        self.after = None
        self.before = None

        self._convert_to_paths = [
            "input_file",
            "download_dir",
            "config_file",
            "appdata_dir",
            "log_dir",
            "sort_folder",
            "scan_folder",
        ]

    def startup(self) -> None:
        """Parses arguments and sets variables accordingly."""
        if self.parsed_args:
            return

        self.parsed_args = parse_args().__dict__

        self.immediate_download = self.parsed_args["download"]
        self.load_config_name = self.parsed_args["config"]
        self.vi_mode = self.parsed_args["vi_mode"]

        for arg in self._convert_to_paths:
            value = self.parsed_args.get(arg)
            if value:
                setattr(self, arg, Path(value))

        if self.parsed_args["no_ui"]:
            self.immediate_download = True
            self.no_ui = True

        if self.load_config_name:
            self.load_config_from_args = True

        if self.parsed_args["download_all_configs"]:
            self.all_configs = True
            self.immediate_download = True

        if self.parsed_args["sort_all_configs"]:
            self.sort_all_configs = True
            self.all_configs = True
            self.immediate_download = True
        if self.parsed_args["retry_failed"]:
            self.retry_failed = True
            self.retry_any = True
            self.immediate_download = True
        if self.parsed_args["retry_all"]:
            self.retry_all = True
            self.retry_any = True
            self.immediate_download = True
        if self.parsed_args["retry_maintenance"]:
            self.retry_maintenance = True
            self.immediate_download = True

        if self.parsed_args["config_file"]:
            self.immediate_download = True
        if self.parsed_args["sort_downloads"]:
            self.sort_downloads = True
        if not self.parsed_args["sort_all_downloads"]:
            self.sort_cdl_only = True
        if self.parsed_args["main_log_filename"]:
            self.main_log_filename = self.parsed_args["main_log_filename"]
        if self.parsed_args["last_forum_post_filename"]:
            self.last_forum_post_filename = self.parsed_args["last_forum_post_filename"]
        if self.parsed_args["unsupported_urls_filename"]:
            self.unsupported_urls_filename = self.parsed_args["unsupported_urls_filename"]
        if self.parsed_args["download_error_urls_filename"]:
            self.download_error_urls_filename = self.parsed_args["download_error_urls_filename"]
        if self.parsed_args["scrape_error_urls_filename"]:
            self.scrape_error_urls_filename = self.parsed_args["scrape_error_urls_filename"]

        if self.parsed_args["proxy"]:
            self.proxy = self.parsed_args["proxy"]
        if self.parsed_args["flaresolverr"]:
            self.flaresolverr = self.parsed_args["flaresolverr"]

        self.other_links = self.parsed_args["links"]

        self.after = self.parsed_args["completed_after"] or arrow.get(0)
        self.before = self.parsed_args["completed_before"] or arrow.get("3000")
        self.max_items = self.parsed_args["max_items_retry"]
        self.webhook_url = self.parsed_args["webhook_url"]

        self.after = self.parsed_args["completed_after"] or arrow.get(0)
        self.before = self.parsed_args["completed_before"] or arrow.get("3000")
        self.max_items = self.parsed_args["max_items_retry"]

        del self.parsed_args["download"]
        del self.parsed_args["download_all_configs"]
        del self.parsed_args["config"]
        del self.parsed_args["no_ui"]
        del self.parsed_args["retry_failed"]
        del self.parsed_args["retry_all"]
        del self.parsed_args["retry_maintenance"]
        del self.parsed_args["input_file"]
        del self.parsed_args["download_dir"]
        del self.parsed_args["appdata_dir"]
        del self.parsed_args["config_file"]
        del self.parsed_args["log_dir"]
        del self.parsed_args["proxy"]
        del self.parsed_args["links"]
        del self.parsed_args["sort_downloads"]
        del self.parsed_args["sort_all_downloads"]
        del self.parsed_args["sort_folder"]
        del self.parsed_args["scan_folder"]
        del self.parsed_args["completed_after"]
        del self.parsed_args["completed_before"]
