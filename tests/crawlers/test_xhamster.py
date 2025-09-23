import pytest

from cyberdrop_dl.crawlers.xhamster import _decode_hex_url


@pytest.mark.parametrize(
    "raw_url, expected_output",
    [
        (
            "01fe0bef492d94cb623a2e4c49fbe1239f7e1105bda61daecca10c105273f634a5cca31dc107eaa9d731f0ec43f44d54f4439ee517bc9cacc3c439bfe70a4d4f5ff915a90eb50f9237ed3dc29ba5a4f40e7e11de62611932102c92cb47692cad3bd5f8cbe489f42dc4d1c6f776d75a93ea0126e796002457f60174e9224588c7902d5de946f51808a0f9aed4d43d78fd56a085d97e2d817f5a69dec286a568a7700d3fc32ad5786d03df0439b41c9ed76a8b733bdc427f5b374aab206289d7a8be11e0449064d64efc64a41708207b7282",
            "https://video-nss-a.xhcdn.com/f_bjveXDoEYe3nrBnyILCA==,1758589200/media=hls4/multi=256x144:144p:,426x240:240p:,854x480:480p:,1280x720:720p:,1920x1080:1080p:,3840x2160:2160p:/027/453/344/_TPL_.av1.mp4.m3u8",
        ),
        (
            "030251bf078b3c34108b5ec467b21781c6e865fcbe2f0fec4fa03c7bedf6634783bb816af8803b19971f0360b2d33dfa77e7e170544e6f3a69d77e93526ba71710858822c5b0c7371fe8af1aa21f7db5e46a1b329eceeceeadbb845e6398c431a107cdee5c478335d3e0b46e9be59e4b492a702f0c257339238c63607de262e7c8d30bba40d8febad01b1c33cf2b177b1a3e04d826286b9aaf45bf6c4229b2ea31de015312067881b8e97e25df7fdc",
            "https://video-nss-a.xhcdn.com/if6CPa9MjylU2jNYhxtjWg==,1758596400/media=hls4/multi=256x144:144p:,426x240:240p:,854x480:480p:,1280x720:720p:/017/537/816/_TPL_.av1.mp4.m3u8",
        ),
    ],
)
def test_decode_hex_url(raw_url: str, expected_output: str) -> None:
    result = _decode_hex_url(raw_url)
    assert result == expected_output
