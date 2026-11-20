# SMB Cash-Flow Copilot
## Catch small-business cash crunches 60 days early and keep the customer

**For:** Chief Customer Officer (executive sponsor) · Director, Customer Success Operations (domain owner)
**Industry:** small-business accounting & payments SaaS (FinTech)

> **Outcome:** Customer Success Agents see which SMBs will run short of cash *before* the owner panics or churns, with the reason and the next best action, in one screen.

---

## 1. The problem: we learn about cash crunches too late

- Our SMB customers' biggest risk is **cash flow, not profit**. Invoices go unpaid while payroll and bills keep coming.
- Every signal is already in our platform: bank feed, invoices (AR), bills (AP), agents' call notes. **No one sees them together.**
- Today an agent learns about it when the owner calls in distress, or **cancels**.

**In a representative book of 1,500 SMBs (synthetic, modeled on our patterns):**

| Signal | Value |
|---|---|
| SMBs likely to hit a cash shortfall within 60 days | **304 (20%)** |
| Cash stuck in overdue invoices at those SMBs | **$14.9M** |
| Overdue AR across the whole book | **$30.2M** |

---

## 2. What the agent sees: Granite Goods, a real-feeling Monday morning

- **$21.5K** in the bank, burning **$16.5K/month**, so a **39-day runway**. ML puts the **shortfall risk at 74%**.
- But **$89K is stuck in 8 overdue invoices**, $42.5K of it from one customer (Stark Retail).
- The owner's last call: *"thinking about cutting two staff."*
- **Copilot's advice:** *Chase receivables first. Overdue AR is 4x the cash on hand.* It also produces a reminder plan in priority order, and **one click logs the action**.
- The agent is ready in **under a minute**. Today that takes three systems and about 15 minutes of digging.

---

## 3. Impact in your KPIs

| | KPI | Baseline | With Copilot | How we measure |
|---|---|---|---|---|
| **Exec sponsor (CCO)** | Gross revenue retention of at-risk SMBs | at-risk SMBs found reactively | **304 at-risk SMBs flagged ~60 days early**; model ranks risk better than today's rule (**AUC 0.79 vs 0.69**) | churn rate of flagged vs. unflagged cohort |
| | Customer outcome: cash recovered for SMBs | $14.9M overdue AR at at-risk SMBs | **every 10% collected = $1.5M back to customers** | AR collected within 30 days of an action |
| **Domain owner (CS Ops)** | Agent prep time per at-risk account | ~15 min across 3 tools *(assumption)* | **< 1 min**: one screen, briefing pre-written | app telemetry (`agent_actions`) |
| | Proactive touches per agent per week | ad hoc | **~25 prioritized accounts per agent** | actions logged per agent |
| | Compliance: PII never sent to AI | manual policy | **100% of SSN/card prompts blocked + audited** | `copilot_audit` table |

*Baselines marked "assumption" are to be confirmed in the pilot.*

---

## 4. How it works: one platform, no new silos

```
Bank feed · invoices · bills · notes  ->  Lakeflow (Auto Loader + quality checks)  ->  Unity Catalog (governed bronze/silver/gold)
  ->  ML shortfall model (MLflow, UC registry) + Claude briefings & embeddings
  ->  Lakebase (millisecond serving, vector search, agent write-back)
  ->  Databricks App for agents  +  Genie for leaders ("Which West accounts have < 45 days of runway?")
```

- **Daily, automated:** one job runs ingest, scoring, briefings and serving refresh in **about 7 minutes**.
- **Fast where it matters:** account lookup in **3.8 ms**, similar-situation search in **< 1 ms** (Lakebase pgvector).
- **Self-serve insight:** leaders ask Genie in plain English and get governed SQL and answers, with no ticket to the data team.

---

## 5. Trust & governance built in

- **PII masked at the source:** owner email and tax ID are masked by Unity Catalog column masks, and stay masked for the agents and the AI.
- **AI guardrails:** prompts with SSNs or card numbers are **blocked before they reach the model**, and every copilot call is **audited**.
- **Grounded answers:** Claude answers only from the account's own facts. Each answer shows the numbers it used.
- **Least privilege + lineage:** the app runs as a service principal with read-only grants. Lineage is tracked end to end, from the raw file to the agent's screen.
- **Model governance:** versioned model in Unity Catalog with a `@champion` alias, so we can roll back in one step.

---

## 6. Rollout & ask

| Phase | Scope | Success criteria |
|---|---|---|
| **Weeks 0-2: Pilot setup** | Connect production bank-feed, AR/AP and notes data; 2 agent pods (~25 agents) | data fresh daily; model AUC ≥ 0.75 on real outcomes |
| **Weeks 3-10: Pilot** | Flagged accounts worked through the Copilot vs. control pods | **churn ↓ in flagged cohort**, AR collected, prep time < 2 min |
| **Quarter 2: Scale** | All CS pods; owner-facing alerts in-product | GRR lift reported to the exec team |

**Ask:** sponsor a 10-week pilot with two Customer Success pods, plus a named CS Ops owner for success metrics.
