DOMAIN = "tiktok"
TEST_CASES = [
    (
        "https://tiktok.com/@_sophialocke_/video/7271803599443791146",
        [
            {
                "url": "https://www.tiktok.com/@_sophialocke_/video/7271803599443791146",
                "original_filename": "7271803599443791146.mp4",
                "referer": "https://www.tiktok.com/@_sophialocke_/video/7271803599443791146",
                "album_id": "7271803599443791146",
                "download_folder": r"re:_sophialocke_ \(TikTok\)",
                "datetime": 1693098723,
            },
            {
                "url": "https://www.tiktok.com/music/original-audio-7271803602241456938",
                "filename": "original sound - _sophialocke_ [7271803602241456938].mp3",
                "original_filename": "original sound - _sophialocke_.mp3",
                "referer": "https://www.tiktok.com/@_sophialocke_/video/7271803599443791146",
                "debrid_link": "ANY",
                "album_id": "7271803599443791146",
                "download_folder": r"re:_sophialocke_ \(TikTok\)",
                "datetime": 1693098723,
            },
        ],
    ),
    (
        "https://www.tiktok.com/@ploense",
        [],
        2,
    ),
    (
        "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374",
        [
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/0",
                "debrid_url": "ANY",
                "filename": "7545228111973977374_img000.jpeg",
                "referer": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374",
                "album_id": "7545228111973977374",
                "download_folder": r"re:ggwendollyn \(TikTok\)",
                "datetime": 1756760334,
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/1",
                "filename": "7545228111973977374_img001.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/2",
                "filename": "7545228111973977374_img002.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/3",
                "filename": "7545228111973977374_img003.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/4",
                "filename": "7545228111973977374_img004.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/5",
                "filename": "7545228111973977374_img005.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/6",
                "filename": "7545228111973977374_img006.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/7",
                "filename": "7545228111973977374_img007.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/8",
                "filename": "7545228111973977374_img008.jpeg",
            },
            {
                "url": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374/9",
                "filename": "7545228111973977374_img009.jpeg",
            },
            {
                "url": "https://www.tiktok.com/music/plug-walk-remix-7490972580300573470",
                "filename": "plug walk remix [7490972580300573470].mp3",
                "original_filename": "plug walk remix.mp3",
                "referer": "https://www.tiktok.com/@ggwendollyn/photo/7545228111973977374",
                "debrid_link": "ANY",
                "album_id": "7545228111973977374",
                "download_folder": r"re:ggwendollyn \(TikTok\)/Audios",
                "datetime": 1756760334,
            },
        ],
        None,
        {
            "skip": "post was deleted",
        },
    ),
]
