import asyncio
import contextlib
import logging
import os
import sys
import time
from pathlib import Path
import sentry_sdk
import sentry_sdk.attachments
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.types import Event, Hint

from rich.console import Console
from rich.logging import RichHandler

from cyberdrop_dl.clients.errors import InvalidYamlConfig
from cyberdrop_dl.managers.console_manager import print_
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scraper import ScrapeMapper
from cyberdrop_dl.ui.ui import program_ui
from cyberdrop_dl.utils.sorting import Sorter
from cyberdrop_dl.utils.utilities import check_latest_pypi, log_with_color, \
    check_partials_and_empty_folders, log, log_spacer, send_webhook_message, \
    DEFAULT_CONSOLE_WIDTH, sent_apprise_notifications


SENTRY_CLIENT: sentry_sdk.client.BaseClient = None

RICH_HANDLER_CONFIG = {
    "show_time": True,
    "rich_tracebacks": True,
    "tracebacks_show_locals": False
}

RICH_HANDLER_DEBUG_CONFIG = {
    "show_time": True,
    "rich_tracebacks": True,
    "tracebacks_show_locals": True,
    "locals_max_string": DEFAULT_CONSOLE_WIDTH,
    "tracebacks_extra_lines": 2,
    "locals_max_length": 20
}

start_time = 0


def sentry_before_send(event: Event, hint: Hint):
    return event

def sentry_before_breadcrumb(event: Event, hint: Hint):
    if event.get("response") is not None:
        # Response codes to include in breadcrumbs. e.g. allow 405s to be sent to sentry
        if event.get("response").get("status_code") in [405]:
            return event


def startup() -> Manager:
    """
    Starts the program and returns the manager
    This will also run the UI for the program
    After this function returns, the manager will be ready to use and scraping / downloading can begin
    """

    try:
        manager = Manager()
        manager.startup()

        if not manager.args_manager.immediate_download:
            program_ui(manager)

        return manager

    except InvalidYamlConfig as e:
        print_(e.message_rich)
        exit(1)

    except KeyboardInterrupt:
        print_("\nExiting...")
        exit(0)


async def runtime(manager: Manager) -> None:
    """Main runtime loop for the program, this will run until all scraping and downloading is complete"""
    scrape_mapper = ScrapeMapper(manager)

    # NEW CODE
    async with asyncio.TaskGroup() as task_group:
        manager.task_group = task_group
        await scrape_mapper.start()


async def post_runtime(manager: Manager) -> None:
    """Actions to complete after main runtime, and before ui shutdown"""

    await log_spacer(20)
    await log_with_color(f"Running Post-Download Processes For Config: {manager.config_manager.loaded_config}...\n",
                        "green", 20)
    # checking and removing dupes
    if not manager.args_manager.sort_all_configs:
        await manager.hash_manager.hash_client.cleanup_dupes()
    if isinstance(manager.args_manager.sort_downloads, bool):
        if manager.args_manager.sort_downloads:
            sorter = Sorter(manager)
            await sorter.sort()
    elif manager.config_manager.settings_data['Sorting']['sort_downloads'] and not manager.args_manager.retry_any:
        sorter = Sorter(manager)
        await sorter.sort()
    await check_partials_and_empty_folders(manager)

    if manager.config_manager.settings_data['Runtime_Options']['update_last_forum_post']:
        await manager.log_manager.update_last_forum_post()


async def director(manager: Manager) -> None:
    """Runs the program and handles the UI"""
    if manager.config_manager.global_settings_data["Privacy"]["enable_sentry_integration"]:
        global SENTRY_CLIENT
        from cyberdrop_dl import __version__ as version
        environments = {
            "rc": "Release Candidate",
            "a": "Alpha",
            "b": "Beta",
            "pre": "Pre-Release",
            "post": "Post-Release",
            "dev": "Development"
        }
        environment = next((env for key, env in environments.items() if key in str(version)), "Production")
        sentry_sdk.init(
            dsn="https://c027bde3b1c128f436ad3d93837da3b7@o4504108908478464.ingest.us.sentry.io/4508246301540352",
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for tracing.
            traces_sample_rate=1.0,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=1.0,
            release=version,
            environment=environment,
            integrations=[AsyncioIntegration()],
            before_breadcrumb=sentry_before_breadcrumb
        )
        SENTRY_CLIENT = sentry_sdk.get_client()

    configs = manager.config_manager.get_configs()
    configs_ran = []
    manager.path_manager.startup()
    manager.log_manager.startup()

    logger_debug = logging.getLogger("cyberdrop_dl_debug")
    import cyberdrop_dl.utils.utilities

    if os.getenv("PYCHARM_HOSTED") is not None or manager.config_manager.settings_data['Runtime_Options'][
        'log_level'] == -1 or 'TERM_PROGRAM' in os.environ.keys() and os.environ['TERM_PROGRAM'] == 'vscode':
        manager.config_manager.settings_data['Runtime_Options']['log_level'] = 10
        cyberdrop_dl.utils.utilities.DEBUG_VAR = True

        if cyberdrop_dl.utils.utilities.DEBUG_VAR:
            ignore_logger("cyberdrop_dl")
        else:
            ignore_logger("cyberdrop_dl_debug")

    if os.getenv("PYCHARM_HOSTED") is not None or manager.config_manager.settings_data['Runtime_Options'][
        'console_log_level'] == -1 or 'TERM_PROGRAM' in os.environ.keys() and os.environ['TERM_PROGRAM'] == 'vscode':
        cyberdrop_dl.utils.utilities.CONSOLE_DEBUG_VAR = True

    if cyberdrop_dl.utils.utilities.DEBUG_VAR:
        logger_debug.setLevel(manager.config_manager.settings_data['Runtime_Options']['log_level'])
        if os.getenv("PYCHARM_HOSTED") is not None or 'TERM_PROGRAM' in os.environ.keys() and os.environ[
            'TERM_PROGRAM'] == 'vscode':
            debug_log_file_path = Path(__file__).parents[1] / "cyberdrop_dl_debug.log"
        else:
            debug_log_file_path = Path(__file__).parent / "cyberdrop_dl_debug.log"

        rich_file_handler_debug = RichHandler(
            **RICH_HANDLER_DEBUG_CONFIG,
            console=Console(file=debug_log_file_path.open("w", encoding="utf8"),
                            width=DEFAULT_CONSOLE_WIDTH),
            level=manager.config_manager.settings_data['Runtime_Options']['log_level']
        )

        logger_debug.addHandler(rich_file_handler_debug)
        # aiosqlite_log = logging.getLogger("aiosqlite")
        # aiosqlite_log.setLevel(manager.config_manager.settings_data['Runtime_Options']['log_level'])
        # aiosqlite_log.addHandler(file_handler_debug)

    is_last_config = False
    while not is_last_config:
        logger = logging.getLogger("cyberdrop_dl")
        if manager.args_manager.all_configs:
            if len(logger.handlers) > 0:
                await log("Picking new config...", 20)

            configs_to_run = list(set(configs) - set(configs_ran))
            configs_to_run.sort()
            manager.config_manager.change_config(configs_to_run[0])
            configs_ran.append(configs_to_run[0])
            if len(logger.handlers) > 0:
                await log(f"Changing config to {configs_to_run[0]}...", 20)
                old_file_handler = logger.handlers[0]
                logger.removeHandler(logger.handlers[0])
                old_file_handler.close()

        logger.setLevel(manager.config_manager.settings_data['Runtime_Options']['log_level'])

        if cyberdrop_dl.utils.utilities.DEBUG_VAR:
            manager.config_manager.settings_data['Runtime_Options']['log_level'] = 10
        rich_file_handler = RichHandler(
            **RICH_HANDLER_CONFIG,
            console=Console(file=manager.path_manager.main_log.open("w", encoding="utf8"),
                            width=DEFAULT_CONSOLE_WIDTH),
            level=manager.config_manager.settings_data['Runtime_Options']['log_level']
        )

        logger.addHandler(rich_file_handler)
        import cyberdrop_dl.managers.console_manager
        cyberdrop_dl.managers.console_manager.LEVEL = manager.config_manager.settings_data['Runtime_Options'][
            'console_log_level']

        await log(
            f"Using Debug Log: {debug_log_file_path.resolve() if cyberdrop_dl.utils.utilities.DEBUG_VAR else None}", 10)
        await log("Starting Async Processes...", 20)
        await manager.async_startup()

        await log_spacer(20)
        await log("Starting CDL...\n", 20)
        if not manager.args_manager.sort_all_configs:
            try:
                async with manager.live_manager.get_main_live(stop=True):
                    await runtime(manager)
                    await post_runtime(manager)
            except Exception:
                if SENTRY_CLIENT is not None:
                    sentry_sdk.set_tag("config", manager.config_manager.loaded_config)
                    log_path = manager.path_manager.main_log if not cyberdrop_dl.utils.utilities.DEBUG_VAR else debug_log_file_path
                    sentry_sdk.get_current_scope().add_attachment(path=log_path, filename=log_path.name)
                SENTRY_CLIENT.close()
                await log("\nAn error occurred, please report this to the developer:", 50, exc_info=True)
                exit(1)

        await log_spacer(20)
        await manager.progress_manager.print_stats(start_time)

        is_last_config = not manager.args_manager.all_configs or not list(set(configs) - set(configs_ran))

        if SENTRY_CLIENT is not None:
            log_path = manager.path_manager.main_log if not cyberdrop_dl.utils.utilities.DEBUG_VAR else debug_log_file_path
            sentry_sdk.get_current_scope().add_attachment(path=log_path, filename=log_path.name)
            sentry_sdk.add_breadcrumb(message="Attaching log file", category="log")
            SENTRY_CLIENT.flush()
            # Remove the attachment from the scope
            # sentry_sdk.get_current_scope().clear()

        if is_last_config:
            await log_spacer(20)
            await log("Checking for Updates...", 20)
            await check_latest_pypi()
            await log_spacer(20)
            await log("Closing Program...", 20)
            await manager.close()
            await log_with_color("Finished downloading. Enjoy :)", 'green', 20, show_in_stats=False)

        await send_webhook_message(manager)
        await sent_apprise_notifications(manager)


def main():
    global start_time
    start_time = time.perf_counter()
    manager = startup()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with contextlib.suppress(RuntimeError):
        try:
            asyncio.run(director(manager))

        except KeyboardInterrupt:
            if SENTRY_CLIENT is not None:
                sentry_sdk.capture_message("Keyboard Interrupt")
                SENTRY_CLIENT.close()
            print_("\nTrying to Exit...")
            with contextlib.suppress(Exception):
                asyncio.run(manager.close())
            exit(1)
    if SENTRY_CLIENT is not None:
        SENTRY_CLIENT.close()
    loop.close()
    sys.exit(0)


if __name__ == '__main__':
    main()
