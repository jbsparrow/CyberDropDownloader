DOMAIN = "transflix"
TEST_CASES = [
    # No resolution in title
    (
        "https://transflix.net/video/avery-lust-chanel-chance-48259",
        [
            {
                "url": "https://cdn.transflix.net/video/2025-10-20/1760979682.mp4",
                "filename": "Avery Lust Chanel Chance [48259].mp4",
                "referer": "https://transflix.net/video/avery-lust-chanel-chance-48259",
            }
        ],
    ),

    # resolution in title
    (
        "https://transflix.net/video/tmn-ruby-wren-pf-bhangs-1080-48256",
        [
            {
                "url": "https://cdn.transflix.net/video/2025-10-20/1760979418.mp4",
                "filename": "Tmn Ruby Wren Pf Bhangs (1080) [48256][1080p].mp4",
                "referer": "https://transflix.net/video/tmn-ruby-wren-pf-bhangs-1080-48256",
            }
        ],
    ),
]
