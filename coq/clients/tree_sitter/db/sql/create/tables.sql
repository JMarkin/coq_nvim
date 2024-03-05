BEGIN;


CREATE TABLE IF NOT EXISTS buffers (
  rowid    INTEGER NOT NULL PRIMARY KEY,
  filetype TEXT    NOT NULL,
  filename TEXT    NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS buffers_filetype ON buffers (filetype);


CREATE TABLE IF NOT EXISTS words (
  buffer_id INTEGER NOT NULL REFERENCES buffers (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
  word      TEXT    NOT NULL,
  lword     TEXT    NOT NULL,
  lo        INTEGER NOT NULL,
  hi        INTEGER NOT NULL,
  kind      TEXT    NOT NULL,
  pword     TEXT,
  pkind     TEXT,
  gpword    TEXT,
  gpkind    TEXT,
  UNIQUE (buffer_id, word)
);
CREATE INDEX IF NOT EXISTS words_buffer_id ON words (buffer_id);
CREATE INDEX IF NOT EXISTS words_word      ON words (word);
CREATE INDEX IF NOT EXISTS words_lword     ON words (lword);
CREATE INDEX IF NOT EXISTS words_buffer_lo ON words (buffer_id, lo);
CREATE INDEX IF NOT EXISTS words_buffer_hi ON words (buffer_id, hi);


CREATE VIEW IF NOT EXISTS words_view AS
SELECT
  buffers.filetype,
  buffers.filename,
  words.word,
  words.lword,
  words.lo + 1 AS lo,
  words.hi + 1 AS hi,
  words.kind,
  words.pword,
  words.pkind,
  words.gpword,
  words.gpkind
FROM buffers
JOIN words
ON
  words.buffer_id = buffers.rowid
GROUP BY
  words.word
HAVING
  words.word <> '';


END;
