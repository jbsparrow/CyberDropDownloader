DOMAIN = "imagetwist.com"
TEST_CASES = [
    (
        "https://imagetwist.com/uynrhb4lavce/Latoya14.jpg",
        [
            {
                "url": "https://img115.imagetwist.com/i/20566/uynrhb4lavce.jpg/Latoya14.jpg",
                "filename": "Latoya14.jpg",
                "referer": "https://imagetwist.com/uynrhb4lavce",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://img115.imagetwist.com/i/20566/uynrhb4lavce.jpg/Latoya14.jpg",
        [
            {
                "url": "https://img115.imagetwist.com/i/20566/uynrhb4lavce.jpg/Latoya14.jpg",
                "filename": "Latoya14.jpg",
                "referer": "https://imagetwist.com/uynrhb4lavce",
            }
        ],
    ),
    (
        "https://img115.imagetwist.com/th/20566/uynrhb4lavce.jpg",
        [
            {
                "url": "https://img115.imagetwist.com/i/20566/uynrhb4lavce.jpg/Latoya14.jpg",
                "filename": "Latoya14.jpg",
                "referer": "https://imagetwist.com/uynrhb4lavce",
            }
        ],
    ),
]
