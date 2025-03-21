from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import browser_cookie3
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler

from cyberdrop_dl import env
from cyberdrop_dl.clients.errors import InvalidYamlError
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scrape_mapper import ScrapeMapper
from cyberdrop_dl.ui.program_ui import ProgramUI
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.apprise import send_apprise_notifications
from cyberdrop_dl.utils.dumper import Dumper
from cyberdrop_dl.utils.logger import RedactedConsole, add_custom_log_render, log, log_spacer, log_with_color
from cyberdrop_dl.utils.sorting import Sorter
from cyberdrop_dl.utils.updates import check_latest_pypi
from cyberdrop_dl.utils.utilities import check_partials_and_empty_folders, send_webhook_message
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

startup_logger = logging.getLogger("cyberdrop_dl_startup")
STARTUP_LOGGER_FILE = Path.cwd().joinpath("startup.log")


def startup() -> Manager:
    """Starts the program and returns the manager.

    This will also run the UI for the program
    After this function returns, the manager will be ready to use and scraping / downloading can begin.
    """

    try:
        manager = Manager()
        manager.startup()
        if manager.parsed_args.cli_only_args.multiconfig:
            startup_logger.info("validating all configs, please wait...")
            manager.validate_all_configs()

        if not manager.parsed_args.cli_only_args.download:
            ProgramUI(manager)

    except InvalidYamlError as e:
        startup_logger.error(e.message)
        sys.exit(1)

    except ValidationError as e:
        sources = {
            "GlobalSettings": manager.config_manager.global_settings,
            "ConfigSettings": manager.config_manager.settings,
            "AuthSettings": manager.config_manager.authentication_settings,
        }

        file = sources.get(e.title)
        handle_validation_error(e, file=file)
        sys.exit(1)

    except KeyboardInterrupt:
        startup_logger.info("Exiting...")
        sys.exit(0)

    except browser_cookie3.BrowserCookieError:
        startup_logger.exception("")
        sys.exit(1)

    except Exception:
        msg = "An error occurred, please report this to the developer with your logs file:"
        startup_logger.exception(msg)
        sys.exit(1)

    else:
        return manager


async def runtime(manager: Manager) -> None:
    """Main runtime loop for the program, this will run until all scraping and downloading is complete."""
    if manager.multiconfig and manager.config_manager.settings_data.sorting.sort_downloads:
        return

    with manager.live_manager.get_main_live(stop=True):
        scrape_mapper = ScrapeMapper(manager)
        async with asyncio.TaskGroup() as task_group:
            manager.task_group = task_group
            await scrape_mapper.start()


async def post_runtime(manager: Manager) -> None:
    """Actions to complete after main runtime, and before ui shutdown."""
    log_spacer(20, log_to_console=False)
    msg = f"Running Post-Download Processes For Config: {manager.config_manager.loaded_config}"
    log_with_color(msg, "green", 20)
    # checking and removing dupes
    if not (manager.multiconfig and manager.config_manager.settings_data.sorting.sort_downloads):
        await manager.hash_manager.hash_client.cleanup_dupes_after_download()
    if manager.config_manager.settings_data.sorting.sort_downloads and not manager.parsed_args.cli_only_args.retry_any:
        sorter = Sorter(manager)
        await sorter.run()

    check_partials_and_empty_folders(manager)

    if manager.config_manager.settings_data.runtime_options.update_last_forum_post:
        await manager.log_manager.update_last_forum_post()

    if manager.config_manager.settings_data.files.dump_json:
        dumper = Dumper(manager)
        dumper.run()


def setup_startup_logger(*, first_time_setup: bool = False) -> None:
    if first_time_setup:
        STARTUP_LOGGER_FILE.unlink(missing_ok=True)  # Only delete file once. Subsequent calls will append to file
    destroy_startup_logger()
    startup_logger.setLevel(10)
    console_handler = RichHandler(**(constants.RICH_HANDLER_CONFIG | {"show_time": False}), level=10)
    startup_logger.addHandler(console_handler)

    file_io = STARTUP_LOGGER_FILE.open("a", encoding="utf8")
    file_console = RedactedConsole(file=file_io, width=constants.DEFAULT_CONSOLE_WIDTH)
    file_handler = RichHandler(**constants.RICH_HANDLER_CONFIG, console=file_console, level=10)
    add_custom_log_render(file_handler)
    startup_logger.addHandler(file_handler)


def destroy_startup_logger(remove_all_handlers: bool = True) -> None:
    handlers: list[RichHandler] = startup_logger.handlers  # type: ignore
    for handler in handlers[:]:  # create copy
        if not (handler.console._file or remove_all_handlers):
            continue
        if handler.console._file:
            handler.console._file.close()
        startup_logger.removeHandler(handler)
        handler.close()

    if STARTUP_LOGGER_FILE.is_file() and STARTUP_LOGGER_FILE.stat().st_size > 0:
        return
    STARTUP_LOGGER_FILE.unlink(missing_ok=True)


@contextlib.contextmanager
def startup_logging(*, first_time_setup: bool = False) -> Generator:
    try:
        setup_startup_logger(first_time_setup=first_time_setup)
        yield
    finally:
        destroy_startup_logger()


def setup_debug_logger(manager: Manager) -> Path | None:
    if not env.DEBUG_VAR:
        return

    logger_debug = logging.getLogger("cyberdrop_dl_debug")
    log_level = 10
    manager.config_manager.settings_data.runtime_options.log_level = log_level
    logger_debug.setLevel(log_level)
    debug_log_file_path = Path(__file__).parents[1] / "cyberdrop_dl_debug.log"
    with startup_logging():
        if env.DEBUG_LOG_FOLDER:
            debug_log_folder = Path(env.DEBUG_LOG_FOLDER)
            if not debug_log_folder.is_dir():
                msg = "Value of env var 'CDL_DEBUG_LOG_FOLDER' is invalid."
                msg += f" Folder '{debug_log_folder}' does not exists"
                startup_logger.error(msg)
                sys.exit(1)
            date = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_log_file_path = debug_log_folder / f"cyberdrop_dl_debug_{date}.log"
        try:
            file_io = debug_log_file_path.open("w", encoding="utf8")
        except OSError as e:
            startup_logger.exception(str(e))
            sys.exit(1)

    file_console = Console(file=file_io, width=manager.config_manager.settings_data.logs.log_line_width)
    file_handler_debug = RichHandler(**constants.RICH_HANDLER_DEBUG_CONFIG, console=file_console, level=log_level)
    add_custom_log_render(file_handler_debug)
    logger_debug.addHandler(file_handler_debug)

    aiohttp_client_cache_logger = logging.getLogger("aiohttp_client_cache")
    aiohttp_client_cache_logger.setLevel(log_level)
    aiohttp_client_cache_logger.addHandler(file_handler_debug)

    # aiosqlite_log = logging.getLogger("aiosqlite")
    # aiosqlite_log.setLevel(log_level)
    # aiosqlite_log.addHandler(file_handler_debug)

    return debug_log_file_path.resolve()


def setup_logger(manager: Manager, config_name: str) -> None:
    logger = logging.getLogger("cyberdrop_dl")
    with startup_logging():
        if manager.multiconfig:
            if len(logger.handlers) > 0:
                log("Picking new config...", 20)
            manager.config_manager.change_config(config_name)
            if len(logger.handlers) > 0:
                log(f"Changing config to {config_name}...", 20)
                old_file_handler = logger.handlers[0]
                logger.removeHandler(logger.handlers[0])
                old_file_handler.close()

        try:
            file_io = manager.path_manager.main_log.open("w", encoding="utf8")
        except OSError as e:
            startup_logger.exception(str(e))
            sys.exit(1)

    log_level = manager.config_manager.settings_data.runtime_options.log_level
    logger.setLevel(log_level)

    if not manager.parsed_args.cli_only_args.fullscreen_ui:
        constants.CONSOLE_LEVEL = manager.config_manager.settings_data.runtime_options.console_log_level

    console_log_level = constants.CONSOLE_LEVEL
    file_console = RedactedConsole(file=file_io, width=manager.config_manager.settings_data.logs.log_line_width)
    file_handler = RichHandler(**constants.RICH_HANDLER_CONFIG, console=file_console, level=log_level)
    console_handler = RichHandler(**(constants.RICH_HANDLER_CONFIG | {"show_time": False}), level=console_log_level)
    add_custom_log_render(file_handler)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def ui_error_handling_wrapper(func: Callable) -> Callable:
    """Wrapper handles errors from the main UI."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except* Exception as e:
            exceptions = [e]
            if isinstance(e, ExceptionGroup):
                exceptions = e.exceptions
            if not isinstance(exceptions[0], browser_cookie3.BrowserCookieError):
                msg = "An error occurred, please report this to the developer with your logs file:"
                log_with_color(msg, "bold red", 50, show_in_stats=False)
            for exc in exceptions:
                log_with_color(f"  {exc}", "bold red", 50, show_in_stats=False, exc_info=exc)

    return wrapper


@ui_error_handling_wrapper
async def director(manager: Manager) -> None:
    """Runs the program and handles the UI."""
    manager.path_manager.startup()
    manager.log_manager.startup()
    debug_log_file_path = setup_debug_logger(manager)

    configs_to_run = [manager.config_manager.loaded_config]
    if manager.multiconfig:
        configs_to_run = manager.config_manager.get_configs()

    start_time = manager.start_time
    while configs_to_run:
        current_config = configs_to_run[0]
        setup_logger(manager, current_config)
        configs_to_run.pop(0)

        log(f"Using Debug Log: {debug_log_file_path}", 10)
        log("Starting Async Processes...", 10)
        await manager.async_startup()
        log_spacer(10)

        log("Starting CDL...\n", 20)
        await runtime(manager)
        await post_runtime(manager)

        manager.progress_manager.print_stats(start_time)

        if not configs_to_run:
            log_spacer(20)
            log("Checking for Updates...", 20)
            check_latest_pypi()
            log_spacer(20)
            log("Closing Program...", 20)
            log_with_color("Finished downloading. Enjoy :)", "green", 20, show_in_stats=False)

        await send_webhook_message(manager)
        await send_apprise_notifications(manager)
        start_time = perf_counter()


def main(*, profiling: bool = False, ask: bool = True):
    if not (profiling or env.PROFILING):
        return actual_main()
    from cyberdrop_dl.profiling import profile

    profile(actual_main, ask)


def actual_main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    exit_code = 1
    with startup_logging(first_time_setup=True):
        manager = startup()
    with contextlib.suppress(Exception):
        try:
            asyncio.run(director(manager))
            exit_code = 0
        except KeyboardInterrupt:
            Console().print("Trying to Exit ...")
        finally:
            asyncio.run(manager.close())
    loop.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
