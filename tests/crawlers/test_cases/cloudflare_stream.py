DOMAIN = "cloudflarestream"
TEST_CASES = [
    (
        # This video has subtitles
        "https://customer-eq7kiuol0tk9chox.cloudflarestream.com/embed/sdk-iframe-integration.fla9.latest.js?video=e7bd2dd67e0f8860b4ae81e33a966049",
        [
            {
                "url": "https://watch.cloudflarestream.com/e7bd2dd67e0f8860b4ae81e33a966049",
                "filename": "e7bd2dd67e0f8860b4ae81e33a966049 [e7bd2dd67e0f8860b4ae81e33a966049][avc1][mp4a][720p].mp4",
                "original_filename": "e7bd2dd67e0f8860b4ae81e33a966049.mp4",
                "referer": "https://watch.cloudflarestream.com/e7bd2dd67e0f8860b4ae81e33a966049",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://customer-u1hok16au7q8ozt4.cloudflarestream.com/1c0006dc4f4299fa33d0dfd161db1c35/watch",
        [
            {
                "url": "https://watch.cloudflarestream.com/1c0006dc4f4299fa33d0dfd161db1c35",
                "filename": "1c0006dc4f4299fa33d0dfd161db1c35 [1c0006dc4f4299fa33d0dfd161db1c35][avc1][mp4a][1080p].mp4",
                "original_filename": "1c0006dc4f4299fa33d0dfd161db1c35.mp4",
                "referer": "https://watch.cloudflarestream.com/1c0006dc4f4299fa33d0dfd161db1c35",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
]
