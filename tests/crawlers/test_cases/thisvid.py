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
            }
        ],
    ),
    (
        # No resolution info in video page
        "https://thisvid.com/videos/smelling-foreskin/",
        [
            {
                "url": "https://thisvid.com/videos/smelling-foreskin",
                "filename": "Smelling foreskin [794368].mp4",
                "referer": "https://thisvid.com/videos/smelling-foreskin",
                "album_id": None,
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
