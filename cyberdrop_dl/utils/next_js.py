"""Utils to parse Next.JS v13 Flight Data

We only parse a subset of the spec (w/ regex instead of a state machine) and discard any non Payload chunk"""

from __future__ import annotations

import base64
import dataclasses
import re
from collections.abc import Generator
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, NewType, final

from bs4 import BeautifulSoup

from cyberdrop_dl.utils import css, json

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping

type _ChunkID = str
FlightData = NewType("FlightData", str)
NextJSFlight = dict[_ChunkID, list[dict[str, Any]]]
# Map of chunk_id (hex index of the chunk) -> list of all the objects (components) created from that chunk

_match_init_push = re.compile(r"\(self\.__next_f\s?=\s?self\.__next_f\s?\|\|\s?\[\]\)\.push\((\[.+?\])\)").match


class _Magic(StrEnum):
    ERROR = "<ERROR>"
    INIT = "<INIT>"


class _FlightType(IntEnum):
    BOOTSTRAP = 0
    PAYLOAD = 1
    FORM_STATE = 2
    BINARY = 3


_Push = tuple[_FlightType, str]


@final
@dataclasses.dataclass(slots=True, order=True)
class _FlightChunk:
    index: int = dataclasses.field(init=False)
    id: _ChunkID
    marker: str | None
    data: str

    decoded_data: Any = dataclasses.field(init=False)  # pyright: ignore[reportAny]
    resolved: bool = dataclasses.field(init=False, default=False)

    def __post_init__(self) -> None:
        self.index = int(self.id, base=16)
        self.decoded_data = self.data


@final
@dataclasses.dataclass(slots=True)
class LazyChunk:
    reference: _ChunkID


def _split_push(push: str) -> tuple[str, str, str]:
    chunk_id, sep, data = push[1:-1].partition(",")
    return chunk_id.strip(), sep, data.strip().rstrip(",").strip()


def _dedent_push(push: str) -> str:
    push = push.strip()
    if push.startswith(("{", "[")) and push.endswith(("}", "]")):
        parts = filter(None, _split_push(push))
        push = "".join((push[0], *parts, push[-1]))
    return push


def _extract_raw_pushes(soup: BeautifulSoup) -> Generator[str]:
    push = "self.__next_f.push("
    for script in css.iselect(soup, "script:-soup-contains-own('self.__next_f')"):
        content = script.get_text(strip=True).strip()
        if m := _match_init_push(content):
            yield _dedent_push(m.group(1))
        else:
            try:
                start = content.index(push) + len(push)
            except ValueError:
                continue

            yield _dedent_push(content[start : content.rindex(")")])


def _decode_push(raw_push: str) -> _Push:
    push: list[Any] = json.loads(raw_push)  # pyright: ignore[reportAny]
    match push:
        case [_FlightType.BOOTSTRAP]:
            return _FlightType.BOOTSTRAP, _Magic.INIT
        case [_FlightType.PAYLOAD | _FlightType.FORM_STATE as type_, value]:
            return _FlightType(type_), value
        case [_FlightType.BINARY, value]:
            return _FlightType.BINARY, base64.b64decode(value.encode()).decode()
        case _:
            raise RuntimeError(f"Invalid NextJS push found: {push!r}")


def _extract_flight_data(raw_pushes: Iterable[str]) -> Generator[str]:
    found_init: bool = False
    for flight_type, data in map(_decode_push, raw_pushes):
        if flight_type is _FlightType.BOOTSTRAP:
            if found_init:
                raise RuntimeError("NextJS data was initialized multiple times")
            found_init = True

        elif flight_type is _FlightType.PAYLOAD:
            if not found_init:
                raise RuntimeError("Found NextJS push without initialized array")
            yield data


def _parse_raw_chunks(flight_data: FlightData) -> Generator[_FlightChunk]:
    for line in flight_data.splitlines():
        if line.startswith(":HL"):
            continue
        m = re.match("^([0-9a-f]+):(T[0-9A-Fa-f]+,|[A-SU-Z]{0,1})", line)
        assert m
        chunk_id, marker = m.groups()
        marker = marker or None
        data = line[m.end() :].strip()
        if marker and marker.startswith("T"):
            length = int(marker[1:-1], 16)
            data, rest = data[:length], FlightData(data[length:])
            yield _FlightChunk(chunk_id, "T", data)
            if rest:
                yield from _parse_raw_chunks(rest)
        else:
            yield _FlightChunk(chunk_id, marker, data)


def _revive_str(value: str) -> str | int | LazyChunk | None:  # noqa: PLR0911
    if value[0] != "$":
        return value

    if value == "$":
        return ""

    match value[1]:
        case "$":
            return value[2:]
        case "@" | "L":
            chunk_id = value[2:]
            return LazyChunk(chunk_id)
        case "u":
            return None
        case "D":
            return value[2:]
        case "n":
            return int(value[2:])
        case _:
            return value[1:]


def _revive(value: object, /, chunks: Mapping[_ChunkID, _FlightChunk]) -> Any:  # noqa: PLR0911
    if not value:
        return value

    match value:
        case str():
            obj = _revive_str(value)
            if type(obj) is LazyChunk:
                return _revive(chunks[obj.reference], chunks)
            return obj

        case list():
            for idx, obj in enumerate(value):
                value[idx] = _revive(obj, chunks)
            return value

        case dict():
            for key, obj in value.items():
                value[key] = _revive(obj, chunks)
            return value

        case _FlightChunk():
            _initialize(value, chunks)
            return value.decoded_data

        case _:
            return value


def _initialize(chunk: _FlightChunk, /, chunks: Mapping[_ChunkID, _FlightChunk]) -> None:
    if chunk.resolved:
        return
    try:
        raw_value = json.loads(chunk.decoded_data) if isinstance(chunk.decoded_data, str) else chunk.decoded_data
    except json.JSONDecodeError:
        chunk.decoded_data = _Magic.ERROR
    else:
        chunk.decoded_data = _revive(raw_value, chunks)
    finally:
        chunk.resolved = True


def _hidrate_chunks(raw_chunks: Iterable[_FlightChunk]) -> Generator[_FlightChunk]:
    chunks_map = {chunk.id: chunk for chunk in sorted(raw_chunks)}
    for chunk in chunks_map.values():
        _initialize(chunk, chunks_map)
        yield chunk


def extract_flight_data(soup: BeautifulSoup) -> FlightData:
    return FlightData("".join(_extract_flight_data(_extract_raw_pushes(soup))).replace('"$undefined"', "null"))


def ifind(next_flight: NextJSFlight, attr: str, *attrs: str) -> Generator[dict[str, Any]]:
    """Yield every object within `next_flight` that have the required `attrs`."""
    needed = frozenset([attr, *attrs])

    def walk(obj: object) -> Generator[dict[str, Any]]:
        if isinstance(obj, dict):
            if needed.issubset(obj):
                yield obj
            else:
                for v in obj.values():
                    yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)

    for ele in next_flight.values():
        yield from walk(ele)


def find(next_flight: NextJSFlight, attr: str, *attrs: str) -> dict[str, Any]:
    """Get the first object within `next_flight` that have the required `attrs`."""
    return next(ifind(next_flight, attr, *attrs))


def extract(soup: BeautifulSoup) -> NextJSFlight:
    return parse(extract_flight_data(soup))


def parse(flight_data: FlightData, /) -> NextJSFlight:
    return {chunk.id: chunk.decoded_data for chunk in _hidrate_chunks(_parse_raw_chunks(flight_data))}  # pyright: ignore[reportAny]


def remove_unused_tags(file: Path) -> None:
    soup = BeautifulSoup(file.read_text(), "html.parser")
    for tag in soup.find_all():
        if tag.name.lower() not in {"script", "html", "body"}:
            tag.decompose()

    file.write_text(soup.prettify())


def data(tag: BeautifulSoup) -> Any:
    return json.loads(css.select_text(tag, "#__NEXT_DATA__"))


if __name__ == "__main__":
    import sys
    from pathlib import Path

    file = Path(sys.argv[1])
    soup = BeautifulSoup(file.read_text(), "html.parser")
    flight_data = extract_flight_data(soup)
    Path("flight_data.txt").write_text(flight_data)
    decoded = parse(flight_data)
    Path("flight_data_decoded.json").write_text(json.dumps(decoded, indent=2, ensure_ascii=False))
