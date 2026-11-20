#!/usr/bin/env python3
"""Ask the Genie space questions via the Conversation API; print answer text, generated SQL and result rows.
Usage: python3 genie/ask_genie.py > evidence/06_genie_conversation.log"""
import json, os, subprocess, time

PROFILE = os.getenv("DATABRICKS_PROFILE", "fevm-0dcqtv")
SPACE = os.getenv("GENIE_SPACE_ID", "01f1e4f8753e1bb08155f860d8d67ecb")
QUESTIONS = [
    "Which West region accounts have less than 45 days of runway?",
    "How much overdue receivable is stuck in high-risk accounts by agent?",
    "Which industries have the highest average shortfall probability?",
    "Show Granite Goods' overdue invoices by customer",
]


def api(method, path, body=None):
    cmd = ["databricks", "api", method, path, "-p", PROFILE] + (["--json", json.dumps(body)] if body else [])
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


base = f"/api/2.0/genie/spaces/{SPACE}"
print(f"# Genie space 'SMB Cash-Flow Copilot' ({SPACE}) - conversation transcript {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
conv = None
for q in QUESTIONS:
    t = time.time()
    m = api("post", f"{base}/conversations/{conv}/messages" if conv else f"{base}/start-conversation", {"content": q})
    conv = m.get("conversation_id") or conv
    mid = m.get("message_id") or m.get("id") or m["message"]["id"]
    while True:
        msg = api("get", f"{base}/conversations/{conv}/messages/{mid}")
        if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    print(f"\n## Q: {q}\nstatus={msg.get('status')}  ({time.time() - t:.1f}s)")
    for att in msg.get("attachments", []) or []:
        if att.get("text"):
            print("Genie:", att["text"].get("content"))
        if att.get("query"):
            print("Genie:", att["query"].get("description"))
            print("SQL:\n" + att["query"].get("query", ""))
            res = api("get", f"{base}/conversations/{conv}/messages/{mid}/attachments/{att['attachment_id']}/query-result")
            sr = res.get("statement_response", {})
            cols = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            rows = (sr.get("result", {}) or {}).get("data_array", []) or []
            print("Result:", " | ".join(cols))
            for r in rows[:12]:
                print("  ", " | ".join("" if v is None else str(v) for v in r))
            print(f"   ({sr.get('manifest', {}).get('total_row_count', len(rows))} rows)")
