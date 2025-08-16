DOMAIN = "nhentai.net"
TEST_CASES = [
    (
        "https://nhentai.net/g/363796/",
        [
            {
                "url": r"re:nhentai.net/galleries/1941242/",
                "referer": "https://nhentai.net/g/363796",
                "album_id": "363796",
                "datetime": 1624512830,
            }
        ],
        25,
    ),
    (
        "https://nhentai.net/artist/tamabi/",
        [
            {
                "url": r"re:nhentai.net/galleries/",
                "download_folder": r"re:tamabi \[artist\] \(nHentai\)/",
            }
        ],
        8658,
    ),
]
