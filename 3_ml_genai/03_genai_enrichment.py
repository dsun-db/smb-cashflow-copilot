# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Gen AI enrichment (job task 3, after the ML model scores `account_cashflow_health`)
# MAGIC * Embed every agent call note with `databricks-gte-large-en` -> synced to Lakebase -> pgvector semantic search
# MAGIC * Claude (`ai_query`) writes a grounded 2-sentence next-best-action briefing for every High-risk SMB

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_0dcqtv_catalog")
dbutils.widgets.text("schema", "smb_cashflow")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-5-5")
LLM = dbutils.widgets.get("llm_endpoint")
spark.sql(f"USE {dbutils.widgets.get('catalog')}.{dbutils.widgets.get('schema')}")


def add_pk(table, col):
    """NOT NULL + informational PK (required for Lakebase synced tables)."""
    spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL")
    try:
        spark.sql(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY ({col})")
    except Exception as e:
        print(f"{table}: PK exists ({str(e)[:40]})")

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE account_notes_embedded
COMMENT 'Agent call notes + 1024-d gte-large-en embeddings (ai_query). Synced to Lakebase; queried with pgvector.'
TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
SELECT note_id, account_id, agent_id, created_date, note_text,
       ai_query('databricks-gte-large-en', note_text) AS embedding
FROM silver_account_notes""")
add_pk("account_notes_embedded", "note_id")
display(spark.sql("SELECT count(*) notes, min(size(embedding)) dim FROM account_notes_embedded"))

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE copilot_briefings
COMMENT 'Claude-generated next-best-action briefing for each High-risk SMB (batch ai_query, grounded only in gold facts)'
TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
SELECT account_id, business_name, agent_id, risk_tier, shortfall_prob,
       ai_query('{LLM}',
         concat('You are a cash-flow copilot for a small-business Customer Success Agent. Using ONLY these facts, ',
                'write a 2-sentence briefing (max 70 words): the cash risk in plain words, then the single best next action. Facts: ',
                'business=', business_name, '; industry=', industry, '; bank balance=$', format_number(current_balance,0),
                '; overdue receivables=$', format_number(overdue_ar,0), ' across ', overdue_ar_count, ' invoices',
                '; bills due in 30 days=$', format_number(ap_due_30,0), '; net monthly cash flow=$', format_number(net_monthly,0),
                '; runway days=', runway_days, '; ML 60-day shortfall probability=', round(shortfall_prob*100), '%',
                '; primary driver=', primary_driver),
         modelParameters => named_struct('max_tokens', 1000)) AS briefing,
       current_timestamp() AS generated_at
FROM account_cashflow_health WHERE risk_tier = 'High'""")
add_pk("copilot_briefings", "account_id")
for r in spark.sql("""SELECT account_id, business_name, briefing FROM copilot_briefings
                      ORDER BY account_id = 'SMB-0112' DESC, shortfall_prob DESC LIMIT 4""").collect():
    print(f"[{r.account_id}] {r.business_name}\n  {r.briefing}\n")
print("briefings:", spark.table("copilot_briefings").count())
