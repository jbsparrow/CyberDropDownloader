from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import itertools
import random
from typing import TYPE_CHECKING, Any, ClassVar, final

from rich.columns import Columns
from rich.markup import escape
from rich.progress import SpinnerColumn
from rich.spinner import Spinner
from rich.text import Text

from cyberdrop_dl import __version__
from cyberdrop_dl.progress import create_test_live, strip_markup, truncate_float
from cyberdrop_dl.progress.overflow import OverFlowPanel

if TYPE_CHECKING:
    from collections.abc import Generator


_generate_unique_id = itertools.count(1).__next__


@final
@dataclasses.dataclass(slots=True, frozen=True)
class StatusMessage:
    description: str = f" cyberdrop-dl [blue]v{__version__}[/blue]"
    _messages: dict[int, tuple[Spinner, Text]] = dataclasses.field(init=False, default_factory=dict)
    _cols: Columns = dataclasses.field(init=False, default_factory=Columns)

    def shutdown(self) -> None:
        self._cols.renderables[0] = self.description + " [yellow](shutting down...)[/yellow]"

    def __post_init__(self) -> None:
        self._cols.renderables.extend([self.description, Spinner("point", style="green"), "|"])

    def __rich__(self) -> Columns:
        return self._cols

    def _append_msg(self, msg: object) -> int:
        msg_id = _generate_unique_id()
        self._messages[msg_id] = new_msg = Spinner("dots3", style="green"), Text(escape(str(msg)))
        self._cols.renderables.extend(new_msg)
        return msg_id

    @contextlib.contextmanager
    def __call__(self, msg: object) -> Generator[None]:
        msg_id = self._append_msg(msg)
        try:
            yield
        finally:
            self._pop_msg(msg_id)

    def _pop_msg(self, msg_id: int) -> None:
        del self._messages[msg_id]
        self._cols.renderables[3:] = itertools.chain.from_iterable(self._messages.values())

    def __json__(self) -> dict[str, Any]:
        return {
            "description": strip_markup(self.description).strip(),
            "messages": tuple(strip_markup(text.plain) for _, text in self._messages.values()),
        }

    async def simulate(self) -> None:
        await asyncio.sleep(2)

        async def show(msg: str) -> None:
            with self(msg):
                await asyncio.sleep(random.random() * 5)

        async with asyncio.TaskGroup() as tg:
            for idx in range(1, 10):
                _ = tg.create_task(show(f"test msg {idx}"))


@final
class ScrapingPanel(OverFlowPanel):
    unit: ClassVar[str] = "URL"

    def __init__(self) -> None:
        super().__init__(
            SpinnerColumn("dots3"),
            "[progress.description]{task.description}",
            max_rows=3,
            expand=False,
        )

    @contextlib.contextmanager
    def new(self, url: object) -> Generator[None]:
        task = self._add_task(url)
        try:
            yield
        finally:
            self._remove_task(task)

    async def simulate(self) -> None:
        a = self._add_task("url_a")
        b = self._add_task("url_b")
        c = self._add_task("url_c")
        await asyncio.sleep(5)
        d = self._add_task("url_d")
        _ = self._add_task("http://example.com/file1")
        _ = self._add_task("http://example.com/file2")
        await asyncio.sleep(5)
        self._remove_task(a)
        self._remove_task(b)
        self._remove_task(c)
        self._remove_task(d)
        await asyncio.sleep(2)
        with self.new("http://github.com"):
            await asyncio.sleep(2)
            with self.new("http://github2.com"):
                await asyncio.sleep(2)
            with self.new("http://github3.com"):
                await asyncio.sleep(2)

    def __json__(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "url": strip_markup(task.description),
                "elapsed": truncate_float(task.elapsed),
            }
            for task in self._progress.tasks
        )


if __name__ == "__main__":
    import rich

    panel = ScrapingPanel()
    status = StatusMessage()
    with create_test_live(status):
        asyncio.run(status.simulate())

    with create_test_live(panel):
        asyncio.run(panel.simulate())

    status._append_msg("test msg1")
    status._append_msg("test msg2")
    dump = {"scrape": panel.__json__(), "status": status.__json__()}
    rich.print(dump)
