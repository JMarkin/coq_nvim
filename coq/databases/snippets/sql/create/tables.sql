BEGIN;


CREATE TABLE IF NOT EXISTS sources (
  rowid    BLOB NOT NULL PRIMARY KEY,
  filename TEXT NOT NULL UNIQUE,
  mtime    REAL NOT NULL
) WITHOUT rowid;
CREATE INDEX IF NOT EXISTS sources_filename ON sources (filename);


CREATE TABLE IF NOT EXISTS filetypes (
  filetype TEXT NOT NULL PRIMARY KEY
) WITHOUT ROWID;


CREATE TABLE IF NOT EXISTS extensions (
  source_id BLOB NOT NULL REFERENCES sources   (rowid)    ON UPDATE CASCADE ON DELETE CASCADE,
  src       TEXT NOT NULL REFERENCES filetypes (filetype) ON UPDATE CASCADE ON DELETE CASCADE,
  dest      TEXT NOT NULL REFERENCES filetypes (filetype) ON UPDATE CASCADE ON DELETE CASCADE,
  UNIQUE (source_id, src, dest)
);
CREATE INDEX IF NOT EXISTS extensions_source_id ON extensions (source_id);
CREATE INDEX IF NOT EXISTS extensions_src       ON extensions (src);
CREATE INDEX IF NOT EXISTS extensions_dest      ON extensions (dest);
CREATE INDEX IF NOT EXISTS extensions_src_dest  ON extensions (src, dest);
CREATE INDEX IF NOT EXISTS extensions_dest_src  ON extensions (dest, src);


CREATE TABLE IF NOT EXISTS snippets (
  rowid     BLOB NOT NULL PRIMARY KEY,
  source_id BLOB NOT NULL REFERENCES sources   (rowid)    ON UPDATE CASCADE ON DELETE CASCADE,
  filetype  TEXT NOT NULL REFERENCES filetypes (filetype) ON UPDATE CASCADE ON DELETE CASCADE,
  grammar   TEXT NOT NULL,
  content   TEXT NOT NULL,
  label     TEXT NOT NULL,
  doc       TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS snippets_source_id ON snippets (source_id);
CREATE INDEX IF NOT EXISTS snippets_filetype  ON snippets (filetype);


CREATE TABLE IF NOT EXISTS matches (
  snippet_id BLOB NOT NULL REFERENCES snippets (rowid) ON UPDATE CASCADE ON DELETE CASCADE,
  word       TEXT NOT NULL,
  lword      TEXT NOT NULL,
  UNIQUE(snippet_id, word)
);
CREATE INDEX IF NOT EXISTS matches_snippet_id ON matches (snippet_id);
CREATE INDEX IF NOT EXISTS matches_word       ON matches (word);
CREATE INDEX IF NOT EXISTS matches_lword      ON matches (lword);


CREATE VIEW IF NOT EXISTS uniq_extensions_view AS
SELECT DISTINCT
  src,
  dest
FROM extensions
WHERE 
  src <> dest;


CREATE VIEW IF NOT EXISTS extensions_view AS
WITH RECURSIVE all_exts AS (
  SELECT
    1 AS lvl,
    e1.src,
    e1.dest
  FROM uniq_extensions_view AS e1
  UNION ALL
  SELECT
    all_exts.lvl + 1 AS lvl,
    all_exts.src,
    e2.dest
  FROM uniq_extensions_view AS e2
  JOIN all_exts
  ON
    all_exts.dest = e2.src
)
SELECT
  filetypes.filetype AS src,
  filetypes.filetype AS dest
FROM filetypes
UNION ALL
SELECT
  all_exts.src,
  all_exts.dest
FROM all_exts
WHERE
  lvl < 9;


CREATE VIEW IF NOT EXISTS snippets_view AS
SELECT
  snippets.rowid       AS snippet_id,
  snippets.source_id   AS source_id,
  snippets.grammar     AS grammar,
  matches.word         AS word,
  matches.lword        AS lword,
  snippets.content     AS snippet,
  snippets.label       AS label,
  snippets.doc         AS doc,
  extensions_view.src  AS ft_src,
  extensions_view.dest AS ft_dest
FROM snippets
JOIN matches
ON matches.snippet_id = snippets.rowid
JOIN extensions_view
ON
  snippets.filetype = extensions_view.dest
WHERE
  matches.word <> ''
  AND
  snippets.content <> '';


END;
