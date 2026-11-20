-- SMB Cash-Flow Copilot :: Lakeflow SDP, file 2/2 - gold feature + portfolio materialized views

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
  LEFT JOIN flow f ON a.account_id = f.account_id),
runway AS (
  SELECT *, CASE WHEN net_monthly >= 0 THEN 365 WHEN current_balance <= 0 THEN 0
                 ELSE least(365, current_balance / (-net_monthly / 30)) END AS raw_runway
  FROM base)
SELECT * EXCEPT (raw_runway), round(raw_runway, 0) AS runway_days,
       CASE WHEN raw_runway < 45 THEN 'High'
            WHEN raw_runway < 120 OR overdue_ar > greatest(current_balance, 0) THEN 'Watch'
            ELSE 'Healthy' END AS rule_risk_tier
FROM runway;

CREATE OR REFRESH MATERIALIZED VIEW gold_agent_portfolio
COMMENT 'Per Success Agent book summary: accounts, rule-based risk mix, overdue AR exposure'
TBLPROPERTIES ('quality' = 'gold')
AS SELECT agent_id, agent_name, region, count(*) accounts,
          count_if(rule_risk_tier = 'High') high_risk_accounts,
          count_if(rule_risk_tier = 'Watch') watch_accounts,
          round(sum(overdue_ar), 2) overdue_ar_total,
          round(avg(runway_days), 1) avg_runway_days
FROM gold_account_features GROUP BY agent_id, agent_name, region;
