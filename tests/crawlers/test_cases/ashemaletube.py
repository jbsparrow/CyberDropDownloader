DOMAIN = "ashemaletube"
TEST_CASES = [
    # Direct image link
    (
        "https://cc.ashemaletube.com/images/2025-09/b8/68b658b8f35c3/68b658b8f35c3-full-0.jpg?size=x800",
        [
            {
                "url": "https://cc.ashemaletube.com/images/2025-09/b8/68b658b8f35c3/68b658b8f35c3-full-0.jpg",
                "filename": "68b658b8f35c3-full-0.jpg",
                "referer": "https://cc.ashemaletube.com/images/2025-09/b8/68b658b8f35c3/68b658b8f35c3-full-0.jpg?size=x800",
            }
        ],
    ),
    # Image page link
    (
        "https://www.ashemaletube.com/pics/265074/jjk-black-uniform/1/",
        [
            {
                "url": "https://cc.ashemaletube.com/images/2025-09/b8/68b658b8f35c3/68b658b8f35c3-full-0.jpg",
                "filename": "68b658b8f35c3-full-0.jpg [11374066].jpg",
                "referer": "https://www.ashemaletube.com/pics/265074/jjk-black-uniform/1",
                "album_id": None,
            }
        ],
    ),
    # Album page link
    (
        "https://www.ashemaletube.com/pics/265074/jjk-black-uniform/",
        [
            {
                "url": "re:https://cc.ashemaletube.com/images/2025-09/b8/68b658b8f35c3",
                "download_folder": r"re:JJK Black Uniform \[album\] \(aShemaleTube\)",
                "referer": "re:https://www.ashemaletube.com/pics/265074/jjk-black-uniform",
                "album_id": None,
            }
        ],
        5,
    ),
    # Video page link
    (
        "https://www.ashemaletube.com/videos/1133457/full-sissy-play-g041-1/",
        [
            {
                "url": "https://www.ashemaletube.com/videos/1133457",
                "filename": "Full Sissy Play - G041.1 [1133457][1080p].mp4",
                "referer": "https://www.ashemaletube.com/videos/1133457",
                "album_id": None,
            }
        ],
    ),
]
