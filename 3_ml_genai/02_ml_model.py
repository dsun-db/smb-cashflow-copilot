# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - ML: cash-shortfall model (job task 2, after the Lakeflow pipeline)
# MAGIC 1. **ML**: GBT classifier for *P(cash shortfall in 60 days)* -> MLflow -> UC registry `@champion` -> serving endpoint
# MAGIC 2. **Score** every SMB -> `account_cashflow_health` (synced to Lakebase)
# MAGIC 3. Gen AI enrichment runs next in `03_genai_enrichment`

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

FEATURES = ["current_balance", "overdue_ar", "overdue_ar_count", "open_ar", "max_days_overdue", "ap_due_30",
            "overdue_bills", "monthly_inflow", "monthly_outflow", "net_monthly", "runway_days", "tenure_days"]
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

# Serve the champion: roll the real-time endpoint (used by the app's what-if) to the new version
from databricks.sdk import WorkspaceClient
ws = WorkspaceClient()
EP = "smb-cashflow-shortfall"
cfg = {"served_entities": [{"name": "champion", "entity_name": MODEL_NAME, "entity_version": str(latest.version),
                            "workload_size": "Small", "scale_to_zero_enabled": True}]}
try:  # non-blocking; endpoint created once with AI Gateway inference tables
    ws.api_client.do("PUT", f"/api/2.0/serving-endpoints/{EP}/config", body=cfg)
    print(f"endpoint {EP}: rolling to v{latest.version}")
except Exception as e:
    print(f"endpoint {EP}: rollout skipped ({str(e)[:120]})")

# COMMAND ----------

# MAGIC %md ## 2. Score every SMB with the `@champion` model -> `account_cashflow_health`

# COMMAND ----------

import pandas as pd


def add_pk(table, col):
    """NOT NULL + informational PK (required for Lakebase synced tables)."""
    spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL")
    try:
        spark.sql(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY ({col})")
    except Exception as e:
        print(f"{table}: PK exists ({str(e)[:40]})")


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
add_pk("account_cashflow_health", "account_id")
spark.sql("ALTER TABLE account_cashflow_health SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
spark.sql("""COMMENT ON TABLE account_cashflow_health IS
  'Serving table: gold features + ML shortfall_prob (@champion) + risk tier/driver. Synced to Lakebase.'""")
display(spark.sql("""SELECT risk_tier, count(*) accounts, round(avg(shortfall_prob),3) avg_prob,
                            round(sum(overdue_ar)) overdue_ar FROM account_cashflow_health GROUP BY 1 ORDER BY 1"""))

# COMMAND ----------

display(spark.sql("""SELECT account_id, business_name, agent_name, current_balance, overdue_ar, runway_days,
                            rule_risk_tier, shortfall_prob, risk_tier, primary_driver
                     FROM account_cashflow_health WHERE account_id = 'SMB-0112'"""))
