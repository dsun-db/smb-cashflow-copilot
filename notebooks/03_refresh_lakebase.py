# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Lakebase: refresh pgvector index + verify operational serving
# MAGIC Final task of the `smb-cashflow-copilot` job (after the UC -> Lakebase synced tables refresh).
# MAGIC Rebuilds `app.note_vectors` (native `vector(1024)` + HNSW) from the synced embeddings, then
# MAGIC checks the serving tables the app reads and times a point lookup + a semantic search.

# COMMAND ----------

# MAGIC %pip install -q psycopg2-binary
# MAGIC %restart_python

# COMMAND ----------

import time, psycopg2
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ENDPOINT = "projects/smb-cashflow/branches/production/endpoints/primary"
ep = w.api_client.do("GET", f"/api/2.0/postgres/{ENDPOINT}")
host = ep["status"]["hosts"]["host"]
token = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={"endpoint": ENDPOINT})["token"]
user = w.current_user.me().user_name
conn = psycopg2.connect(host=host, dbname="cashflow", user=user, password=token, sslmode="require")
conn.autocommit = True
cur = conn.cursor()
print("connected to Lakebase", host.split(".")[0], "as", user)

# COMMAND ----------

t = time.time()
cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY app.note_vectors")
print(f"refreshed app.note_vectors in {time.time() - t:.1f}s")
for tbl in ["smb_cashflow.lb_account_cashflow_health", "smb_cashflow.lb_invoices", "smb_cashflow.lb_bills",
            "smb_cashflow.lb_success_agents", "smb_cashflow.lb_agent_portfolio", "smb_cashflow.lb_copilot_briefings",
            "smb_cashflow.lb_account_notes_embedded", "app.note_vectors", "app.agent_actions", "app.copilot_audit"]:
    cur.execute(f"SELECT count(*) FROM {tbl}")
    print(f"{tbl:<42} {cur.fetchone()[0]:>7} rows")

# COMMAND ----------

t = time.time()
cur.execute("""SELECT account_id, business_name, current_balance, overdue_ar, runway_days, shortfall_prob, risk_tier
               FROM smb_cashflow.lb_account_cashflow_health WHERE account_id = 'SMB-0112'""")
row = cur.fetchone()
print(f"point lookup {1000 * (time.time() - t):.1f} ms ->", row)

cur.execute("SELECT emb FROM app.note_vectors WHERE account_id = 'SMB-0112' LIMIT 1")
q = cur.fetchone()[0]
t = time.time()
cur.execute("""SELECT account_id, left(note_text, 70), round((emb <=> %s::vector)::numeric, 3)
               FROM app.note_vectors WHERE account_id <> 'SMB-0112' ORDER BY emb <=> %s::vector LIMIT 3""", (q, q))
res = cur.fetchall()
print(f"pgvector HNSW top-3 search {1000 * (time.time() - t):.1f} ms")
for r in res:
    print("  ", r)
conn.close()
