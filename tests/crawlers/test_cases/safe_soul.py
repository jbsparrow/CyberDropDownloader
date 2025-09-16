DOMAIN = "safe.soul.lol"
TEST_CASES = [
    (
        "https://safe.soul.lol/GGCW62sr.dat",
        [
            {
                "url": "https://safe.soul.lol/GGCW62sr.dat",
                "filename": "GGCW62sr.dat",
                "referer": "https://safe.soul.lol/GGCW62sr.dat",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://safe.soul.lol/a/fH8aoyxD",
        [
            {
                "url": "https://safe.soul.lol/GGCW62sr.dat",
                "filename": "GGCW62sr.dat",
                "referer": "https://safe.soul.lol/GGCW62sr.dat",
                "album_id": "fH8aoyxD",
                "datetime": 1757997917,
                "download_folder": r"re:cdl_test \(Safe\.Soul\)",
            },
            {
                "url": "https://safe.soul.lol/rQPLKGeA.zip",
                "filename": "rQPLKGeA.zip",
                "referer": "https://safe.soul.lol/rQPLKGeA.zip",
                "album_id": "fH8aoyxD",
                "datetime": 1757997915,
                "download_folder": r"re:cdl_test \(Safe\.Soul\)",
            },
            {
                "url": "https://safe.soul.lol/8WXnedx1.bin",
                "filename": "8WXnedx1.bin",
                "referer": "https://safe.soul.lol/8WXnedx1.bin",
                "album_id": "fH8aoyxD",
                "datetime": 1757997914,
                "download_folder": r"re:cdl_test \(Safe\.Soul\)",
            },
        ],
    ),
]
