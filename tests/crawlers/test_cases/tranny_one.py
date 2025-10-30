DOMAIN = "tranny.one"
TEST_CASES = [
    # Video
    (
        "https://www.tranny.one/view/1156655/",
        [
            {
                "url": r"re:https://stream.tranny.one/.+/3137805.mp4",
                "filename": "Femboy and the Hunk [1156655].mp4",
                "referer": "https://www.tranny.one/view/1156655",
                "datetime": None,
            }
        ],
    ),
    # Search
    (
        "https://www.tranny.one/search/ruby+wren/",
        [],
        2,
    ),
    # Album
    (
        "https://www.tranny.one/pics/album/2967/",
        [
            {
                "url": "re:https://pics.tranny.one/work/orig/2904/339248",
                "download_folder": r"re:Natalie mars cuckolds the world \[album\] \(Tranny\.One\)",
                "referer": "re:https://pics.tranny.one/work/orig/2904/339248",
                "album_id": "2967",
            }
        ],
        17,
    ),
]
