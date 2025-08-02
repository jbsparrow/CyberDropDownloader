DOMAIN = "imagebam"
TEST_CASES = [
    (
        "https://www.imagebam.com/image/9b65e0342494935",
        [
            {
                "url": "https://images3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
                "filename": "0_1456043.jpg",
                "original_filename": "9b65e0342494935.JPG",
                "referer": "https://www.imagebam.com/image/9b65e0342494935",
                "album_id": None,
            },
        ],
    ),
    (
        "https://images3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
        [
            {
                "url": "https://images3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
                "filename": "0_1456043.jpg",
                "original_filename": "9b65e0342494935.JPG",
                "referer": "https://www.imagebam.com/image/9b65e0342494935",
                "album_id": None,
            },
        ],
    ),
    (
        "https://thumbs3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
        [
            {
                "url": "https://images3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
                "filename": "0_1456043.jpg",
                "original_filename": "9b65e0342494935.JPG",
                "referer": "https://www.imagebam.com/image/9b65e0342494935",
                "album_id": None,
            },
        ],
    ),
]
