from typing import Any

import pytest

from cyberdrop_dl.downloader import mega_nz


@pytest.mark.parametrize(
    "attrs, key, expected_output",
    [
        (
            b"$7\xcc\x8e\x05G\r\x18\x9e\xa421\xb3b\x1bv\xc3\xf7\xc7\x1c\xa9N\xcd\x12\xc2\xe1D\xb3\xfe\x1c<\xd7\x07\xd2v\x8d\xac\x14\xfc\xc2\xdd\x1f+\x9c\xd4G\x86A\xef?\xd1*\xc9\xf2)\x97\x80\xcc~\x99n\xc2X\xee\xcc\xfb\xe2\x05\xc6\x01C'\xc9\xbc,\xab\xa4j\x93\xb7",
            (3008087885, 1189702641, 1874401314, 489354689),
            {
                "c": "GDO1Ezwa5QTio14u5dIHXQR0Tgtk",
                "n": "Messages — OnlyFans(4).mp4",
            },
        ),
        (
            b'\xb6E[\xe6K\xbd\xf9\t\x95\x1d\xcb\xe9\xa3N\x13 \xbb\xf3\x15\xf9H\xb7\x11\xe8\xec\\\x92"\x1d\xb45ia\xaf\x89v\xa5\xab\xd3\xb1\xa8Y\xbb\xe0\x81g\x8e\x19\x1b\xf5b\xa8\x1f`\x9d\x05b<\x13\x7fM\x07\xe0\xea',
            (1958576006, 489861153, 2106943810, 3660715586),
            {
                "c": "KGUlr2utItBMvUIKW-RuwQSUdM9j",
                "n": "SAM4}.png",
            },
        ),
    ],
)
def test_decrypt_attr(attrs: bytes, key: mega_nz.U32IntSequence, expected_output: dict[str, Any]):
    output = mega_nz.decrypt_attr(attrs, key)
    assert output == expected_output
