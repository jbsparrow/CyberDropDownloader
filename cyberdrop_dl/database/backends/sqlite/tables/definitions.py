create_history = """CREATE TABLE IF NOT EXISTS media (
  domain TEXT,
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

create_fixed_history = """CREATE TABLE IF NOT EXISTS media_copy (
  domain TEXT,
  url_path TEXT,
  referer TEXT,
  album_id TEXT,
  download_path TEXT,
  download_filename TEXT,
  original_filename TEXT,
  file_size INT,
  duration FLOAT,
  completed INTEGER NOT NULL,
  PRIMARY KEY (domain, url_path, original_filename)
);"""

create_temp_referer = """CREATE TABLE IF NOT EXISTS temp_referer (referer TEXT);"""

create_files = """
CREATE TABLE IF NOT EXISTS files (
  folder TEXT,
  download_filename TEXT,
  original_filename TEXT,
  file_size INT,
  referer TEXT,
  date INT,
  PRIMARY KEY (folder, download_filename)
);

"""

create_hash = """
CREATE TABLE IF NOT EXISTS hash (
  folder TEXT,
  download_filename TEXT,
  hash_type TEXT,
  hash TEXT,
  PRIMARY KEY (folder, download_filename, hash_type),
  FOREIGN KEY (folder, download_filename) REFERENCES files(folder, download_filename)
);

"""

create_temp_hash = """
CREATE TABLE IF NOT EXISTS temp_hash (
  folder TEXT,
  download_filename TEXT,
  hash_type TEXT,
  hash TEXT,
  PRIMARY KEY (folder, download_filename, hash_type),
  FOREIGN KEY (folder, download_filename) REFERENCES files(folder, download_filename)
);
"""
