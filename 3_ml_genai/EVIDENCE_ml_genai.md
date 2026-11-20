# ML + Gen AI evidence (captured 2026-11-20T16:57:51Z) - notebook cell outputs exported from job run 239048784653883

## `02_ml_model.py` (task `ml_model`, task run 648147192348280, SUCCESS)
**cell:** `dbutils.widgets.text("catalog", "serverless_stable_0dcqtv_catalog")`
```
target schema: serverless_stable_0dcqtv_catalog.smb_cashflow | llm: databricks-claude-sonnet-5-5
```
**cell:** `FEATURES = ["current_balance", "overdue_ar", "overdue_ar_count", "open_ar", "max_days_over`
```
(1500, 14) | positive rate: 0.231

                     mean      min       max
current_balance   79707.4  -5856.0  219989.0
overdue_ar        20154.8      0.0  148477.7
overdue_ar_count      2.5      0.0      16.0
open_ar           42076.0      0.0  135607.2
max_days_overdue     76.3      0.0     167.0
ap_due_30         17007.6      0.0   60776.2
overdue_bills         1.3      0.0       7.0
monthly_inflow    51948.6   7240.9  112138.0
monthly_outflow   41089.5   9050.2   88674.5
net_monthly       10859.1 -50804.0   70741.2
runway_days         294.5      0.0     365.0
tenure_days         918.2     63.0    1802.0
label                 0.2      0.0       1.0
```
**cell:** `mlflow.set_registry_uri("databricks-uc")`
```
🔗 View Logged Model at: https://<workspace-host>/ml/experiments/515311966395607/models/m-371057fe57824867a06a55824899c80c?o=<workspace-id>
Registered model 'serverless_stable_0dcqtv_catalog.smb_cashflow.cash_shortfall_model' already exists. Creating a new version of this model...

🔗 Created version '5' of model 'serverless_stable_0dcqtv_catalog.smb_cashflow.cash_shortfall_model': https://<workspace-host>/explore/data/models/serverless_stable_0dcqtv_catalog/smb_cashflow/cash_shortfall_model/version/5?o=<workspace-id>

run_id: 39c56292d65a4f9d9947b7dc8dd0df1e
{'test_auc': 0.7884, 'test_avg_precision': 0.6071, 'baseline_rule_auc': 0.6892}
              precision    recall  f1-score   support

           0      0.867     0.924     0.894       289
           1      0.672     0.523     0.588        86

    accuracy                          0.832       375
   macro avg      0.769     0.724     0.741       375
weighted avg      0.822     0.832     0.824       375
```
**cell:** `client = MlflowClient()`
```
registered serverless_stable_0dcqtv_catalog.smb_cashflow.cash_shortfall_model v5 -> alias @champion
current_balance    0.549
monthly_inflow     0.101
overdue_ar         0.072
net_monthly        0.051
tenure_days        0.049
open_ar            0.044
ap_due_30          0.041
monthly_outflow    0.036
max_days_overdue   0.030
overdue_ar_count   0.013
runway_days        0.009
overdue_bills      0.005
```
**cell:** `ws = WorkspaceClient()`
```
endpoint smb-cashflow-shortfall: rolling to v5
```
**cell:** `def add_pk(table, col):`
```
risk_tier | accounts | avg_prob | overdue_ar
Healthy | 963 | 0.061 | 7800179.0
High | 304 | 0.718 | 14895209.0
Watch | 233 | 0.276 | 7536841.0
```
**cell:** `display(spark.sql("""SELECT account_id, business_name, agent_name, current_balance, overdu`
```
account_id | business_name | agent_name | current_balance | overdue_ar | runway_days | rule_risk_tier | shortfall_prob | risk_tier | primary_driver
SMB-0112 | Granite Goods | Priya Nair | 21500.0 | 89040.0 | 39.0 | High | 0.7447 | High | Overdue receivables exceed cash on hand
```
## `03_genai_enrichment.py` (task `genai_enrichment`, task run 45693678363405, SUCCESS)
**cell:** `spark.sql("""`
```
notes | dim
3063 | 1024
```
**cell:** `spark.sql(f"""`
```
[SMB-0112] Granite Goods
  Granite Goods has about 39 days of cash left, burning $16,500 a month, and a 74% chance of a 60-day shortfall, mainly because $89,040 across 8 overdue invoices is more than the $21,500 in the bank. Next action: start collection calls today on the largest overdue invoices, and ask for payment dates before the $13,758 in bills come due.

[SMB-1092] Lantern Marketing
  Lantern Marketing has only about 7 days of cash ($4,025) against $16,046 in bills due within 30 days and a $16,584 monthly burn, so a 60-day shortfall is 97% likely, mainly because $70,607 sits unpaid across 11 overdue invoices. The best next action is to start collection calls today on the largest overdue invoices, since even partial payment would cover the upcoming bills.

[SMB-0182] Driftwood Partners
  Driftwood Partners has only $297 in the bank against $37,671 in bills due within 30 days, and with a $9,698 monthly cash burn, it has roughly one day of runway and a 97% chance of a 60-day shortfall. The best next action is to immediately call the customers behind the $68,427 in overdue invoices (8 in total), starting with the largest, and ask for payment this week.

[SMB-0434] Trailhead Manufacturing
  Trailhead Manufacturing has only about 10 days of runway: its $6,016 balance can't cover $8,803 in bills due within 30 days while it loses $18,802 a month, and the model puts the chance o
```
## Model in UC + real-time serving endpoint
```
model serverless_stable_0dcqtv_catalog.smb_cashflow.cash_shortfall_model aliases=[('champion', 5)] versions=[1, 2, 3, 4, 5]
endpoint smb-cashflow-shortfall state={'config_update': 'NOT_UPDATING', 'ready': 'READY'} served=[('cash_shortfall_model', '5')]
ai_gateway={"inference_table_config": {"catalog_name": "serverless_stable_0dcqtv_catalog", "enabled": true, "schema_name": "smb_cashflow", "table_name_prefix": "shortfall_endpoint"}, "usage_tracking_config": {"enabled": true}}
invocation (Granite Goods today vs. after collecting Stark Retail $42,550): {
  "predictions": [
    [
      0.25529938364662985,
      0.7447006163533701
    ],
    [
      0.9042919177886328,
      0.09570808221136716
    ]
  ]
}
```