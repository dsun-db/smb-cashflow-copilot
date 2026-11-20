-- SMB Cash-Flow Copilot :: Lakeflow Spark Declarative Pipeline (serverless), file 1/2
-- raw CSV drops in a UC Volume --Auto Loader--> bronze --expectations + PII masks--> silver
-- Config: raw_path = /Volumes/<catalog>/smb_cashflow/raw

-- ------------------------------------------------------------------ BRONZE (Auto Loader)
CREATE OR REFRESH STREAMING TABLE bronze_smb_accounts
COMMENT 'Raw SMB account master drops (Auto Loader, schema-on-read)'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/smb_accounts', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_success_agents
COMMENT 'Raw Customer Success Agent roster'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/success_agents', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_invoices
COMMENT 'Raw invoices (accounts receivable) issued by SMBs to their customers'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/invoices', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_bills
COMMENT 'Raw bills (accounts payable) owed by SMBs to vendors'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/bills', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_bank_transactions
COMMENT 'Raw bank-feed transactions connected to each SMB'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/bank_transactions', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_account_notes
COMMENT 'Raw free-text notes written by Success Agents after customer calls'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_path}/account_notes', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_account_outcomes
COMMENT 'Historical labels: did the SMB hit a cash shortfall within 60 days of the snapshot'
TBLPROPERTIES ('quality' = 'bronze') AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
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

