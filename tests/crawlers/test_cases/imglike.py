DOMAIN = "imglike.com"
TEST_CASES = [
    (
        "https://imglike.com/image/Palm-Desert-Resuscitation-Education-%28YourCPRMD.com%29.L1xHc",
        [
            {
                "url": "https://imglike.com/images/2022/10/20/Palm-Desert-Resuscitation-Education-YourCPRMD.com.png",
                "filename": "Palm-Desert-Resuscitation-Education-YourCPRMD.com.png",
                "referer": "https://imglike.com/image/L1xHc",
                "album_id": None,
                "datetime": 1666261421,
            }
        ],
    ),
    (
        "https://imglike.com/album/Kara-Del-Toro-Naked.cG7l",
        [
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-6.jpg",
                "filename": "Nude-Kara-Del-Tori-6.jpg",
                "referer": "https://imglike.com/image/LGXgd",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-5.jpg",
                "filename": "Nude-Kara-Del-Tori-5.jpg",
                "referer": "https://imglike.com/image/LGxFT",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-3.jpg",
                "filename": "Nude-Kara-Del-Tori-3.jpg",
                "referer": "https://imglike.com/image/LGB1z",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-4.jpg",
                "filename": "Nude-Kara-Del-Tori-4.jpg",
                "referer": "https://imglike.com/image/LG6lR",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-2.jpg",
                "filename": "Nude-Kara-Del-Tori-2.jpg",
                "referer": "https://imglike.com/image/LG4Jg",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
            {
                "url": "https://imglike.com/images/2022/06/23/Nude-Kara-Del-Tori-1.jpg",
                "filename": "Nude-Kara-Del-Tori-1.jpg",
                "referer": "https://imglike.com/image/LGP7s",
                "download_folder": r"re:Kara Del Toro Naked \(ImgLike\)",
                "datetime": None,
                "album_id": "cG7l",
            },
        ],
    ),
    (
        "https://imglike.com/bonton18/albums",
        [
            {
                "url": "https://imglike.com/images/2022/10/03/01__4_.jpg",
                "filename": "01__4_.jpg",
                "referer": "https://imglike.com/image/L1iUm",
                "album_id": "iNlR",
            }
        ],
    ),
    (
        # Fails with aiohttp and works with curl-cffi
        "https://imglike.com/album/D%C3%A9sir%C3%A9e-Nick-Boob-Slip-at-unesco-benefiz-gala%2C-2001.vihF",
        [
            {
                "url": "https://imglike.com/images/2020/12/03/Desiree-Nick-Boob-Slip-at-unesco-benefiz-gala-2001-1.jpg",
                "filename": "Desiree-Nick-Boob-Slip-at-unesco-benefiz-gala-2001-1.jpg",
                "referer": "https://imglike.com/image/rq5gV",
                "album_id": "vihF",
                "download_folder": r"re:Désirée Nick Boob Slip at unesco-benefiz gala, 2001 \(ImgLike\)",
                "datetime": None,
            },
        ],
        10,
    ),
]
