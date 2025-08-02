DOMAIN = "pixhost"
TEST_CASES = [
    (
        "https://pixhost.to/show/491/538303562_035.jpg",
        [
            {
                "url": "https://img100.pixhost.to/images/491/538303562_035.jpg",
                "filename": "538303562_035.jpg",
                "referer": "https://pixhost.to/show/491/538303562_035.jpg",
                "album_id": None,
            },
        ],
    ),
    (
        "https://t100.pixhost.to/thumbs/491/538303428_001.jpg",
        [
            {
                "url": "https://img100.pixhost.to/images/491/538303428_001.jpg",
                "filename": "538303428_001.jpg",
                "referer": "https://pixhost.to/show/491/538303428_001.jpg",
                "album_id": None,
            },
        ],
    ),
    (
        "https://pixhost.to/gallery/pgv5s",
        [
            {
                "url": "https://img31.pixhost.to/images/183/107062500_instasave.jpg",
                "filename": "107062500_instasave.jpg",
                "referer": "https://pixhost.to/show/183/107062500_instasave.jpg",
                "album_id": "pgv5s",
            },
        ],
        7,
    ),
]
