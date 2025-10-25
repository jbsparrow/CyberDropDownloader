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
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
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
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
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
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
            },
        ],
    ),
    (
        "https://www.imagebam.com/gallery/hfqrglgtcf4u143xlnvkpfksofn1et7w",
        [
            {
                "url": "https://images3.imagebam.com/68/8f/e5/84105c342494938.jpg",
                "filename": "main_large.jpg",
                "original_filename": "84105c342494938.jpg",
                "referer": "https://www.imagebam.com/image/84105c342494938",
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
            },
            {
                "url": "https://images3.imagebam.com/eb/21/02/9b65e0342494935.JPG",
                "filename": "0_1456043.jpg",
                "original_filename": "9b65e0342494935.JPG",
                "referer": "https://www.imagebam.com/image/9b65e0342494935",
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
            },
            {
                "url": "https://images3.imagebam.com/5a/bd/a1/764c40342494934.JPG",
                "filename": "0_1456042.jpg",
                "original_filename": "764c40342494934.JPG",
                "referer": "https://www.imagebam.com/image/764c40342494934",
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
            },
            {
                "url": "https://images3.imagebam.com/c0/12/7d/889be4342494931.JPG",
                "filename": "0_1456039.jpg",
                "original_filename": "889be4342494931.JPG",
                "referer": "https://www.imagebam.com/image/889be4342494931",
                "album_id": "hfqrglgtcf4u143xlnvkpfksofn1et7w",
            },
        ],
    ),
    (
        "https://www.imagebam.com/view/ME5IIKF",
        [
            {
                "url": "https://images4.imagebam.com/d0/99/a7/ME5IIKF_o.png",
                "filename": "Logic.png",
                "original_filename": "ME5IIKF_o.png",
                "referer": "https://www.imagebam.com/view/ME5IIKF",
                "album_id": "GA2LOS",
            },
        ],
    ),
    (
        "https://www.imagebam.com/view/GA2LOS",
        [
            {
                "url": "https://images4.imagebam.com/4b/b6/4a/ME5IIKH_o.png",
                "filename": "Pads Logic.png",
                "original_filename": "ME5IIKH_o.png",
                "referer": "https://www.imagebam.com/view/ME5IIKH",
                "album_id": "GA2LOS",
            },
        ],
        4,
    ),
    (
        "https://thumbs4.imagebam.com/e5/ab/48/ME5IIKD_t.png",
        [
            {
                "url": "https://images4.imagebam.com/e5/ab/48/ME5IIKD_o.png",
                "referer": "https://www.imagebam.com/view/ME5IIKD",
            },
        ],
    ),
    (
        "https://images4.imagebam.com/e5/ab/48/ME5IIKD_o.png",
        [
            {
                "url": "https://images4.imagebam.com/e5/ab/48/ME5IIKD_o.png",
                "referer": "https://www.imagebam.com/view/ME5IIKD",
            },
        ],
    ),
]
