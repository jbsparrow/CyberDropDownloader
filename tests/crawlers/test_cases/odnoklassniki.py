DOMAIN = "odnoklassniki"
TEST_CASES = [
    (
        "https://ok.ru/video/1416667269705",
        [
            {
                "url": "https://m.ok.ru/video/1416667269705",
                "filename": "73 Réplika_x264 [1416667269705][480p].mp4",
                "original_filename": "1416667269705.mp4",
                "referer": "https://ok.ru/video/1416667269705",
                "album_id": None,
                "datetime": 1566236730,
            }
        ],
    ),
    (
        "https://ok.ru/video/c637817",
        [
            {
                "url": "https://m.ok.ru/video/35013659257",
                "filename": "3. Las Voces de Zim [35013659257][480p].mp4",
                "original_filename": "35013659257.mp4",
                "referer": "https://ok.ru/video/35013659257",
                "download_folder": "re:Invader Zim",
                "album_id": "637817",
            }
        ],
        34,
    ),
]
