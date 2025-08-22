import re

DOMAIN = "iceyfile"
TEST_CASES = [
    # This will fail. iceyfile now always requires a 1 type access only captcha ofr individual files
    (
        "https://iceyfile.com/be60cca8a9dec177/fff.png",
        [
            {
                "url": "re:" + re.escape("https://srv1.iceyfile.net/be60cca8a9dec177/fff.png?download_token="),
                "filename": "fff",
                "referer": "https://iceyfile.com/be60cca8a9dec177/fff.png",
                "album_id": None,
                "datetime": 1755488372,
            }
        ],
    ),
    (
        "https://iceyfile.com/folder/75061972f799eeacba32ac81f37493bc/CDL_test",
        [
            {
                "url": "re:" + re.escape("https://srv1.iceyfile.net/be60cca8a9dec177/fff.png?download_token="),
                "filename": "fff.png",
                "referer": "https://iceyfile.com/be60cca8a9dec177/fff.png",
                "download_folder": r"re:CDL_test \(Iceyfile\)",
                "album_id": "75061972f799eeacba32ac81f37493bc",
                "datetime": 1755491602,
            }
        ],
    ),
]
