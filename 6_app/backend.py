"""Data layer for the SMB Cash-Flow Copilot app (Lakebase + real-time ML what-if).

Reads  : Lakebase Postgres - UC synced tables in schema smb_cashflow (low-latency serving)
Writes : Lakebase Postgres - schema app (agent actions, copilot audit) = OLTP write-back
ML     : cash_shortfall_model@champion behind Model Serving endpoint (what-if scenarios)
Auth   : the app's service principal (OAuth, auto-injected) - no tokens in code.
"""
import os
import time

import psycopg2
import psycopg2.extras
import requests
from databricks.sdk.core import Config

_cfg = Config()
LB_ENDPOINT = os.getenv("LAKEBASE_ENDPOINT", "projects/smb-cashflow/branches/production/endpoints/primary")
MODEL_EP = os.getenv("MODEL_ENDPOINT", "smb-cashflow-shortfall")
S = "smb_cashflow"  # Postgres schema holding the synced tables
FEATURES = ["current_balance", "overdue_ar", "overdue_ar_count", "open_ar", "max_days_overdue", "ap_due_30",
            "overdue_bills", "monthly_inflow", "monthly_outflow", "net_monthly", "runway_days", "tenure_days"]


def base():
    h = _cfg.host or ""
    return h if h.startswith("http") else f"https://{h}"


def headers():
    h = _cfg.authenticate()
    h["Content-Type"] = "application/json"
    return h


# ------------------------------------------------------------------ Lakebase
_tok = {"v": None, "exp": 0}


def _pg_password():
    now = time.time()
    if _tok["v"] and _tok["exp"] > now + 60:
        return _tok["v"]
    r = requests.post(f"{base()}/api/2.0/postgres/credentials", headers=headers(),
                      json={"endpoint": LB_ENDPOINT}, timeout=30)
    r.raise_for_status()
    _tok.update(v=r.json()["token"], exp=now + 3000)
    return _tok["v"]


def _connect():
    return psycopg2.connect(host=os.getenv("PGHOST"), dbname=os.getenv("PGDATABASE", "cashflow"),
                            user=os.getenv("PGUSER") or os.getenv("DATABRICKS_CLIENT_ID"),
                            password=_pg_password(), port=5432, sslmode="require", connect_timeout=15)


def q(sql, params=None):
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall() if cur.description else []
        conn.commit()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ------------------------------------------------------------------ reads
def agents():
    return q(f"SELECT agent_id, agent_name, region FROM {S}.lb_success_agents ORDER BY agent_id")


def portfolio(agent_id):
    summary = q(f"SELECT * FROM {S}.lb_agent_portfolio WHERE agent_id=%s", (agent_id,))
    accts = q(f"""SELECT account_id, business_name, industry, plan_tier, current_balance, overdue_ar,
                         overdue_ar_count, net_monthly, runway_days, shortfall_prob, risk_tier, primary_driver
                  FROM {S}.lb_account_cashflow_health WHERE agent_id=%s
                  ORDER BY shortfall_prob DESC, overdue_ar DESC""", (agent_id,))
    tiers = {t: sum(a["risk_tier"] == t for a in accts) for t in ("High", "Watch", "Healthy")}
    return {"summary": (summary[0] if summary else {}) | {"ml_tiers": tiers}, "accounts": accts}


def account(account_id):
    h = q(f"SELECT * FROM {S}.lb_account_cashflow_health WHERE account_id=%s", (account_id,))
    return {
        "health": h[0] if h else None,
        "invoices": q(f"""SELECT invoice_id, customer_name, amount, issue_date, due_date, status
                          FROM {S}.lb_invoices WHERE account_id=%s AND status <> 'paid'
                          ORDER BY CASE status WHEN 'overdue' THEN 0 ELSE 1 END, due_date LIMIT 12""",
                      (account_id,)),
        "bills": q(f"""SELECT vendor_name, amount, due_date, status FROM {S}.lb_bills
                       WHERE account_id=%s AND status IN ('open','overdue') ORDER BY due_date LIMIT 8""",
                   (account_id,)),
        "notes": q(f"""SELECT created_date, note_text FROM {S}.lb_account_notes_embedded
                       WHERE account_id=%s ORDER BY created_date DESC LIMIT 5""", (account_id,)),
        "briefing": (q(f"SELECT briefing FROM {S}.lb_copilot_briefings WHERE account_id=%s",
                       (account_id,)) or [{}])[0].get("briefing"),
        "actions": q("""SELECT action_type, note, created_at FROM app.agent_actions
                        WHERE account_id=%s ORDER BY created_at DESC LIMIT 10""", (account_id,)),
    }


def log_action(account_id, agent_id, action_type, note):
    return q("""INSERT INTO app.agent_actions(account_id, agent_id, action_type, note)
                VALUES (%s,%s,%s,%s) RETURNING action_id, created_at""",
             (account_id, agent_id, action_type, note))[0]



# ------------------------------------------------------------------ real-time ML what-if
def _runway(balance, net_monthly):
    if net_monthly >= 0:
        return 365.0
    return 0.0 if balance <= 0 else min(365.0, round(balance / (-net_monthly / 30)))


def what_if(account_id, customer):
    """Re-score the account on the serving endpoint as if all overdue invoices from `customer` were collected."""
    h = q(f"SELECT * FROM {S}.lb_account_cashflow_health WHERE account_id=%s", (account_id,))[0]
    inv = q(f"""SELECT customer_name, sum(amount) amt, count(*) n FROM {S}.lb_invoices
                WHERE account_id=%s AND status='overdue' GROUP BY customer_name""", (account_id,))
    hit = next((i for i in inv if i["customer_name"] == customer), None)
    if not hit:
        return {"error": f"no overdue invoices from {customer}"}
    base_row = {f: float(h[f] or 0) for f in FEATURES}
    s = dict(base_row)
    s["current_balance"] += hit["amt"]
    s["overdue_ar"] -= hit["amt"]
    s["overdue_ar_count"] -= hit["n"]
    if s["overdue_ar_count"] <= 0:
        s["max_days_overdue"] = 0.0
    s["runway_days"] = _runway(s["current_balance"], s["net_monthly"])
    t = time.time()
    r = requests.post(f"{base()}/serving-endpoints/{MODEL_EP}/invocations", headers=headers(), timeout=60,
                      json={"dataframe_split": {"columns": FEATURES,
                                                "data": [[base_row[f] for f in FEATURES], [s[f] for f in FEATURES]]}})
    r.raise_for_status()
    p = [row[1] for row in r.json()["predictions"]]  # pyfunc predict_proba -> [P(0), P(1)]
    return {"account_id": account_id, "collect_from": customer, "collected": round(hit["amt"], 2),
            "invoices": hit["n"], "endpoint": MODEL_EP, "latency_ms": int((time.time() - t) * 1000),
            "before": {"shortfall_prob": round(p[0], 4), "runway_days": base_row["runway_days"],
                       "current_balance": base_row["current_balance"]},
            "after": {"shortfall_prob": round(p[1], 4), "runway_days": s["runway_days"],
                      "current_balance": s["current_balance"]}}


def health():
    out = {"lakebase": False, "model_endpoint": MODEL_EP}
    try:
        out["accounts"] = q(f"SELECT count(*) c FROM {S}.lb_account_cashflow_health")[0]["c"]
        out["lakebase"] = True
    except Exception as e:
        out["lakebase_error"] = str(e)[:200]
    return out
