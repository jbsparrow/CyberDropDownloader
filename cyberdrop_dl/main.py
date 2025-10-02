import sys
import warnings


def main() -> None:
    from cyberdrop_dl.utils.logger import catch_exceptions

    sys.exit(catch_exceptions(run)())


def run(args: tuple[str, ...] | None = None) -> str | int | None:
    warnings.filterwarnings("ignore", category=SyntaxWarning, message="invalid escape sequence.*")
    from cyberdrop_dl.director import Director

    director = Director(args)
    return director.run()


if __name__ == "__main__":
    main()
