# SMB Cash-Flow Copilot

**Industry:** FinTech / small-business accounting & payments SaaS. **Buyer:** Chief Customer Officer (sponsor) and Director of Customer Success Ops (domain owner).

**Problem:** each Customer Success Agent looks after 100+ SMB customers, and cash crunches are the main reason those customers churn or fail. The warning signs already sit on the platform (bank feed, overdue invoices, bills due, worried call notes), but nobody sees them together. Agents find out when the owner panics or cancels.

**Outcome:** each morning every agent gets a book ranked by **ML-predicted 60-day cash-shortfall risk**, with the reason, a Claude-written next-best action, a live **what-if** ("if this customer pays, risk drops to X"), and one-click action logging. All of it is served in milliseconds from Lakebase in a Databricks App. Leaders ask portfolio questions in plain English through Genie.

> 100% synthetic data (`data_generator/gen_data.py`, seeded). No customer data or identifiers.

## Evidence map: each stage folder holds its code *and* an `EVIDENCE_*` file of real run output
| Stage | Folder | Proof (text, from real runs) |
|---|---|---|
| **Lakeflow** ingest + orchestration | `1_lakeflow/` | Auto Loader picked up only the new batch_2 files (+2,269 txns, +670 invoices); 13 expectations, 0 failed; 1 Job, 11 tasks, ~7 min, all SUCCESS |
| **Unity Catalog** governance | `2_unity_catalog/` | PII column masks (`****.com`, `****0580`), policy-compliant tags, 6 SELECT grants to the app SP, lineage bronze→silver→gold→Lakebase |
| **ML + Gen AI** | `3_ml_genai/` | GBT **AUC 0.788 vs 0.689** for today's runway rule; MLflow → UC `@champion` v5 → **serving endpoint** (AI Gateway inference table); 3,063 embeddings; 304 Claude briefings |
| **Lakebase** serving | `4_lakebase/` | 7 UC synced tables ONLINE; point lookup ~5 ms; pgvector HNSW `Index Scan` 0.45 ms; app write-back rows in `app.agent_actions` and `app.copilot_audit` |
| **Genie** | `5_genie/` | 4 NL questions → SQL → results (e.g. overdue AR in High-risk accounts by agent) |
| **Databricks App** | `6_app/` | live HTTP calls: book, account, **what-if 74% → 10%**, grounded copilot, **PII blocked**, action saved, Genie in-app |

**Hero (SMB-0112 Granite Goods):** $21.5K in the bank, −$16.5K/mo, **39-day runway**, ML shortfall **74%**. **$89,040 stuck in 8 overdue invoices** ($42,550 from Stark Retail). The owner is thinking about layoffs; the copilot says chase receivables. The what-if confirms it: if Stark pays, **risk falls to 10% and runway rises to 116 days** (Hooli alone only gets to 56%).

## Architecture
```
raw CSV drops (UC Volume) -> Lakeflow SDP: Auto Loader bronze -> silver (expectations, PII masks) -> gold features
  -> 02_ml_model: GBT, MLflow, UC registry @champion, batch scores + rolls serving endpoint -> account_cashflow_health
  -> 03_genai_enrichment: ai_query gte-large-en embeddings + Claude next-best-action briefings
  -> UC synced tables -> Lakebase Postgres (lb_*) + pgvector HNSW MV + app.agent_actions / app.copilot_audit
  -> Databricks App (FastAPI + SPA, service principal) <- Model Serving what-if, FMAPI Claude, Genie Conversation API
```

## Design decisions & trade-offs
1. **Lakebase, not DBSQL, behind the app:** agents need ms point reads, *writes* and vector search in one OLTP store. DBSQL/Genie serve analytics.
2. **Synced tables in SNAPSHOT mode:** scoring is daily and tables are small. CDF is already on, so TRIGGERED/CONTINUOUS is a config change when intraday freshness matters.
3. **pgvector in Lakebase, not Vector Search:** 3K notes that live next to the operational data, so one SQL join returns notes and risk. At millions of docs, or for hybrid search, I'd move to Mosaic AI Vector Search. Synced arrays land as jsonb, so a native `vector(1024)` MV with HNSW took search from ~1.1 s (cast per query) to <1 ms. Templated notes mean duplicate vectors, which **broke HNSW recall at the default ef_search=40** (it missed exact matches). The app sets `ef_search=400`.
4. **GBT for risk; the LLM for language:** tabular, non-linear (balance × burn × AR), explainable importances. Claude explains and recommends, grounded only in that account's facts.
5. **Batch + real-time:** batch ranks the whole book cheaply; a scale-to-zero endpoint powers interactive what-ifs. The notebook rolls the endpoint to each new `@champion`.
6. **Tier = ML OR rule:** High if P ≥ 0.55 or runway < 30 d. The rule is a safety net agents already trust.
7. **PII defense in depth:** UC column masks at source, an app pre-check before any LLM call (blocked and redacted), and every call audited in Lakebase.
8. **Genie ≠ copilot:** Genie handles governed ad-hoc analytics and shows its SQL; the copilot does account-level guidance. Testing caught Genie using `ILIKE '%West%'`, which matched *Mid*west; fixed with an instruction.

**Limitations / next:** synthetic labels (production needs point-in-time features), regex PII guard (move to AI Gateway guardrails), OBO auth plus UC row filters per agent, MLflow GenAI eval for the copilot, Lakehouse Monitoring on the inference table, Asset Bundles for CI/CD.

## Layout & reproduce
`data_generator/` gen_data.py + common.py (synthetic raw data) · `1_lakeflow/` 01_bronze_silver.sql + 02_gold.sql (pipeline), deploy_specs.json (pipeline + job) · `2_unity_catalog/` uc_governance.sql (+ `mask_pii` UDF) · `3_ml_genai/` 02_ml_model.py, 03_genai_enrichment.py · `4_lakebase/` lakebase_setup.sql, 04_refresh_lakebase.py · `5_genie/` create_genie_space.py · `6_app/` app.py, backend.py (Lakebase + what-if), ai.py (copilot/search/PII/Genie), static/.

1. `python3 data_generator/gen_data.py out` → upload `out/batch_1/<entity>/` to `/Volumes/<catalog>/smb_cashflow/raw/<entity>/`
2. Create `mask_pii`, then the pipeline and job from `deploy_specs.json` (workspace folders: `pipeline/`, `notebooks/`)
3. Lakebase project `smb-cashflow` + db `cashflow`; synced tables (`databricks postgres create-synced-table`, SNAPSHOT) for the 7 `lb_*` tables; `lakebase_setup.sql`
4. Serving endpoint `smb-cashflow-shortfall` (model `@champion`, AI Gateway inference table); Genie space; app with resources: Claude + gte endpoints, the model endpoint (CAN_QUERY), Genie (CAN_RUN), warehouse, Lakebase database (`postgres` resource); then the grants
5. Run the job; land `out/batch_2/*`; run again (incremental).

Scrubbed placeholders: `<workspace-host>`, `<workspace-id>`, `<user>`, `<app-sp-client-id>`, `<lakebase-endpoint>`.
