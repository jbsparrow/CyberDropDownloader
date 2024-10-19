import argparse

import arrow

from cyberdrop_dl import __version__ as VERSION
from cyberdrop_dl.utils.dataclasses.supported_domains import SupportedDomains


def parse_args() -> argparse.Namespace:
    """Parses the command line arguments passed into the program"""
    parser = argparse.ArgumentParser(description="Bulk downloader for multiple file hosts")
    general = parser.add_argument_group("General")
    general.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    general.add_argument("--config", type=str, help="name of config to load", default="")
    general.add_argument("--proxy", type=str, help="manually specify proxy string", default="")
    general.add_argument("--flaresolverr", type=str, help="IP:PORT for flaresolverr", default="")
    general.add_argument("--no-ui", action="store_true", help="Disables the UI/Progress view entirely", default=False)
    general.add_argument("--download", action="store_true", help="Skip the UI and go straight to downloading",
                        default=False)
    general.add_argument("--download-all-configs", action="store_true",
                        help="Skip the UI and go straight to downloading (runs all configs sequentially)",
                        default=False)
    general.add_argument("--sort-all-configs", action="store_true", help="Sort all configs sequentially", default=False)
    general.add_argument("--retry-failed", action="store_true", help="retry failed downloads", default=False)
    general.add_argument("--retry-all", action="store_true", help="retry all downloads", default=False)
    general.add_argument("--retry-maintenance", action="store_true",
                        help="retry all failed downloads due to maintenance, only supports bunkr and requires files to be hashed",
                        default=False)
    general.add_argument("--completed-after", help="only download completed downloads at or after this date",
                        default=None, type=lambda x: None if not x else arrow.get(x))
    general.add_argument("--completed-before", help="only download completed downloads at or before this date",
                        default=None, type=lambda x: None if not x else arrow.get(x))
    general.add_argument("--max-items-retry", help="max number of links to retry", type=int)

    # File Paths
    file_paths = parser.add_argument_group("File_Paths")
    file_paths.add_argument("-i", "--input-file", type=str, help="path to txt file containing urls to download",
                            default="")
    file_paths.add_argument("-d", "--output-folder", type=str, help="path to download folder", default="")
    file_paths.add_argument("--config-file", type=str, help="path to the CDL settings.yaml file to load", default="")
    file_paths.add_argument("--appdata-folder", type=str,
                            help="path to where you want CDL to store it's AppData folder", default="")
    file_paths.add_argument("--log-folder", type=str, help="path to where you want CDL to store it's log files",
                            default="")
    file_paths.add_argument("--main-log-filename", type=str, help="filename for the main log file", default="")
    file_paths.add_argument("--last-forum-post-filename", type=str, help="filename for the last forum post log file",
                            default="")
    file_paths.add_argument("--unsupported-urls-filename", type=str, help="filename for the unsupported urls log file",
                            default="")
    file_paths.add_argument("--download-error-urls-filename", type=str,
                            help="filename for the download error urls log file", default="")
    file_paths.add_argument("--scrape-error-urls-filename", type=str,
                            help="filename for the scrape error urls log file", default="")
    file_paths.add_argument("--webhook_url", help="Discord webhook url to send download recap to", default="")

    # Settings
    download_options = parser.add_argument_group("Download_Options")
    download_options.add_argument("--block-download-sub-folders", action=argparse.BooleanOptionalAction,
                                help="block sub folder creation")
    download_options.add_argument("--disable-download-attempt-limit", action=argparse.BooleanOptionalAction,
                                help="disable download attempt limit")
    download_options.add_argument("--disable-file-timestamps", action=argparse.BooleanOptionalAction,
                                help="disable file timestamps", )
    download_options.add_argument("--include-album-id-in-folder-name", action=argparse.BooleanOptionalAction,
                                help="include album id in folder name")
    download_options.add_argument("--include-thread-id-in-folder-name", action=argparse.BooleanOptionalAction,
                                help="include thread id in folder name")
    download_options.add_argument("--remove-domains-from-folder-names", action=argparse.BooleanOptionalAction,
                                help="remove website domains from folder names")
    download_options.add_argument("--remove-generated-id-from-filenames", action=argparse.BooleanOptionalAction,
                                help="remove site generated id from filenames")
    download_options.add_argument("--scrape-single-forum-post", action=argparse.BooleanOptionalAction,
                                help="scrape single forum post")
    download_options.add_argument("--separate-posts", action=argparse.BooleanOptionalAction,
                                help="separate posts into folders")
    download_options.add_argument("--skip-download-mark-completed", action=argparse.BooleanOptionalAction,
                                help="skip download and mark as completed in history")
    download_options.add_argument("--skip-referer-seen-before", action=argparse.BooleanOptionalAction,
                                  help="skip download if referer has been seen before")

    file_size_limits = parser.add_argument_group("File_Size_Limits")
    file_size_limits.add_argument("--maximum-image-size", type=int,
                                help="maximum image size in bytes (default: %(default)s)", default=0)
    file_size_limits.add_argument("--maximum-video-size", type=int,
                                help="maximum video size in bytes (default: %(default)s)", default=0)
    file_size_limits.add_argument("--maximum-other-size", type=int,
                                help="maximum other size in bytes (default: %(default)s)", default=0)
    file_size_limits.add_argument("--minimum-image-size", type=int,
                                help="minimum image size in bytes (default: %(default)s)", default=0)
    file_size_limits.add_argument("--minimum-video-size", type=int,
                                help="minimum video size in bytes (default: %(default)s)", default=0)
    file_size_limits.add_argument("--minimum-other-size", type=int,
                                help="minimum other size in bytes (default: %(default)s)", default=0)

    ignore_options = parser.add_argument_group("Ignore_Options")
    ignore_options.add_argument("--exclude-videos", action=argparse.BooleanOptionalAction,
                                help="exclude videos from downloading")
    ignore_options.add_argument("--exclude-images", action=argparse.BooleanOptionalAction,
                                help="exclude images from downloading")
    ignore_options.add_argument("--exclude-audio", action=argparse.BooleanOptionalAction,
                                help="exclude images from downloading")
    ignore_options.add_argument("--exclude-other", action=argparse.BooleanOptionalAction,
                                help="exclude other files from downloading")
    ignore_options.add_argument("--ignore-coomer-ads", action=argparse.BooleanOptionalAction,
                                help="ignore coomer ads when scraping")
    ignore_options.add_argument("--skip-hosts", choices=SupportedDomains.supported_hosts, action="append",
                                help="skip these domains when scraping", default=[])
    ignore_options.add_argument("--only-hosts", choices=SupportedDomains.supported_hosts, action="append",
                                help="only scrape these domains", default=[])

    runtime_options = parser.add_argument_group("Runtime_Options")
    runtime_options.add_argument("--ignore-history", action=argparse.BooleanOptionalAction,
                                help="ignore history when scraping")
    runtime_options.add_argument("--log-level", type=int, help="set the log level (default: %(default)s)", default=10)
    runtime_options.add_argument("--skip-check-for-partial-files", action=argparse.BooleanOptionalAction,
                                help="skip check for partial downloads")
    runtime_options.add_argument("--skip-check-for-empty-folders", action=argparse.BooleanOptionalAction,
                                help="skip check (and removal) for empty folders")
    runtime_options.add_argument("--delete-partial-files", action=argparse.BooleanOptionalAction,
                                help="delete partial downloads")
    runtime_options.add_argument("--send-unsupported-to-jdownloader", action=argparse.BooleanOptionalAction,
                                help="send unsupported urls to jdownloader")
    runtime_options.add_argument("--update-last-forum-post", action=argparse.BooleanOptionalAction,
                                help="update the last forum post")

    sorting_options = parser.add_argument_group("Sorting")
    sorting_options.add_argument("--sort-downloads", action=argparse.BooleanOptionalAction,
                                help="sort downloads into folders")
    sorting_options.add_argument("--sort-all-downloads", action=argparse.BooleanOptionalAction,
                                help="sort all downloads, not just those downloaded by Cyberdrop-DL")
    sorting_options.add_argument("--sort-folder", type=str, help="path to where you want CDL to store it's log files",
                                default="")
    sorting_options.add_argument("--scan-folder", type=str,
                                help="path to scan for files, if not set then the download_dir is used", default="")

    ui_options = parser.add_argument_group("UI_Options")
    ui_options.add_argument("--vi-mode", action="store_true", help="enable VIM keybindings for UI", default=None)
    ui_options.add_argument("--refresh-rate", type=int, help="refresh rate for the UI (default: %(default)s)",
                            default=10)
    ui_options.add_argument("--scraping-item-limit", type=int,
                            help="number of lines to allow for scraping items before overflow (default: %(default)s)",
                            default=5)
    ui_options.add_argument("--downloading-item-limit", type=int,
                            help="number of lines to allow for downloading items before overflow (default: %(default)s)",
                            default=5)

    # Links
    parser.add_argument("links", metavar="link", nargs="*",
                        help="link to content to download (passing multiple links is supported)", default=[])
    args = parser.parse_args()
    # set ignore history on retry_all
    if args.retry_all or args.retry_maintenance:
        args.ignore_history = True
    return args
