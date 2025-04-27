from __future__ import annotations

import asyncio
import contextlib
import queue
from typing import TYPE_CHECKING

import browser_cookie3
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.widgets import Footer, RichLog, Static, TabbedContent, TabPane

from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.text import Text
    from textual.screen import Screen

    from cyberdrop_dl.managers.manager import Manager

# Only global binding
PAUSE = Binding("p", "pause_resume", "Pause/Resume")

CORE_BINDINGS = [
    (VIEW_LOGS := ("l", "toggle_logs", "Switch To Logs/UI")),
    (AUTO_SCROLL_LOGS := ("s", "toggle_auto_scroll_logs", "AutoScroll ON/OFF")),
    (EXTRACT_COOKIES := ("ctrl+i", "extract_cookies", "Extract Cookies")),
]

LANDSCAPE_BINDINGS: list[Binding] = [PAUSE] + [Binding(*b, show=True) for b in CORE_BINDINGS]
PORTRAIT_BINDINGS: list[Binding] = [PAUSE] + [Binding(*b, show=False) for b in CORE_BINDINGS]

# Not used
DARK_MODE = ("d", "toggle_dark", "Dark Mode")


class LiveConsole(Static):
    def __init__(self) -> None:
        super().__init__(markup=False, shrink=True)

    def get_content_height(self, *args, **kwargs) -> int:
        # Adjustment for header tabs to prevent using a scrollbar
        return super().get_content_height(*args, **kwargs) - 3


class TextualUI(App[int]):
    TITLE = "cyberdrop-dl"
    SUB_TITLE = "Main UI"
    BINDINGS = LANDSCAPE_BINDINGS  # type: ignore

    def __init__(self, manager: Manager):
        super().__init__()
        self.manager = manager
        self.queue: queue.Queue[Text] = manager.textual_log_queue
        self.auto_scroll = True
        manager._textual_ui = self

    def compose(self) -> ComposeResult:
        def create_footer():
            footer = Footer()
            footer.compact = True
            return footer

        with TabbedContent():
            with TabPane("Main UI", id="main-ui"):
                # yield Header(show_clock=True)
                yield LiveConsole()
                yield create_footer()
            with TabPane("Logs", id="logs"):
                yield RichLog(highlight=True)
                yield create_footer()

    def on_mount(self):
        """Sets a refresh rate according to the config

        This is only for the main UI progress. Textual will compute the required refresh for its native stuff"""
        refresh_rate = self.manager.live_manager.refresh_rate
        self.set_interval(1 / refresh_rate, self.update_live)

    def update_live(self) -> None:
        """Get the current layout from the manager's live and manually update the content in the main UI"""

        # This is not officially supported by textual but it works
        # Doing this natively in textual will required a lot more work
        # It will not look as `good` either because textual widgets are still really basic
        # Ex: progress bar can only show % and ETA (no speed)
        content = self.manager.live_manager.live._renderable
        self.query_one(LiveConsole).update(content)  # type: ignore

        logger = self.query_one(RichLog)
        for msg in self.get_queued_log_messages():
            logger.write(msg, scroll_end=self.auto_scroll)

    def get_queued_log_messages(self) -> Iterable[Text]:
        """Get all messages from the queue handler"""
        while True:
            try:
                log_msg = self.queue.get(block=False)
                yield log_msg
                self.queue.task_done()
            except queue.Empty:
                break

    def action_toggle_dark(self) -> None:
        """Not used"""
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_pause_resume(self) -> None:
        self.manager.progress_manager.pause_or_resume()

    def action_toggle_logs(self) -> None:
        """Switch betwen the logs tab and the main UI"""
        tabs = self.query_one(TabbedContent)
        current = tabs.active
        tabs.active = "main-ui" if current == "logs" else "logs"

    def action_toggle_auto_scroll_logs(self) -> None:
        self.auto_scroll = not self.auto_scroll

    def action_extract_cookies(self):
        """Extract cookies right now and apply them to the current session

        This is IO blocking. Not ideal but it works"""

        try:
            got_cookies = self.manager.client_manager.load_cookie_files()
        except browser_cookie3.BrowserCookieError as e:
            log(e, 40)
        except Exception as e:
            log(e, 40, exc_info=e)
        else:
            if got_cookies:
                return self.notify("Cookies imported successfully", title="Done!")
            return self.notify("Please check your config values", title="No cookies imported!", severity="warning")

        self.notify("See logs for details", title="Cookie extraction failed!", severity="error")

    def action_quit(self):
        """Call manager shutdown before the UI quits"""
        self.manager.shutdown(from_user=True)
        self.exit(0)

    def action_help_quit(self) -> None:
        """Bound to ctrl+C to alert the user that it no longer quits."""
        self.notify("Press [b]ctrl+q[/b] to quit", title="Do you want to quit?")

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Custom system commands to remove `take screenshot` and `change theme` from the command palette."""

        yield SystemCommand(
            "Pause/Resume",
            "Pause all scraping and downloading progress",
            self.action_pause_resume,
        )

        yield SystemCommand(
            "AutoScroll ON/OFF",
            "Toggle auto scroll in the logs tab",
            self.action_toggle_auto_scroll_logs,
        )

        yield SystemCommand(
            "Extract Cookies",
            "Extract cookies from browser right now and apply them to the current session",
            self.action_extract_cookies,
        )

        if screen.query("HelpPanel"):
            yield SystemCommand(
                "Hide keys and help panel",
                "Hide the keys and help panel",
                self.action_hide_help_panel,
            )
        else:
            yield SystemCommand(
                "Show keys and help panel",
                "Show help and a summary of available keys",
                self.action_show_help_panel,
            )

        yield SystemCommand(
            "Quit the application",
            "Quit the application as soon as possible",
            self.action_quit,
        )


class PortraitTextualUI(TextualUI):
    BINDINGS = PORTRAIT_BINDINGS  # type: ignore


@contextlib.asynccontextmanager
async def textual_ui(manager: Manager):
    if manager.live_manager.use_textual:
        UI = TextualUI
        if manager.parsed_args.cli_only_args.portrait:
            UI = PortraitTextualUI
        textual_ui = UI(manager)
        ui_task = asyncio.create_task(textual_ui.run_async())
        try:
            yield
        finally:
            textual_ui.exit()
            await ui_task
    else:
        yield
