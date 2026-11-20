"""AI layer: grounded Claude copilot, pgvector semantic search, PII guard, Genie Conversation API."""
import os
import re
import time

import requests

from backend import S, account, base, headers, q

LLM = os.getenv("LLM_ENDPOINT", "databricks-claude-sonnet-5-5")
EMBED = os.getenv("EMBEDDING_ENDPOINT", "databricks-gte-large-en")
GENIE_SPACE = os.getenv("GENIE_SPACE_ID", "")


def embed(text):
    r = requests.post(f"{base()}/serving-endpoints/{EMBED}/invocations", headers=headers(),
                      json={"input": [text]}, timeout=30)
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def similar_notes(text, k=5, exclude=None):
    lit = "[" + ",".join(f"{x:.6f}" for x in embed(text)) + "]"
    # HNSW candidate set, then one best note per account. ef_search raised: templated notes = many duplicate
    # vectors, which drop HNSW recall at the default of 40 (exact matches were missed).
    return q(f"""SET hnsw.ef_search = 400;
                 SELECT * FROM (
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
    od = [i for i in d["invoices"] if i["status"] == "overdue"]  # all of them, so totals reconcile
    if od:
        facts.append("Overdue invoices: " + "; ".join(f"{i['customer_name']} ${i['amount']:,.0f} due {i['due_date']}" for i in od))
    if d["notes"]:
        facts.append("Agent notes: " + " | ".join(n["note_text"] for n in d["notes"][:3]))
    peer_txt = "\n".join(f"- {p['business_name']} ({p['risk_tier']}): {p['note_text']}" for p in peers) or "none"
    system = ("You are the Cash-Flow Copilot for a Customer Success Agent at a small-business accounting platform. "
              "Answer ONLY from the facts given; cite the numbers; recommend 2-3 concrete next actions the agent can "
              "take with the owner. Never invent data. Under 170 words. Never request personal identifiers.")
    user = f"ACCOUNT FACTS:\n" + "\n".join(facts) + f"\n\nSIMILAR SITUATIONS (pgvector search):\n{peer_txt}\n\nQUESTION: {question}"
    r = requests.post(f"{base()}/serving-endpoints/{LLM}/invocations", headers=headers(), timeout=90,
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
    base = f"{base()}/api/2.0/genie/spaces/{GENIE_SPACE}"
    if conversation_id:
        r = requests.post(f"{base}/conversations/{conversation_id}/messages", headers=headers(),
                          json={"content": question}, timeout=30)
    else:
        r = requests.post(f"{base}/start-conversation", headers=headers(), json={"content": question}, timeout=30)
    r.raise_for_status()
    m = r.json()
    conv = m.get("conversation_id") or conversation_id
    mid = m.get("message_id") or m.get("id") or m["message"]["id"]
    for _ in range(60):
        msg = requests.get(f"{base}/conversations/{conv}/messages/{mid}", headers=headers(), timeout=30).json()
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
                               headers=headers(), timeout=30).json()
            sr = res.get("statement_response", {})
            out["columns"] = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            out["rows"] = (sr.get("result", {}) or {}).get("data_array", [])[:50]
    return out


