# SMB Cash-Flow Copilot

**Industry:** Financial Services / FinTech: small-business accounting and payments SaaS
**Customer problem:** A small-business accounting platform's Customer Success Agents each look after 100+ SMB customers. Cash-flow crunches are the main reason those customers churn or fail. Agents only find out when an owner calls in distress, or cancels. The warning signs already sit in the platform's own data: a bank balance trending down, invoices going overdue, bills piling up, worried notes from earlier calls. They're just spread across systems nobody watches together.

**Outcome:** Every morning, each agent gets a ranked book of SMBs likely to run short of cash within 60 days (ML), each with a plain-English reason and next-best action (Claude). The view is served in milliseconds from Lakebase inside a Databricks App, and leaders can ask portfolio questions in plain English through Genie.

> All data is **100% synthetic** (`data_gen/gen_data.py`, seeded). No customer data, names, or identifiers are included.

---

## End-to-end data journey (one orchestrated Lakeflow Job)

```
 raw CSV drops ──► Lakeflow SDP (Auto Loader) ──► bronze ─► silver (DQ expectations, PII masks) ─► gold features
 (UC Volume)                                                                                         │
                                                                ┌────────────────────────────────────┘
                                                                ▼
                         ML: cash_shortfall_model (MLflow, UC registry @champion) ─► account_cashflow_health
                         Gen AI: ai_query gte-large-en embeddings + Claude next-best-action briefings
                                                                │  UC synced tables (managed)
                                                                ▼
                         Lakebase Postgres: lb_* serving tables + pgvector HNSW + app.agent_actions (write-back)
                                                                │
          Genie space (NL over governed UC gold) ◄──────────────┼──────────────► Databricks App (FastAPI + SPA)
                                                                                  console · copilot · PII guard · Ask Genie
```

| Stage | What was built | Code | Execution evidence (text) |
|---|---|---|---|
| **Lakeflow** ingest | Serverless Spark Declarative Pipeline: 7 Auto Loader streaming tables (bronze), 7 typed silver tables with 13 expectations, 2 gold MVs. Incremental: batch_2 files picked up without reprocessing. One Lakeflow **Job** orchestrates pipeline → ML → 7 Lakebase syncs → vector refresh | `pipeline/cashflow_pipeline.sql`, `pipeline/*_spec.json` | `evidence/01_incremental_ingest.log`, `evidence/02_lakeflow_pipeline_event_log.log`, `evidence/03_job_run_summary.log` |
| **Unity Catalog** governance | Column masks on PII (`owner_email`, `tax_id`) via `mask_pii` UDF; governed tags that conform to workspace tag policies; comments on every table; least-privilege grants to the app SP; model in UC registry; lineage from raw volume to Lakebase | `scripts/uc_governance.sql` | `evidence/04_unity_catalog_governance.log` |
| **Lakebase** operational serving | Autoscaling Postgres 17 project; 7 **UC synced tables**; native `pgvector` MV + HNSW index; writable OLTP tables `app.agent_actions` and `app.copilot_audit` | `lakebase/*.sql`, `notebooks/03_refresh_lakebase.py` | `evidence/07_lakebase_serving.log` (3.8 ms point lookup, 0.6 ms HNSW search), `notebooks/executed/03_refresh_lakebase.executed.ipynb` |
| **ML + Gen AI** | GradientBoosting shortfall classifier: **AUC 0.79 vs 0.69** for today's "runway < 45 days" rule; MLflow-tracked, UC-registered `@champion`; batch scoring. Gen AI: `ai_query` embeddings (1024-d) and 304 Claude briefings; real-time grounded copilot (Claude Sonnet on FMAPI) with pgvector retrieval | `notebooks/02_ml_genai.py`, `app/backend.py` | `notebooks/executed/02_ml_genai.executed.ipynb` (metrics, importances, briefings) |
| **Genie** | Genie space on 6 governed tables, with business definitions + example SQL. A wrong `ILIKE '%West%'` (it matched *Mid*west) was caught and fixed with an instruction | `genie/create_genie_space.py`, `genie/ask_genie.py` | `evidence/06_genie_conversation.log` (4 Q&As with SQL + results) |
| **Databricks App** | FastAPI + SPA running as a service principal: agent book, account 360, ML risk, Claude briefing, copilot chat, PII block, action write-back, embedded Genie | `app/` | `evidence/05_app_api_calls.log` (live HTTP calls to the deployed app) |

### Demo hero
**SMB-0112 Granite Goods** (Retail, West, agent Priya Nair) has **$21,500** in the bank, burns **−$16,500/mo**, and has a **39-day runway**. ML puts its shortfall probability at **74%**. The reason: **$89,040 stuck in 8 overdue invoices** (Stark Retail alone owes $42,550). The owner is thinking about laying off staff. The copilot's answer is *chase receivables first*.

## Repo layout
```
data_gen/gen_data.py           synthetic raw data (batch_1 + incremental batch_2)
pipeline/cashflow_pipeline.sql Lakeflow SDP (bronze/silver/gold, expectations, masks)
pipeline/pipeline_spec.json    pipeline definition   pipeline/job_spec.json  orchestration job
notebooks/02_ml_genai.py       ML train/register/score + embeddings + Claude briefings
notebooks/03_refresh_lakebase.py  pgvector refresh + serving latency check
notebooks/executed/*.ipynb     the notebooks exported from the job run WITH outputs
lakebase/*.sql                 Postgres operational schema, pgvector MV, app grants
genie/                         Genie space definition + conversation script
app/                           Databricks App (app.py, backend.py, static/index.html, app.yaml)
scripts/                       dbsql.py (SQL runner), uc_governance.sql, exercise_app.py, export_run_notebooks.py
evidence/                      text logs of every stage actually running
deck/                          business presentation (md + pdf)
```

## Reproduce
Prereqs: Databricks CLI profile, a SQL warehouse, a UC catalog/schema you can write to, Lakebase enabled.
1. `python3 data_gen/gen_data.py` → upload `out/batch_1/*` to `/Volumes/<catalog>/smb_cashflow/raw/<entity>/`
2. Create the `mask_pii` function (see `scripts/uc_governance.sql` header), import `pipeline/cashflow_pipeline.sql`, `databricks pipelines create --json @pipeline/pipeline_spec.json`
3. Import notebooks, create the Lakebase project `smb-cashflow` + database `cashflow`, run `lakebase/01_operational_schema.sql`
4. Create synced tables (`databricks postgres create-synced-table … SNAPSHOT`) for the 7 `lb_*` tables, then `lakebase/02_note_vectors.sql`
5. `python3 genie/create_genie_space.py`, then `databricks apps create --json @app/app_spec.json`, deploy `app/`, run `lakebase/03_app_grants.sql` and `scripts/uc_governance.sql`
6. `databricks jobs create --json @pipeline/job_spec.json` → run. Upload `out/batch_2/*` and run again to see incremental ingest.

Placeholders like `<workspace-host>`, `<user>`, `<app-sp-client-id>` and `<lakebase-endpoint>` stand in for environment-specific values that were scrubbed from this public repo.
