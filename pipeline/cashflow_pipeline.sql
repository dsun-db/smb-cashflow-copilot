-- =====================================================================================
-- SMB Cash-Flow Copilot :: Lakeflow Spark Declarative Pipeline (serverless)
-- raw CSV drops in a UC Volume --(Auto Loader)--> bronze --(expectations)--> silver --> gold
-- Config: raw_path = /Volumes/<catalog>/smb_cashflow/raw
-- =====================================================================================

-- ------------------------------------------------------------------ BRONZE (Auto Loader)
CREATE OR REFRESH STREAMING TABLE bronze_smb_accounts
COMMENT 'Raw SMB account master drops (Auto Loader, schema-on-read)'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/smb_accounts', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_success_agents
COMMENT 'Raw Customer Success Agent roster'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/success_agents', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_invoices
COMMENT 'Raw invoices (accounts receivable) issued by SMBs to their customers'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/invoices', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_bills
COMMENT 'Raw bills (accounts payable) owed by SMBs to vendors'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/bills', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_bank_transactions
COMMENT 'Raw bank-feed transactions connected to each SMB'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/bank_transactions', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_account_notes
COMMENT 'Raw free-text notes written by Success Agents after customer calls'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/account_notes', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_account_outcomes
COMMENT 'Historical labels: did the SMB hit a cash shortfall within 60 days of the snapshot'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/account_outcomes', format => 'csv', header => true);

-- ------------------------------------------------------------------ SILVER (typed + DQ)
CREATE OR REFRESH STREAMING TABLE silver_smb_accounts (
  account_id STRING COMMENT 'SMB account id (SMB-nnnn)',
  business_name STRING, industry STRING, region STRING, plan_tier STRING,
  agent_id STRING COMMENT 'Owning Customer Success Agent',
  signup_date DATE, revenue_band STRING,
  current_balance DOUBLE COMMENT 'Current connected bank balance (USD)',
  owner_email STRING MASK serverless_stable_0dcqtv_catalog.smb_cashflow.mask_pii COMMENT 'PII - masked',
  tax_id STRING MASK serverless_stable_0dcqtv_catalog.smb_cashflow.mask_pii COMMENT 'PII (EIN) - masked',
  _ingested_at TIMESTAMP,
  CONSTRAINT valid_account_id EXPECT (account_id RLIKE '^SMB-[0-9]{4}$') ON VIOLATION DROP ROW,
  CONSTRAINT has_agent EXPECT (agent_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT known_region EXPECT (region IN ('West', 'Midwest', 'Northeast', 'South'))
)
COMMENT 'Cleaned SMB account master. owner_email and tax_id carry UC column masks.'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT CAST(account_id AS STRING) account_id, business_name, industry, region, plan_tier, agent_id,
          CAST(signup_date AS DATE) signup_date, revenue_band, CAST(current_balance AS DOUBLE) current_balance,
          owner_email, CAST(tax_id AS STRING) tax_id, _ingested_at
FROM STREAM(bronze_smb_accounts);

CREATE OR REFRESH STREAMING TABLE silver_success_agents (
  CONSTRAINT has_id EXPECT (agent_id IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Customer Success Agent roster'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT agent_id, agent_name, region FROM STREAM(bronze_success_agents);

CREATE OR REFRESH STREAMING TABLE silver_invoices (
  CONSTRAINT positive_amount EXPECT (amount > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_status EXPECT (status IN ('open', 'paid', 'overdue')) ON VIOLATION DROP ROW,
  CONSTRAINT due_after_issue EXPECT (due_date >= issue_date)
)
COMMENT 'Typed invoices (AR). overdue = past due date and unpaid.'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT invoice_id, account_id, customer_name, CAST(amount AS DOUBLE) amount,
          CAST(issue_date AS DATE) issue_date, CAST(due_date AS DATE) due_date, status,
          CAST(paid_date AS DATE) paid_date, _source_file
FROM STREAM(bronze_invoices);

CREATE OR REFRESH STREAMING TABLE silver_bills (
  CONSTRAINT positive_amount EXPECT (amount > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_status EXPECT (status IN ('open', 'paid', 'overdue')) ON VIOLATION DROP ROW
)
COMMENT 'Typed bills (AP).'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT bill_id, account_id, vendor_name, CAST(amount AS DOUBLE) amount,
          CAST(issue_date AS DATE) issue_date, CAST(due_date AS DATE) due_date, status,
          CAST(paid_date AS DATE) paid_date
FROM STREAM(bronze_bills);

CREATE OR REFRESH STREAMING TABLE silver_bank_transactions (
  CONSTRAINT positive_amount EXPECT (amount > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_direction EXPECT (direction IN ('credit', 'debit')) ON VIOLATION DROP ROW
)
COMMENT 'Typed bank-feed transactions. credit = money in, debit = money out.'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT txn_id, account_id, CAST(txn_date AS DATE) txn_date, CAST(amount AS DOUBLE) amount,
          direction, category, description, _source_file
FROM STREAM(bronze_bank_transactions);

CREATE OR REFRESH STREAMING TABLE silver_account_notes (
  CONSTRAINT has_text EXPECT (length(note_text) > 10) ON VIOLATION DROP ROW
)
COMMENT 'Success Agent call notes (free text; embedded downstream for semantic search)'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT note_id, account_id, agent_id, CAST(created_date AS DATE) created_date, note_text
FROM STREAM(bronze_account_notes);

CREATE OR REFRESH STREAMING TABLE silver_account_outcomes
COMMENT 'Training labels for the cash-shortfall model'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT account_id, CAST(snapshot_date AS DATE) snapshot_date,
          CAST(cash_shortfall_60d AS INT) cash_shortfall_60d
FROM STREAM(bronze_account_outcomes);

-- ------------------------------------------------------------------ GOLD
CREATE OR REFRESH MATERIALIZED VIEW gold_account_features
COMMENT 'One row per SMB: cash position, AR/AP exposure, 90-day burn, rule-based runway + risk tier. Feature table for the ML model and source for Lakebase / Genie / App.'
TBLPROPERTIES ('quality' = 'gold')
AS
WITH asof AS (SELECT max(txn_date) AS as_of FROM silver_bank_transactions),
ar AS (
  SELECT account_id,
         sum(CASE WHEN status = 'overdue' THEN amount ELSE 0 END) overdue_ar,
         count_if(status = 'overdue') overdue_ar_count,
         sum(CASE WHEN status = 'open' THEN amount ELSE 0 END) open_ar,
         max(CASE WHEN status = 'overdue' THEN datediff((SELECT as_of FROM asof), due_date) END) max_days_overdue
  FROM silver_invoices GROUP BY account_id),
ap AS (
  SELECT account_id,
         sum(CASE WHEN status IN ('open', 'overdue') AND due_date <= date_add((SELECT as_of FROM asof), 30)
                  THEN amount ELSE 0 END) ap_due_30,
         count_if(status = 'overdue') overdue_bills
  FROM silver_bills GROUP BY account_id),
flow AS (
  SELECT account_id,
         sum(CASE WHEN direction = 'credit' THEN amount ELSE 0 END) / 3 monthly_inflow,
         sum(CASE WHEN direction = 'debit' THEN amount ELSE 0 END) / 3 monthly_outflow
  FROM silver_bank_transactions
  WHERE txn_date > date_sub((SELECT as_of FROM asof), 90)
  GROUP BY account_id),
base AS (
  SELECT a.account_id, a.business_name, a.industry, a.region, a.plan_tier, a.agent_id, g.agent_name,
         a.revenue_band, a.current_balance,
         round(coalesce(ar.overdue_ar, 0), 2) overdue_ar, coalesce(ar.overdue_ar_count, 0) overdue_ar_count,
         round(coalesce(ar.open_ar, 0), 2) open_ar, coalesce(ar.max_days_overdue, 0) max_days_overdue,
         round(coalesce(ap.ap_due_30, 0), 2) ap_due_30, coalesce(ap.overdue_bills, 0) overdue_bills,
         round(coalesce(f.monthly_inflow, 0), 2) monthly_inflow, round(coalesce(f.monthly_outflow, 0), 2) monthly_outflow,
         round(coalesce(f.monthly_inflow, 0) - coalesce(f.monthly_outflow, 0), 2) net_monthly,
         datediff((SELECT as_of FROM asof), a.signup_date) tenure_days,
         (SELECT as_of FROM asof) as_of_date
  FROM silver_smb_accounts a
  LEFT JOIN silver_success_agents g ON a.agent_id = g.agent_id
  LEFT JOIN ar ON a.account_id = ar.account_id
  LEFT JOIN ap ON a.account_id = ap.account_id
  LEFT JOIN flow f ON a.account_id = f.account_id)
SELECT *,
       CASE WHEN net_monthly >= 0 THEN 365
            WHEN current_balance <= 0 THEN 0
            ELSE least(365, round(current_balance / (-net_monthly / 30), 0)) END AS runway_days,
       CASE WHEN (CASE WHEN net_monthly >= 0 THEN 365 WHEN current_balance <= 0 THEN 0
                       ELSE current_balance / (-net_monthly / 30) END) < 45 THEN 'High'
            WHEN (CASE WHEN net_monthly >= 0 THEN 365 WHEN current_balance <= 0 THEN 0
                       ELSE current_balance / (-net_monthly / 30) END) < 120
                 OR overdue_ar > greatest(current_balance, 0) THEN 'Watch'
            ELSE 'Healthy' END AS rule_risk_tier
FROM base;

CREATE OR REFRESH MATERIALIZED VIEW gold_agent_portfolio
COMMENT 'Per Success Agent book summary: accounts, rule-based risk mix, overdue AR exposure'
TBLPROPERTIES ('quality' = 'gold')
AS SELECT agent_id, agent_name, region, count(*) accounts,
          count_if(rule_risk_tier = 'High') high_risk_accounts,
          count_if(rule_risk_tier = 'Watch') watch_accounts,
          round(sum(overdue_ar), 2) overdue_ar_total,
          round(avg(runway_days), 1) avg_runway_days
FROM gold_account_features GROUP BY agent_id, agent_name, region;
