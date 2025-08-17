DOMAIN = "toonily"
TEST_CASES = [
    (
        "https://toonily.com/serie/black-crow/",
        [
            {
                "url": "https://cdn.toonily.com/chapters/manga_66d8f7bfa8ed9/03ae6f538b989573c121b28f7af4f38a/01.jpg",
                "filename": "01.jpg",
                "referer": "https://toonily.com/serie/black-crow/chapter-1",
                "album_id": None,
                "datetime": 1725498328,
                "download_folder": r"re:Black Crow \(Toonily\)/Chapter 1",
            }
        ],
        1634,
    ),
    (
        "https://toonily.com/serie/black-crow/chapter-1/",
        [
            {
                "url": "https://cdn.toonily.com/chapters/manga_66d8f7bfa8ed9/03ae6f538b989573c121b28f7af4f38a/01.jpg",
                "filename": "01.jpg",
                "referer": "https://toonily.com/serie/black-crow/chapter-1",
                "album_id": None,
                "datetime": 1725498328,
                "download_folder": r"re:Black Crow \(Toonily\)/Chapter 1",
            }
        ],
        50,
    ),
]
