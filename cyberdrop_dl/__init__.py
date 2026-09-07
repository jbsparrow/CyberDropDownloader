from __future__ import annotations

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Generator

__dist_name__ = "cyberdrop-dl-patched"
__version__ = "10.8.0"
__repo_url__ = "https://github.com/Cyberdrop-DL/cyberdrop-dl"


def dependencies() -> Generator[tuple[str, str | None]]:
    import importlib.metadata
    import re

    for req in importlib.metadata.distribution(__dist_name__).requires or []:
        m = re.match(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?", req)
        assert m is not None
        pkg = m.group(0)
        try:
            version = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            version = None

        yield pkg, version
