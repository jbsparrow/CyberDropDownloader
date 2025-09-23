import sys
import warnings


def main() -> None:
    sys.exit(run())


def run(args: tuple[str, ...] | None = None) -> str | int:
    try:
        warnings.filterwarnings("ignore", category=SyntaxWarning, message="invalid escape sequence.*")
        from cyberdrop_dl.director import Director

        director = Director(args)
        return director.run()
    except KeyboardInterrupt:
        return "\nKeyboardInterrupt"


if __name__ == "__main__":
    main()
