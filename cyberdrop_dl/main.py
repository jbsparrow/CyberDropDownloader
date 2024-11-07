from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from cyberdrop_dl.clients.errors import InvalidYamlError
from cyberdrop_dl.managers.console_manager import print_
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scraper import ScrapeMapper
from cyberdrop_dl.ui.ui import program_ui
from cyberdrop_dl.utils.sorting import Sorter
from cyberdrop_dl.utils.utilities import (
    DEFAULT_CONSOLE_WIDTH,
    check_latest_pypi,
    check_partials_and_empty_folders,
    log,
    log_spacer,
    log_with_color,
    send_webhook_message,
    sent_apprise_notifications,
)

RICH_HANDLER_CONFIG = {"show_time": True, "rich_tracebacks": True, "tracebacks_show_locals": False}

RICH_HANDLER_DEBUG_CONFIG = {
    "show_time": True,
    "rich_tracebacks": True,
    "tracebacks_show_locals": True,
    "locals_max_string": DEFAULT_CONSOLE_WIDTH,
    "tracebacks_extra_lines": 2,
    "locals_max_length": 20,
}

start_time = 0


def startup() -> Manager:
    """Starts the program and returns the manager.

    This will also run the UI for the program
    After this function returns, the manager will be ready to use and scraping / downloading can begin.
    """
    try:
        manager = Manager()
        manager.startup()

        if not manager.args_manager.immediate_download:
            program_ui(manager)

        return manager

    except InvalidYamlError as e:
        print_(e.message_rich)
        sys.exit(1)

    except KeyboardInterrupt:
        print_("\nExiting...")
        sys.exit(0)


async def runtime(manager: Manager) -> None:
    """Main runtime loop for the program, this will run until all scraping and downloading is complete."""
    scrape_mapper = ScrapeMapper(manager)

    async with asyncio.TaskGroup() as task_group:
        manager.task_group = task_group
        await scrape_mapper.start()


async def post_runtime(manager: Manager) -> None:
    """Actions to complete after main runtime, and before ui shutdown."""
    log_spacer(20)
    log_with_color(
        f"Running Post-Download Processes For Config: {manager.config_manager.loaded_config}...\n",
        "green",
        20,
    )
    # checking and removing dupes
    if not manager.args_manager.sort_all_configs:
        await manager.hash_manager.hash_client.cleanup_dupes()
    if (
        isinstance(manager.args_manager.sort_downloads, bool)
        and manager.args_manager.sort_downloads
        or manager.config_manager.settings_data["Sorting"]["sort_downloads"]
        and not manager.args_manager.retry_any
    ):
        sorter = Sorter(manager)
        await sorter.sort()
    await check_partials_and_empty_folders(manager)

    if manager.config_manager.settings_data["Runtime_Options"]["update_last_forum_post"]:
        await manager.log_manager.update_last_forum_post()


def setup_debug_logger(manager: Manager) -> Path | None:
    logger_debug = logging.getLogger("cyberdrop_dl_debug")
    debug_log_file_path = None
    running_in_IDE = os.getenv("PYCHARM_HOSTED") or os.getenv("TERM_PROGRAM") == "vscode"
    import cyberdrop_dl.utils.utilities

    if running_in_IDE or manager.config_manager.settings_data["Runtime_Options"]["log_level"] == -1:
        manager.config_manager.settings_data["Runtime_Options"]["log_level"] = 10
        cyberdrop_dl.utils.utilities.DEBUG_VAR = True

    if running_in_IDE or manager.config_manager.settings_data["Runtime_Options"]["console_log_level"] == -1:
        cyberdrop_dl.utils.utilities.CONSOLE_DEBUG_VAR = True

    if cyberdrop_dl.utils.utilities.DEBUG_VAR:
        logger_debug.setLevel(manager.config_manager.settings_data["Runtime_Options"]["log_level"])
        debug_log_file_path = Path(__file__).parent / "cyberdrop_dl_debug.log"
        if running_in_IDE:
            debug_log_file_path = Path(__file__).parents[1] / "cyberdrop_dl_debug.log"

        rich_file_handler_debug = RichHandler(
            **RICH_HANDLER_DEBUG_CONFIG,
            console=Console(file=debug_log_file_path.open("w", encoding="utf8"), width=DEFAULT_CONSOLE_WIDTH),
            level=manager.config_manager.settings_data["Runtime_Options"]["log_level"],
        )

        logger_debug.addHandler(rich_file_handler_debug)
        # aiosqlite_log = logging.getLogger("aiosqlite")
        # aiosqlite_log.setLevel(manager.config_manager.settings_data['Runtime_Options']['log_level'])
        # aiosqlite_log.addHandler(file_handler_debug)

    return debug_log_file_path.resolve() if debug_log_file_path else None


async def switch_config_and_reset_logger(manager: Manager, config_name: str) -> None:
    import cyberdrop_dl.managers.console_manager
    import cyberdrop_dl.utils.utilities

    logger = logging.getLogger("cyberdrop_dl")
    if manager.args_manager.all_configs:
        if len(logger.handlers) > 0:
            log("Picking new config...", 20)
        manager.config_manager.change_config(config_name)
        if len(logger.handlers) > 0:
            log(f"Changing config to {config_name}...", 20)
            old_file_handler = logger.handlers[0]
            logger.removeHandler(logger.handlers[0])
            old_file_handler.close()

    logger.setLevel(manager.config_manager.settings_data["Runtime_Options"]["log_level"])

    if cyberdrop_dl.utils.utilities.DEBUG_VAR:
        manager.config_manager.settings_data["Runtime_Options"]["log_level"] = 10

    rich_file_handler = RichHandler(
        **RICH_HANDLER_CONFIG,
        console=Console(file=manager.path_manager.main_log.open("w", encoding="utf8"), width=DEFAULT_CONSOLE_WIDTH),
        level=manager.config_manager.settings_data["Runtime_Options"]["log_level"],
    )

    logger.addHandler(rich_file_handler)

    cyberdrop_dl.managers.console_manager.LEVEL = manager.config_manager.settings_data["Runtime_Options"][
        "console_log_level"
    ]


async def director(manager: Manager) -> None:
    """Runs the program and handles the UI."""
    global start_time
    manager.path_manager.startup()
    manager.log_manager.startup()
    debug_log_file_path = setup_debug_logger(manager)
    using_multiple_configs = False

    configs_to_run = [manager.config_manager.loaded_config]
    if manager.args_manager.all_configs:
        configs_to_run = manager.config_manager.get_configs()
        using_multiple_configs = True
        configs_to_run.sort()

    for current_config in configs_to_run:
        if using_multiple_configs:
            await switch_config_and_reset_logger(manager, current_config)
        configs_to_run.pop(0)

        log(f"Using Debug Log: {debug_log_file_path if debug_log_file_path else None}", 10)
        log("Starting Async Processes...", 20)
        await manager.async_startup()

        log_spacer(20)
        log("Starting CDL...\n", 20)
        if not manager.args_manager.sort_all_configs:
            try:
                async with manager.live_manager.get_main_live(stop=True):
                    await runtime(manager)
                    await post_runtime(manager)
            except Exception:
                log("\nAn error occurred, please report this to the developer:", 50, exc_info=True)
                sys.exit(1)

        log_spacer(20)
        await manager.progress_manager.print_stats(start_time)

        if not configs_to_run:
            log_spacer(20)
            log("Checking for Updates...", 20)
            check_latest_pypi()
            log_spacer(20)
            log("Closing Program...", 20)
            await manager.close()
            log_with_color("Finished downloading. Enjoy :)", "green", 20, show_in_stats=False)

        await send_webhook_message(manager)
        await sent_apprise_notifications(manager)
        start_time = time.perf_counter()


def main() -> None:
    global start_time
    start_time = time.perf_counter()
    manager = startup()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with contextlib.suppress(RuntimeError):
        try:
            asyncio.run(director(manager))

        except KeyboardInterrupt:
            print_("\nTrying to Exit...")
            with contextlib.suppress(Exception):
                asyncio.run(manager.close())
            sys.exit(1)
    loop.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
