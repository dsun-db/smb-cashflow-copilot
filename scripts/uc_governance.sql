-- Unity Catalog governance for the SMB Cash-Flow Copilot (run after the pipeline + ML job)
GRANT USE CATALOG ON CATALOG serverless_stable_0dcqtv_catalog TO `<app-sp-client-id>`;
GRANT USE SCHEMA ON SCHEMA serverless_stable_0dcqtv_catalog.smb_cashflow TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_cashflow_health TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.copilot_briefings TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.gold_agent_portfolio TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_invoices TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_bills TO `<app-sp-client-id>`;
GRANT SELECT ON TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_bank_transactions TO `<app-sp-client-id>`;
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_cashflow_health ALTER COLUMN shortfall_prob COMMENT 'ML P(cash shortfall within 60 days) from cash_shortfall_model@champion';
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_cashflow_health ALTER COLUMN runway_days COMMENT 'Days of cash left at the trailing-90-day burn rate (365 = cash-flow positive)';
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_cashflow_health ALTER COLUMN overdue_ar COMMENT 'USD of unpaid invoices past due date';
-- Tags conform to this workspace's governed tag policies (domain / data_product are policy-controlled keys)
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_cashflow_health SET TAGS ('domain' = 'finance', 'data_product' = 'analytics', 'cashflow_layer' = 'gold_serving');
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.copilot_briefings SET TAGS ('domain' = 'finance', 'data_product' = 'machine_learning', 'ai_generated' = 'true');
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.account_notes_embedded SET TAGS ('domain' = 'finance', 'data_product' = 'machine_learning', 'ai_generated' = 'embeddings');
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_smb_accounts SET TAGS ('domain' = 'finance', 'data_product' = 'data_engineering', 'contains_pii' = 'true');
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_smb_accounts ALTER COLUMN owner_email SET TAGS ('pii_type' = 'email');
ALTER TABLE serverless_stable_0dcqtv_catalog.smb_cashflow.silver_smb_accounts ALTER COLUMN tax_id SET TAGS ('pii' = 'ssn')  -- closest allowed value: government tax identifier;
