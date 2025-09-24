DOMAIN = "thisvid"
TEST_CASES = [
    (
        "https://thisvid.com/videos/a-wedding-photo-to-remember/",
        [
            {
                "url": "https://thisvid.com/videos/a-wedding-photo-to-remember",
                "filename": "A wedding photo to remember [12797267].mp4",
                "referer": "https://thisvid.com/videos/a-wedding-photo-to-remember",
                "album_id": None,
                "datetime": 1753326000,
            }
        ],
    ),
    (
        "https://thisvid.com/albums/bruxel/",
        [
            {
                "url": "re:https://media.thisvid.com/contents/albums/main/700x525/517000/51739",
                "download_folder": r"re:Julia Bruxel \[album\] \(ThisVid\)",
                "referer": "re:https://thisvid.com/albums/bruxel",
                "album_id": "517393",
            },
        ],
        10,
    ),
]
