-- Lakebase (Postgres 17) setup for the SMB Cash-Flow Copilot. Run in database 'cashflow' after the UC synced tables exist.
-- Synced (read-only, managed by UC synced tables, schema smb_cashflow): lb_account_cashflow_health, lb_invoices, lb_bills,
--   lb_success_agents, lb_agent_portfolio, lb_account_notes_embedded, lb_copilot_briefings

-- 1) operational (writable) objects
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector for semantic search over agent notes

CREATE SCHEMA IF NOT EXISTS app;
-- Writable OLTP table: actions a Success Agent logs from the app (write-back path)
CREATE TABLE IF NOT EXISTS app.agent_actions (
  action_id    BIGSERIAL PRIMARY KEY,
  account_id   TEXT NOT NULL,
  agent_id     TEXT NOT NULL,
  action_type  TEXT NOT NULL CHECK (action_type IN
               ('send_ar_reminders','offer_payment_plan','offer_financing','schedule_bills','call_owner','other')),
  note         TEXT,
  created_by   TEXT DEFAULT current_user,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_actions_acct ON app.agent_actions(account_id, created_at DESC);

-- Copilot audit log (every question; PII-redacted; blocked flag) -> governance evidence
CREATE TABLE IF NOT EXISTS app.copilot_audit (
  id                BIGSERIAL PRIMARY KEY,
  account_id        TEXT,
  question_redacted TEXT,
  blocked           BOOLEAN,
  pii_entities      TEXT,
  model             TEXT,
  latency_ms        INT,
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- 2) native pgvector copy of synced jsonb embeddings + HNSW (refreshed by job task refresh_lakebase_vectors)
CREATE MATERIALIZED VIEW IF NOT EXISTS app.note_vectors AS
  SELECT note_id, account_id, note_text, (embedding::text)::vector(1024) AS emb
  FROM smb_cashflow.lb_account_notes_embedded;
CREATE UNIQUE INDEX IF NOT EXISTS uq_note_vectors ON app.note_vectors(note_id);
CREATE INDEX IF NOT EXISTS hnsw_note_vectors ON app.note_vectors USING hnsw (emb vector_cosine_ops);
REFRESH MATERIALIZED VIEW CONCURRENTLY app.note_vectors;

-- 3) least-privilege grants for the app service principal (role auto-created by the app's postgres resource)
GRANT USAGE ON SCHEMA smb_cashflow TO "<app-sp-client-id>";
GRANT SELECT ON ALL TABLES IN SCHEMA smb_cashflow TO "<app-sp-client-id>";
GRANT USAGE ON SCHEMA app TO "<app-sp-client-id>";
GRANT SELECT, INSERT ON app.agent_actions, app.copilot_audit TO "<app-sp-client-id>";
GRANT SELECT ON app.note_vectors TO "<app-sp-client-id>";
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO "<app-sp-client-id>";
