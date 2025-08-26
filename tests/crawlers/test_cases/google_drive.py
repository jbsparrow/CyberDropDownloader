DOMAIN = "drive.google"
TEST_CASES = [
    (
        # small file with no warning
        "https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6/edit",
        [
            {
                "url": "ANY",
                "filename": "file-50MB.dat",
                "referer": "https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # small file with no warning
        "https://drive.google.com/file/d/15WghIO0iwekXStmVWeK5HxC566iN41l6/view",
        [
            {
                "url": "ANY",
                "filename": "file-100MB.dat",
                "referer": "https://drive.google.com/file/d/15WghIO0iwekXStmVWeK5HxC566iN41l6",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # file with warning do to large size (529M)
        "https://drive.usercontent.google.com/download?id=1fXgBupLzThTGLLsiYCHRQJixuDsR1bSI&export=download",
        [
            {
                "url": "ANY",
                "filename": "cifar10_stats.npz",
                "referer": "https://drive.google.com/file/d/1fXgBupLzThTGLLsiYCHRQJixuDsR1bSI",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # huge file with warning do to large size (9.8G)
        "https://drive.google.com/file/d/1WHv5Dm1GtrDZj-AxJZd3T-NMIBXty3eV/view",
        [
            {
                "url": "ANY",
                "filename": "bundle_cutouts_africa.zip",
                "referer": "https://drive.google.com/file/d/1WHv5Dm1GtrDZj-AxJZd3T-NMIBXty3eV",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://drive.google.com/file/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY/edit",
        [
            {
                "url": "ANY",
                "filename": "test.pdf",
                "referer": "https://drive.google.com/file/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=pdf",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=txt",
        [
            {
                "url": "ANY",
                "filename": "test.txt",
                "referer": "https://drive.google.com/file/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=txt",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY",
        [
            {
                "url": "ANY",
                "filename": "test.docx",
                "referer": "https://drive.google.com/file/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=docx",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=xlsx",
        [],
    ),
]
