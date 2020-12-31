BEGIN;


CREATE TABLE sources (
  rowid    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  source   TEXT    NOT NULL UNIQUE
) WITHOUT ROWID;


CREATE TABLE filetypes (
  rowid    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  filetype TEXT    NOT NULL UNIQUE
) WITHOUT ROWID;


CREATE TABLE files (
  rowid       INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  filename    TEXT    NOT NULL UNIQUE,
  filetype_id INTEGER NOT NULL REFERENCES filetypes (rowid) ON DELETE CASCADE
) WITHOUT ROWID;


CREATE TABLE words (
  rowid     INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  word      TEXT    NOT NULL UNIQUE,
  nword     TEXT    NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources (rowid) ON DELETE CASCADE,
) WITHOUT ROWID;
CREATE INDEX words_nword ON words (nword);


CREATE TABLE word_locations (
  rowid   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  word_id INTEGER NOT NULL REFERENCES words (rowid) ON DELETE CASCADE,
  file_id INTEGER NOT NULL REFERENCES files (rowid) ON DELETE CASCADE,
  row     INTEGER NOT NULL
) WITHOUT ROWID;


CREATE VIEW word_sources_view AS
SELECT
  words.word,
  words.nword,
FROM words
JOIN sources
ON
  words.source_id = sources.rowid;


END;
