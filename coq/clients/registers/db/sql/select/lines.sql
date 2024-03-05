SELECT
  register,
  word,
  line AS text
FROM lines
WHERE
  (
    :word <> ''
    AND
    lword LIKE :like_word ESCAPE '!'
    AND
    LENGTH(word) + :look_ahead >= LENGTH(:word)
    AND
    X_SIMILARITY(LOWER(:word), lword, :look_ahead) > :cut_off
  )
  OR
  (
    :sym <> ''
    AND
    lword LIKE :like_sym ESCAPE '!'
    AND
    LENGTH(word) + :look_ahead >= LENGTH(:sym)
    AND
    X_SIMILARITY(LOWER(:sym), lword, :look_ahead) > :cut_off
  )
LIMIT :limit
