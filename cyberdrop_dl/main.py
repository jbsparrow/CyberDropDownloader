import sys

from cyberdrop_dl import env
from cyberdrop_dl.director import Director


def main(*, profiling: bool = False, ask: bool = True):
    if not (profiling or env.PROFILING):
        return run()
    from cyberdrop_dl.profiling import profile

    profile(run, ask)


def run() -> None:
    director = Director()
    sys.exit(director.run())


if __name__ == "__main__":
    main()
