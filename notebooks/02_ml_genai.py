# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Make it intelligent: cash-shortfall ML model + Gen AI enrichment
# MAGIC Runs as task 2 of the `smb-cashflow-copilot` job, right after the Lakeflow ingest pipeline.
# MAGIC 1. **ML** - train a gradient-boosted classifier that predicts *P(cash shortfall in next 60 days)* from the gold
# MAGIC    feature table, track it in MLflow, register it in Unity Catalog with alias `champion`.
# MAGIC 2. **Score** every SMB -> `account_cashflow_health` (the serving table that is synced to Lakebase).
# MAGIC 3. **Gen AI** - embed agent call notes (`databricks-gte-large-en`) for semantic search in Lakebase (pgvector) and
# MAGIC    generate a "next best action" briefing for every High-risk SMB with Claude via `ai_query`.

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.16" scikit-learn
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_0dcqtv_catalog")
dbutils.widgets.text("schema", "smb_cashflow")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-5-5")
CAT, SCH = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
LLM = dbutils.widgets.get("llm_endpoint")
FQ = f"{CAT}.{SCH}"
spark.sql(f"USE {FQ}")
print("target schema:", FQ, "| llm:", LLM)

# COMMAND ----------

# MAGIC %md ## 1. Training set = gold features joined to historical outcomes

# COMMAND ----------

FEATURES = ["current_balance", "overdue_ar", "overdue_ar_count", "open_ar", "max_days_overdue",
            "ap_due_30", "overdue_bills", "monthly_inflow", "monthly_outflow", "net_monthly",
            "runway_days", "tenure_days"]
df = spark.sql(f"""
  SELECT f.account_id, {', '.join('f.' + c for c in FEATURES)}, o.cash_shortfall_60d AS label
  FROM gold_account_features f JOIN silver_account_outcomes o USING (account_id)""").toPandas()
df[FEATURES] = df[FEATURES].astype(float)
print(df.shape, "| positive rate:", round(df.label.mean(), 3))
df.describe().T[["mean", "min", "max"]].round(1)

# COMMAND ----------

import mlflow
import numpy as np
from mlflow.models import infer_signature
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from sklearn.model_selection import train_test_split

mlflow.set_registry_uri("databricks-uc")
user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/smb_cashflow_shortfall_model")
MODEL_NAME = f"{FQ}.cash_shortfall_model"

X, y = df[FEATURES], df["label"]
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
params = dict(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.9, random_state=42)

with mlflow.start_run(run_name="gbt_cash_shortfall") as run:
    model = GradientBoostingClassifier(**params).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    # baseline = the old rule (runway < 45 days) that agents use today
    rule = (Xte["runway_days"] < 45).astype(int)
    metrics = {"test_auc": roc_auc_score(yte, p), "test_avg_precision": average_precision_score(yte, p),
               "baseline_rule_auc": roc_auc_score(yte, rule)}
    mlflow.log_params(params)
    mlflow.log_metrics(metrics)
    mlflow.sklearn.log_model(model, name="model", registered_model_name=MODEL_NAME,
                             pyfunc_predict_fn="predict_proba",
                             signature=infer_signature(Xtr, model.predict_proba(Xtr)),
                             input_example=Xtr.head(3))
    print("run_id:", run.info.run_id)
    print({k: round(v, 4) for k, v in metrics.items()})
    print(classification_report(yte, (p >= 0.5).astype(int), digits=3))

# COMMAND ----------

from mlflow import MlflowClient
client = MlflowClient()
latest = max(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda v: int(v.version))
client.set_registered_model_alias(MODEL_NAME, "champion", latest.version)
print(f"registered {MODEL_NAME} v{latest.version} -> alias @champion")
imp = sorted(zip(FEATURES, model.feature_importances_), key=lambda t: -t[1])
for f, w in imp:
    print(f"{f:<18} {w:.3f}")

# COMMAND ----------

# MAGIC %md ## 2. Score every SMB with the `@champion` model -> `account_cashflow_health`

# COMMAND ----------

import pandas as pd
champion = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
gold = spark.table("gold_account_features").toPandas()
gold[FEATURES] = gold[FEATURES].astype(float)
gold["shortfall_prob"] = np.round(np.asarray(champion.predict(gold[FEATURES]))[:, 1], 4)  # P(class=1)


def tier(r):
    if r.shortfall_prob >= 0.55 or r.runway_days < 30:
        return "High"
    if r.shortfall_prob >= 0.25 or r.rule_risk_tier != "Healthy":
        return "Watch"
    return "Healthy"


def driver(r):
    if r.overdue_ar > max(r.current_balance, 0) and r.overdue_ar > 0:
        return "Overdue receivables exceed cash on hand"
    if r.net_monthly < 0:
        return "Negative monthly cash flow"
    if r.ap_due_30 > max(r.current_balance, 0):
        return "Bills due in 30 days exceed cash"
    return "Stable"


gold["risk_tier"] = gold.apply(tier, axis=1)
gold["primary_driver"] = gold.apply(driver, axis=1)
gold["model_version"] = int(latest.version)
gold["scored_at"] = pd.Timestamp.utcnow().tz_localize(None)

(spark.createDataFrame(gold).write.mode("overwrite").option("overwriteSchema", "true")
      .saveAsTable("account_cashflow_health"))
spark.sql("ALTER TABLE account_cashflow_health ALTER COLUMN account_id SET NOT NULL")
spark.sql("""ALTER TABLE account_cashflow_health SET TBLPROPERTIES (delta.enableChangeDataFeed = true)""")
try:
    spark.sql("ALTER TABLE account_cashflow_health ADD CONSTRAINT pk_health PRIMARY KEY (account_id)")
except Exception as e:
    print("PK exists:", str(e)[:80])
spark.sql("""COMMENT ON TABLE account_cashflow_health IS
  'Serving table: gold features + ML shortfall probability (cash_shortfall_model@champion), final risk tier and primary driver. Synced to Lakebase for the app.'""")
display(spark.sql("""SELECT risk_tier, count(*) accounts, round(avg(shortfall_prob),3) avg_prob,
                            round(sum(overdue_ar)) overdue_ar FROM account_cashflow_health GROUP BY 1 ORDER BY 1"""))

# COMMAND ----------

display(spark.sql("""SELECT account_id, business_name, agent_name, current_balance, overdue_ar, runway_days,
                            rule_risk_tier, shortfall_prob, risk_tier, primary_driver
                     FROM account_cashflow_health WHERE account_id = 'SMB-0112'"""))

# COMMAND ----------

# MAGIC %md ## 3. Gen AI: embed agent notes (semantic search) + Claude next-best-action briefings

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE account_notes_embedded
COMMENT 'Agent call notes + 1024-d gte-large-en embeddings (ai_query). Synced to Lakebase; queried with pgvector.'
TBLPROPERTIES (delta.enableChangeDataFeed = true) AS
SELECT note_id, account_id, agent_id, created_date, note_text,
       ai_query('databricks-gte-large-en', note_text) AS embedding
FROM silver_account_notes""")
spark.sql("ALTER TABLE account_notes_embedded ALTER COLUMN note_id SET NOT NULL")
try:
    spark.sql("ALTER TABLE account_notes_embedded ADD CONSTRAINT pk_notes PRIMARY KEY (note_id)")
except Exception as e:
    print("PK exists:", str(e)[:80])
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
spark.sql("ALTER TABLE copilot_briefings ALTER COLUMN account_id SET NOT NULL")
try:
    spark.sql("ALTER TABLE copilot_briefings ADD CONSTRAINT pk_brief PRIMARY KEY (account_id)")
except Exception as e:
    print("PK exists:", str(e)[:80])
for r in spark.sql("""SELECT account_id, business_name, briefing FROM copilot_briefings
                      ORDER BY account_id = 'SMB-0112' DESC, shortfall_prob DESC LIMIT 4""").collect():
    print(f"[{r.account_id}] {r.business_name}\n  {r.briefing}\n")
print("briefings:", spark.table("copilot_briefings").count())
