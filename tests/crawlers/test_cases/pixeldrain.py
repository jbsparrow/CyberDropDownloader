DOMAIN = "pixeldrain"
TEST_CASES = [
    (
        "https://pixeldrain.com/u/HjYNXA67",
        [
            {
                "url": "https://pixeldrain.com/api/file/HjYNXA67?download",
                "filename": "Cyberdrop-DL.v8.4.0.zip",
                "original_filename": "Cyberdrop-DL.v8.4.0.zip",
                "download_folder": r"re:Loose Files \(PixelDrain\)",
                "referer": "https://pixeldrain.com/u/HjYNXA67",
                "album_id": None,
                "datetime": 1761091325,
            },
        ],
    ),
    (
        "https://pd.1drv.eu.org/HjYNXA67",
        [
            {
                "url": "https://pixeldrain.com/api/file/HjYNXA67?download",
                "filename": "Cyberdrop-DL.v8.4.0.zip",
                "original_filename": "Cyberdrop-DL.v8.4.0.zip",
                "download_folder": r"re:Loose Files \(PixelDrain\)",
                "referer": "https://pixeldrain.com/u/HjYNXA67",
                "album_id": None,
                "datetime": 1761091325,
                "debrid_link": "ANY",
            },
        ],
    ),
    (
        # text file with links
        "https://pixeldrain.com/u/b7V1Gjk4",
        [
            {
                "url": "https://pixeldrain.com/api/file/Hs5zFGYB?download",
                "filename": "test_file.png",
                "download_folder": r"re:links \(PixelDrain\)/Loose Files",
                "referer": "https://pixeldrain.com/u/Hs5zFGYB",
                "album_id": None,
            },
            {
                "url": "https://pixeldrain.com/api/file/HjYNXA67?download",
                "filename": "Cyberdrop-DL.v8.4.0.zip",
                "download_folder": r"re:links \(PixelDrain\)/Loose Files",
                "referer": "https://pixeldrain.com/u/HjYNXA67",
                "album_id": None,
            },
        ],
    ),
]
