import datetime
from typing import Annotated

from cyclopts import App, Parameter

from cyberdrop_dl.commands import CLIarguments
from cyberdrop_dl.commands.scrape import prepare_manager, scrape
from cyberdrop_dl.config import Config
from cyberdrop_dl.constants import USE_RETRY_PATH
from cyberdrop_dl.models import ConfigModel
from cyberdrop_dl.scrape_source import RetryScrapeSource, RetrySource

app = App(name="retry", help="Retry downloads from the database")


@Parameter(name="*")
class RetryArgs(ConfigModel):
    from_: Annotated[datetime.date, Parameter(name="from")] = datetime.date(1970, 1, 1)
    "Only retry URLs added to the database since this date"

    to: Annotated[datetime.date | None, Parameter(show_default=True)] = None
    "Only retry URLs added to the database before this date"

    force_original_path: bool = False
    "Ignore current config options and force downloads to use the exact same path of the initial download attempt"

    cli_args: CLIarguments | None = None
    cli_overrides: Config | None = None


def _tomorrow() -> datetime.date:
    return datetime.datetime.now(tz=datetime.UTC).date() + datetime.timedelta(days=1)


def create_retry_src(retry: RetrySource, args: RetryArgs | None = None) -> RetryScrapeSource:
    args = args or RetryArgs()
    if args.force_original_path:
        USE_RETRY_PATH.set(True)

    return RetryScrapeSource(retry, after=args.from_, before=args.to or _tomorrow())


@app.command
def failed(*, args: RetryArgs | None = None) -> None:
    """Retry failed downloads"""
    args = args or RetryArgs()
    with prepare_manager(args.cli_args, args.cli_overrides)() as manager:
        scrape(manager, source=create_retry_src(RetrySource.FAILED, args))


@app.command(name="all")
def retry_all(*, args: RetryArgs | None = None) -> None:
    "Retry all downloads"
    args = args or RetryArgs()
    with prepare_manager(args.cli_args, args.cli_overrides)() as manager:
        scrape(manager, source=create_retry_src(RetrySource.ALL, args))
