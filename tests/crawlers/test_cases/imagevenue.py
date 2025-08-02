DOMAIN = "www.imagevenue.com"
TEST_CASES = [
    (
        "https://www.imagevenue.com/ME1BEWWG",
        [
            {
                "url": "https://cdn-images.imagevenue.com/65/8b/4d/ME1BEWWG_o.jpg",
                "filename": "001.jpg",
                "original_filename": "ME1BEWWG_o.jpg",
                "referer": "https://www.imagevenue.com/ME1BEWWG",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://cdn-thumbs.imagevenue.com/d2/90/5c/ME1BEWWG_t.jpg",
        [
            {
                "url": "https://cdn-images.imagevenue.com/65/8b/4d/ME1BEWWG_o.jpg",
                "referer": "https://www.imagevenue.com/ME1BEWWG",
            }
        ],
    ),
    (
        "https://www.imagevenue.com/ME1BEWWG",
        [
            {
                "url": "https://cdn-images.imagevenue.com/65/8b/4d/ME1BEWWG_o.jpg",
                "filename": "001.jpg",
                "original_filename": "ME1BEWWG_o.jpg",
                "referer": "https://www.imagevenue.com/ME1BEWWG",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
]
