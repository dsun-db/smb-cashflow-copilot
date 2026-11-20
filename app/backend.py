"""Data + AI access layer for the SMB Cash-Flow Copilot app.

Reads    : Lakebase Postgres (UC synced tables, schema smb_cashflow) - low-latency serving
Writes   : Lakebase Postgres (schema app) - agent actions + copilot audit log (OLTP write-back)
Search   : pgvector over agent-note embeddings (app.note_vectors, HNSW)
Copilot  : Claude on Databricks Foundation Model APIs, grounded in Lakebase facts, PII pre-check
Genie    : Genie Conversation API over the governed UC gold tables (natural-language analytics)
Auth     : the app's service principal (OAuth, auto-injected) - no tokens in code.
"""
import os
import re
import time

import psycopg2
import psycopg2.extras
import requests
from databricks.sdk.core import Config

_cfg = Config()
LB_ENDPOINT = os.getenv("LAKEBASE_ENDPOINT", "projects/smb-cashflow/branches/production/endpoints/primary")
LLM = os.getenv("LLM_ENDPOINT", "databricks-claude-sonnet-5-5")
EMBED = os.getenv("EMBEDDING_ENDPOINT", "databricks-gte-large-en")
GENIE_SPACE = os.getenv("GENIE_SPACE_ID", "")
S = "smb_cashflow"  # Postgres schema holding the synced tables


def _base():
    h = _cfg.host or ""
    return h if h.startswith("http") else f"https://{h}"


def _headers():
    h = _cfg.authenticate()
    h["Content-Type"] = "application/json"
    return h


# ------------------------------------------------------------------ Lakebase
_tok = {"v": None, "exp": 0}


def _pg_password():
    now = time.time()
    if _tok["v"] and _tok["exp"] > now + 60:
        return _tok["v"]
    r = requests.post(f"{_base()}/api/2.0/postgres/credentials", headers=_headers(),
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


# ------------------------------------------------------------------ AI
def embed(text):
    r = requests.post(f"{_base()}/serving-endpoints/{EMBED}/invocations", headers=_headers(),
                      json={"input": [text]}, timeout=30)
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def similar_notes(text, k=5, exclude=None):
    lit = "[" + ",".join(f"{x:.6f}" for x in embed(text)) + "]"
    # HNSW candidate set, then one best note per account
    return q(f"""SELECT * FROM (
                   SELECT DISTINCT ON (c.account_id) c.account_id, h.business_name, h.risk_tier, c.note_text, c.distance
                   FROM (SELECT account_id, note_text, round((emb <=> %s::vector)::numeric, 3) AS distance
                         FROM app.note_vectors WHERE account_id <> %s
                         ORDER BY emb <=> %s::vector LIMIT 60) c
                   JOIN {S}.lb_account_cashflow_health h USING (account_id)
                   ORDER BY c.account_id, c.distance) x
                 ORDER BY distance, risk_tier LIMIT %s""",
             (lit, exclude or "", lit, k))


PII = {"US_SSN": r"\b\d{3}-\d{2}-\d{4}\b", "CARD_NUMBER": r"\b(?:\d[ -]?){13,16}\b",
       "EIN": r"\b\d{2}-\d{7}\b", "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.]+"}


def pii_check(text):
    return sorted(k for k, rx in PII.items() if re.search(rx, text))


def _audit(account_id, question, blocked, entities, latency_ms):
    try:
        q("""INSERT INTO app.copilot_audit(account_id, question_redacted, blocked, pii_entities, model, latency_ms)
             VALUES (%s,%s,%s,%s,%s,%s)""",
          (account_id, _redact(question), blocked, ",".join(entities), LLM, latency_ms))
    except Exception:
        pass


def _redact(t):
    for k, rx in PII.items():
        t = re.sub(rx, f"<{k}>", t)
    return t


def ask_copilot(account_id, question):
    t0 = time.time()
    found = pii_check(question)
    if found:
        _audit(account_id, question, True, found, 0)
        return {"blocked": True, "pii_entities": found, "redacted": _redact(question)}
    d = account(account_id)
    h = d["health"] or {}
    try:
        peers = similar_notes(f"{h.get('primary_driver', '')}: {question}", k=3, exclude=account_id)
    except Exception:
        peers = []
    facts = [f"Business: {h.get('business_name')} ({h.get('industry')}, {h.get('region')}, {h.get('plan_tier')} plan)",
             f"Bank balance ${h.get('current_balance', 0):,.0f}; net monthly cash flow ${h.get('net_monthly', 0):,.0f}; "
             f"runway {h.get('runway_days', 0):.0f} days",
             f"Overdue receivables ${h.get('overdue_ar', 0):,.0f} across {h.get('overdue_ar_count')} invoices; "
             f"open AR ${h.get('open_ar', 0):,.0f}; bills due in 30 days ${h.get('ap_due_30', 0):,.0f}",
             f"ML 60-day cash-shortfall probability {100 * (h.get('shortfall_prob') or 0):.0f}% -> risk tier "
             f"{h.get('risk_tier')} (driver: {h.get('primary_driver')})"]
    od = [i for i in d["invoices"] if i["status"] == "overdue"][:6]
    if od:
        facts.append("Overdue invoices: " + "; ".join(f"{i['customer_name']} ${i['amount']:,.0f} due {i['due_date']}" for i in od))
    if d["notes"]:
        facts.append("Agent notes: " + " | ".join(n["note_text"] for n in d["notes"][:3]))
    peer_txt = "\n".join(f"- {p['business_name']} ({p['risk_tier']}): {p['note_text']}" for p in peers) or "none"
    system = ("You are the Cash-Flow Copilot for a Customer Success Agent at a small-business accounting platform. "
              "Answer ONLY from the facts given; cite the numbers; recommend 2-3 concrete next actions the agent can "
              "take with the owner. Never invent data. Under 170 words. Never request personal identifiers.")
    user = f"ACCOUNT FACTS:\n" + "\n".join(facts) + f"\n\nSIMILAR SITUATIONS (pgvector search):\n{peer_txt}\n\nQUESTION: {question}"
    r = requests.post(f"{_base()}/serving-endpoints/{LLM}/invocations", headers=_headers(), timeout=90,
                      json={"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                            "max_tokens": 2000})  # headroom: model may spend tokens on adaptive thinking first
    ms = int((time.time() - t0) * 1000)
    _audit(account_id, question, False, [], ms)
    if r.status_code != 200:
        return {"blocked": False, "error": r.text[:400]}
    content = r.json()["choices"][0]["message"]["content"]
    if isinstance(content, list):  # newer FMAPI Claude responses return content blocks
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type", "text") == "text")
    return {"blocked": False, "answer": content, "model": LLM,
            "latency_ms": ms, "similar": peers,
            "grounding": {k: h.get(k) for k in ("current_balance", "overdue_ar", "runway_days", "shortfall_prob", "risk_tier")}}


# ------------------------------------------------------------------ Genie
def ask_genie(question, conversation_id=None):
    base = f"{_base()}/api/2.0/genie/spaces/{GENIE_SPACE}"
    if conversation_id:
        r = requests.post(f"{base}/conversations/{conversation_id}/messages", headers=_headers(),
                          json={"content": question}, timeout=30)
    else:
        r = requests.post(f"{base}/start-conversation", headers=_headers(), json={"content": question}, timeout=30)
    r.raise_for_status()
    m = r.json()
    conv = m.get("conversation_id") or conversation_id
    mid = m.get("message_id") or m.get("id") or m["message"]["id"]
    for _ in range(60):
        msg = requests.get(f"{base}/conversations/{conv}/messages/{mid}", headers=_headers(), timeout=30).json()
        if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    out = {"conversation_id": conv, "status": msg.get("status"), "text": None, "sql": None, "columns": [], "rows": []}
    for att in msg.get("attachments", []) or []:
        if att.get("text"):
            out["text"] = att["text"].get("content")
        if att.get("query"):
            out["sql"] = att["query"].get("query")
            out["text"] = out["text"] or att["query"].get("description")
            res = requests.get(f"{base}/conversations/{conv}/messages/{mid}/attachments/{att['attachment_id']}/query-result",
                               headers=_headers(), timeout=30).json()
            sr = res.get("statement_response", {})
            out["columns"] = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            out["rows"] = (sr.get("result", {}) or {}).get("data_array", [])[:50]
    return out


def health():
    out = {"lakebase": False, "llm": LLM, "genie_space": bool(GENIE_SPACE)}
    try:
        out["accounts"] = q(f"SELECT count(*) c FROM {S}.lb_account_cashflow_health")[0]["c"]
        out["lakebase"] = True
    except Exception as e:
        out["lakebase_error"] = str(e)[:200]
    return out
