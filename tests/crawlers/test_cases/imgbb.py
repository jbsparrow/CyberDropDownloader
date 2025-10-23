DOMAIN = "imgbb"
TEST_CASES = [
    (
        "https://ibb.co/FbtMCg43",
        [
            {
                "url": "https://i.ibb.co/DDnyT5fW/Long-toes-are-the-best.jpg",
                "filename": "Long-toes-are-the-best.jpg",
                "referer": "https://ibb.co/FbtMCg43",
                "album_id": None,
                "datetime": 1740984052,
            }
        ],
    ),
    (
        "https://i.ibb.co/DDnyT5fW/Long-toes-are-the-best.jpg",
        [
            {
                "url": "https://i.ibb.co/DDnyT5fW/Long-toes-are-the-best.jpg",
                "filename": "Long-toes-are-the-best.jpg",
                "referer": "https://i.ibb.co/DDnyT5fW/Long-toes-are-the-best.jpg",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://ibb.co/album/yhdTNv",
        [
            {
                "url": "re:.jpg",
                "album_id": "yhdTNv",
                "download_filename": r"re:ALEXA_2024/25 \(ImgBB\)",
                "datetime": None,
            }
        ],
        1537,
    ),
]
