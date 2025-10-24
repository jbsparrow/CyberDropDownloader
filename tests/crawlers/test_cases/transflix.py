DOMAIN = "transflix"
TEST_CASES = [
    (
        "https://transflix.net/video/avery-lust-chanel-chance-48259",
        [
            {
                "url": "https://cdn.transflix.net/video/2025-10-20/1760979682.mp4",
                "filename": "Avery Lust Chanel Chance [48259].mp4",
                "referer": "https://transflix.net/video/avery-lust-chanel-chance-48259",
                "datetime": 1760979682,
            }
        ],
    ),
    (
        "https://transflix.net/search?q=ruby+wren",
        [],
        4,
    ),
    # Timestamp mixed with leading letters
    (
        "https://transflix.net/video/hunnypaint-take-care-tranny-videos-xxx-43343",
        [
            {
                "url": "https://cdn.transflix.net/video/2025-03-28/qa2cxgri1743182001.mp4",
                "filename": "Hunnypaint - Take Care - Tranny Videos Xxx [43343].mp4",
                "referer": "https://transflix.net/video/hunnypaint-take-care-tranny-videos-xxx-43343",
                "datetime": 1743182001,
            }
        ],
    ),
]
