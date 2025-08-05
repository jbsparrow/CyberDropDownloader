DOMAIN = "pixhost"
TEST_CASES = [
    (
        "https://pixhost.to/show/491/538303562_035.jpg",
        [
            {
                "url": "https://img100.pixhost.to/images/491/538303562_035.jpg",
                "filename": "538303562_035.jpg",
                "referer": "https://pixhost.to/show/491/538303562_035.jpg",
                "album_id": None,  # TODO: get the album id for individual images
            },
        ],
    ),
]
