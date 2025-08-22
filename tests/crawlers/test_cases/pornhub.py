DOMAIN = "pornhub"
TEST_CASES = [
    (
        "https://www.pornhub.com/album/36252941",
        [
            {
                "url": "re:ei.phncdn.com/pics/albums/036/252/941/453277801",
                "filename": "453277801.jpg",
                "original_filename": "original_453277801.jpg",
                "referer": "https://www.pornhub.com/photo/453277801",
                "album_id": "36252941",
                "download_folder": r"re:White Top White Striped Calvins \(PornHub\)",
                "datetime": None,
            }
        ],
        8,
    ),
    (
        # mp4 available
        "https://www.pornhub.com/view_video.php?viewkey=ph5d530fd885a81",
        [
            {
                "url": "https://www.pornhub.com/embed/ph5d530fd885a81",
                "filename": "masturbating with my tail butt plug in - Ally Blake [ph5d530fd885a81][1080p].mp4",
                "original_filename": "ph5d530fd885a81.mp4",
                "referer": "https://www.pornhub.com/view_video.php?viewkey=ph5d530fd885a81",
                "album_id": None,
                "datetime": 1565724764,
            }
        ],
    ),
    (
        # m3u8 download
        "https://www.pornhub.com/embed/6890ddc0b4b11",
        [
            {
                "url": "https://www.pornhub.com/embed/6890ddc0b4b11",
                "filename": "MILF Celebrates Victory in Public Parking Ramp by Flashing Her Titti [6890ddc0b4b11][1080p].mp4",
                "original_filename": "6890ddc0b4b11.mp4",
                "referer": "https://www.pornhub.com/view_video.php?viewkey=6890ddc0b4b11",
                "album_id": None,
                "datetime": 1754324606,
            }
        ],
    ),
]
