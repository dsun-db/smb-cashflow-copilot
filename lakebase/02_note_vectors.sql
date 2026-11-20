-- Native pgvector copy of the synced (jsonb) embeddings, with an HNSW index for fast cosine search.
-- Re-run after each sync (job task `refresh_lakebase_vectors`).
CREATE MATERIALIZED VIEW IF NOT EXISTS app.note_vectors AS
  SELECT note_id, account_id, note_text, (embedding::text)::vector(1024) AS emb
  FROM smb_cashflow.lb_account_notes_embedded;
CREATE UNIQUE INDEX IF NOT EXISTS uq_note_vectors ON app.note_vectors(note_id);
CREATE INDEX IF NOT EXISTS hnsw_note_vectors ON app.note_vectors USING hnsw (emb vector_cosine_ops);
REFRESH MATERIALIZED VIEW CONCURRENTLY app.note_vectors;
