DOMAIN = "pimpbunny.com"
TEST_CASES = [
    (
        "https://pimpbunny.com/videos/vladislava-flexes-muscles-in-the-shower",
        [
            {
                "url": "https://pimpbunny.com/videos/vladislava-flexes-muscles-in-the-shower",
                "filename": "Vladislava Flexes Muscles In The Shower [344744][1440p].mp4",
                "referer": "https://pimpbunny.com/videos/vladislava-flexes-muscles-in-the-shower",
                "album_id": None,
            }
        ],
    ),
    (
        "https://pimpbunny.com/albums/boudoirbunny/",
        [
            {
                "url": "re:https://pimpbunny.com/get_image",
                "download_folder": r"re:Boudoirbunny \[album\] \(PimpBunny\)",
                "referer": "https://pimpbunny.com/albums/boudoirbunny/",
                "album_id": None,
            }
        ],
        73,
    ),
    (
        "https://pimpbunny.com/albums/models/boudoirbunny/",
        [
            {
                "url": "re:https://pimpbunny.com/get_image",
                "download_folder": r"re:BoudoIrBunny \[model\] \(PimpBunny\)/Boudoirbunny \[album\]",
                "referer": "https://pimpbunny.com/albums/boudoirbunny/",
                "album_id": None,
            }
        ],
        102,
    ),
    (
        "https://pimpbunny.com/onlyfans-models/boudoirbunny/",
        [],
        107,
    ),
]
