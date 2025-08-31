DOMAIN = "tiktok"
TEST_CASES = [
    (
        "https://tiktok.com/@_sophialocke_/video/7271803599443791146",
        [
            {
                "url": "https://tiktok.com/@_sophialocke_/video/7271803599443791146",
                "filename": "7271803599443791146.mp4",
                "referer": "https://tiktok.com/@_sophialocke_/video/7271803599443791146",
                "album_id": "7271803599443791146",
                "download_folder": r"re:_sophialocke_ \(TikTok\)/2023-08-26 - 7271803599443791146",
                "datetime": 1693098723,
            }
        ],
    ),
    (
        "https://www.tiktok.com/@_sophialocke_",
        [],
        140,
    ),
]
