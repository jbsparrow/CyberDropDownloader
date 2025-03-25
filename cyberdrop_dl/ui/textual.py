from __future__ import annotations

import queue
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.widgets import Footer, RichLog, Static, TabbedContent, TabPane

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
        refresh_rate = self.manager.live_manager.refresh_rate
        self.set_interval(1 / refresh_rate, self.update_live)

    def update_live(self) -> None:
        content = self.manager.live_manager.live._renderable
        self.query_one(LiveConsole).update(content)  # type: ignore

        logger = self.query_one(RichLog)
        for msg in self.get_queued_log_messages():
            logger.write(msg, scroll_end=self.auto_scroll)

    def get_queued_log_messages(self) -> Iterable[Text]:
        while True:
            try:
                log_msg = self.queue.get(block=False)
                yield log_msg
                self.queue.task_done()
            except queue.Empty:
                break

    def action_toggle_dark(self) -> None:
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_pause_resume(self) -> None:
        self.manager.progress_manager.pause_or_resume()

    def action_toggle_logs(self) -> None:
        tabs = self.query_one(TabbedContent)
        current = tabs.active
        tabs.active = "main-ui" if current == "logs" else "logs"

    def action_toggle_auto_scroll_logs(self) -> None:
        self.auto_scroll = not self.auto_scroll

    def action_extract_cookies(self):
        # This is blocking. Not ideal but it works
        self.manager.client_manager.load_cookie_files()

    def action_quit(self):
        # Quit
        self.manager.shutdown(from_user=True)
        self.exit(0)

    def action_help_quit(self) -> None:
        """Bound to ctrl+C to alert the user that it no longer quits."""
        # Doing this because users will reflexively hit ctrl+C to exit
        self.notify("Press [b]ctrl+q[/b] to quit [b]cyberdrop-dl[/b]", title="Do you want to quit?")

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Custom system commands to remove `take screenshot` from the command palette."""

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
