import re

DOMAIN = "iceyfile"
TEST_CASES = [
    # This will fail. iceyfile now always requires a 1 type access only captcha
    (
        "https://iceyfile.com/b0828955298d065a/fff",
        [
            {
                "url": "re:" + re.escape("https://srv1.iceyfile.net/b0828955298d065a/fff?download_token="),
                "filename": "fff",
                "referer": "https://iceyfile.com/b0828955298d065a/fff",
                "album_id": None,
                "datetime": 1755488372,
            }
        ],
    )
]
