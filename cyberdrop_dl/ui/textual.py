from __future__ import annotations

import queue
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.widgets import Footer, RichLog, Static, TabbedContent, TabPane

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.text import Text

    from cyberdrop_dl.managers.manager import Manager

DARK_MODE = ("d", "toggle_dark", "Dark Mode")
PAUSE = ("p", "pause_resume", "Pause/Resume")
VIEW_LOGS = ("l", "toggle_logs", "Switch To Logs/UI")
AUTO_SCROLL_LOGS = ("s", "toggle_auto_scroll_logs", "AutoScroll ON/OFF")
EXTRACT_COOKIES = ("ctrl+i", "extract_cookies", "Extract Cookies")


class LiveConsole(Static):
    def __init__(self) -> None:
        super().__init__(markup=False, shrink=True)

    def get_content_height(self, *args, **kwargs) -> int:
        # Adjustment for header tabs to prevent using a scrollbar
        return super().get_content_height(*args, **kwargs) - 3


class TextualUI(App):
    TITLE = "cyberdrop-dl"
    SUB_TITLE = "Main UI"
    BINDINGS = [PAUSE, VIEW_LOGS, AUTO_SCROLL_LOGS, EXTRACT_COOKIES]  # noqa: RUF012

    def __init__(self, manager: Manager):
        super().__init__()
        self.manager = manager
        self.queue: queue.Queue[Text] = queue.Queue()
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

    def get_queued_log_messages(self) -> Generator[Text]:
        while True:
            try:
                log_msg = self.queue.get(block=False)
                yield log_msg
                self.queue.task_done()
            except queue.Empty:
                break

    def log_to_ui(self, msg: Text) -> None:
        self.queue.put_nowait(msg)

    def action_toggle_dark(self) -> None:
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_pause_resume(self) -> None:
        # Not implemented. Needs GH-PR-#820
        return

    def action_toggle_logs(self) -> None:
        tabs = self.query_one(TabbedContent)
        current = tabs.active
        tabs.active = "main-ui" if current == "logs" else "logs"

    def action_toggle_auto_scroll_logs(self) -> None:
        self.auto_scroll = not self.auto_scroll

    def action_extract_cookies(self):
        # This is blocking. Not ideal but it works
        self.manager.client_manager.load_cookie_files()
