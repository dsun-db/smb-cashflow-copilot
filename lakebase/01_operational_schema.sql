-- Lakebase (Postgres) operational objects that are NOT synced from the lakehouse.
-- Synced (read-only, managed by UC synced tables) live in schema smb_cashflow:
--   lb_account_cashflow_health, lb_invoices, lb_bills, lb_success_agents,
--   lb_agent_portfolio, lb_account_notes_embedded, lb_copilot_briefings
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
