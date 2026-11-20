#!/usr/bin/env python3
"""Create (or update) the 'SMB Cash-Flow Copilot' Genie space via the Genie REST API."""
import json, os, subprocess, sys, uuid

PROFILE = os.getenv("DATABRICKS_PROFILE", "fevm-0dcqtv")
WH = os.getenv("WAREHOUSE_ID", "b7cf85f7d0eac200")
FQ = "serverless_stable_0dcqtv_catalog.smb_cashflow"
SPACE_ID = sys.argv[1] if len(sys.argv) > 1 else None


def hid():
    return uuid.uuid4().hex


tables = ["account_cashflow_health", "copilot_briefings", "gold_agent_portfolio",
          "silver_bank_transactions", "silver_bills", "silver_invoices"]
instructions = """You answer questions for Customer Success leaders and agents at a small-business accounting platform.
Definitions:
- "runway" = runway_days in account_cashflow_health (days of cash left at the current 90-day burn rate; 365 = cash-flow positive).
- "at risk" / "high risk" = risk_tier = 'High' (ML shortfall_prob >= 0.55 or runway < 30 days). "Watch" is the middle tier.
- "shortfall probability" = shortfall_prob, the ML model's probability the SMB runs out of cash in the next 60 days. Show it as a percentage.
- "stuck cash" / "overdue AR" = overdue_ar (unpaid invoices past their due date). overdue_ar_count = number of those invoices.
- Agent = Customer Success Agent (agent_id / agent_name). Region is exactly one of 'West', 'Midwest', 'Northeast', 'South'.
  ALWAYS filter region with equality (region = 'West'), never LIKE/ILIKE - 'Midwest' contains the substring 'West'.
- For invoice-level detail use silver_invoices where status = 'overdue'.
Always round currency to whole dollars and sort riskiest first."""

examples = [
    ("Which West region accounts have less than 45 days of runway?",
     f"SELECT account_id, business_name, agent_name, current_balance, overdue_ar, runway_days, round(shortfall_prob*100) AS shortfall_pct\nFROM {FQ}.account_cashflow_health\nWHERE region = 'West' AND runway_days < 45\nORDER BY runway_days ASC"),
    ("How much overdue receivable is stuck in high-risk accounts by agent?",
     f"SELECT agent_name, count(*) AS high_risk_accounts, round(sum(overdue_ar)) AS overdue_ar\nFROM {FQ}.account_cashflow_health\nWHERE risk_tier = 'High'\nGROUP BY agent_name ORDER BY overdue_ar DESC"),
]
space = {
    "version": 2,
    "config": {"sample_questions": sorted([
        {"id": hid(), "question": [q]} for q in [
            "Which West region accounts have less than 45 days of runway?",
            "How much overdue receivable is stuck in high-risk accounts by agent?",
            "Which industries have the highest average shortfall probability?",
            "Show Granite Goods' overdue invoices by customer",
        ]], key=lambda x: x["id"])},
    "data_sources": {"tables": [{"identifier": f"{FQ}.{t}"} for t in sorted(tables)]},
    "instructions": {
        "text_instructions": [{"id": hid(), "content": [instructions]}],
        "example_question_sqls": sorted([{"id": hid(), "question": [q], "sql": [s]} for q, s in examples],
                                        key=lambda x: x["id"]),
    },
}
body = {"warehouse_id": WH, "title": "SMB Cash-Flow Copilot",
        "description": "Ask about SMB cash runway, ML shortfall risk, overdue receivables and agent books.",
        "serialized_space": json.dumps(space)}
method, path = ("patch", f"/api/2.0/genie/spaces/{SPACE_ID}") if SPACE_ID else ("post", "/api/2.0/genie/spaces")
p = subprocess.run(["databricks", "api", method, path, "-p", PROFILE, "--json", json.dumps(body)],
                   capture_output=True, text=True)
print(p.stdout[:600] or p.stderr[:1500])
