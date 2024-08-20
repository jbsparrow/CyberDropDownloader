create_history = """CREATE TABLE IF NOT EXISTS media (domain TEXT,
                                               url_path TEXT,
                                               referer TEXT,
                                               album_id TEXT,
                                               download_path TEXT,
                                               download_filename TEXT,
                                               original_filename TEXT,
                                               completed INTEGER NOT NULL,
                                               created_at TIMESTAMP,
                                               completed_at TIMESTAMP,
                                               PRIMARY KEY (domain, url_path, original_filename)
                                               );"""

create_fixed_history = """CREATE TABLE IF NOT EXISTS media_copy (domain TEXT,
                                               url_path TEXT,
                                               referer TEXT,
                                               album_id TEXT,
                                               download_path TEXT,
                                               download_filename TEXT,
                                               original_filename TEXT,
                                               file_size INT,
                                               completed INTEGER NOT NULL,
                                               PRIMARY KEY (domain, url_path, original_filename)
                                               );"""

create_temp = """CREATE TABLE IF NOT EXISTS temp (downloaded_filename TEXT);"""

create_hash = """
CREATE TABLE IF NOT EXISTS hash (
  folder TEXT,
  download_filename TEXT,
  original_filename TEXT,
  file_size INT,
  hash TEXT,
  UNIQUE (folder, original_filename)
  PRIMARY KEY (folder, original_filename,hash)
);
"""
