#!/usr/bin/env python3
"""Exercise the deployed Databricks App end-to-end and log every request/response as text.

Auth: the caller's short-lived Databricks CLI U2M OAuth token, held in memory only (never printed/saved).
Usage: python3 scripts/exercise_app.py > evidence/05_app_api_calls.log
"""
import json, os, subprocess, sys, time, urllib.request

PROFILE = os.getenv("DATABRICKS_PROFILE", "fevm-0dcqtv")
APP = os.getenv("APP_URL", "https://<app-host>")
TOKEN = json.loads(subprocess.run(["databricks", "auth", "token", "-p", PROFILE], capture_output=True,
                                  text=True, check=True).stdout)["access_token"]


def call(method, path, body=None):
    req = urllib.request.Request(APP + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            status, data = r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        status, data = e.code, e.read().decode()[:500]
    ms = int((time.time() - t) * 1000)
    print(f"\n### {method} {path}  ->  HTTP {status}  ({ms} ms)")
    if body:
        print("request:", json.dumps(body))
    return status, data


def show(obj, n=1800):
    print(json.dumps(obj, indent=2, default=str)[:n])


print(f"# App API evidence  {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n# app: {APP.split('//')[1].split('-')[0]}-... (Databricks App, SP auth to Lakebase / FMAPI / Genie)")

_, d = call("GET", "/api/health"); show(d)
_, d = call("GET", "/api/agents"); show(d[:4]); print(f"... {len(d)} agents")
_, d = call("GET", "/api/portfolio?agent_id=AG-01")
show(d["summary"]); print("top 5 accounts by ML shortfall risk:")
for a in d["accounts"][:5]:
    print(f"  {a['account_id']} {a['business_name']:<26} tier={a['risk_tier']:<7} p={a['shortfall_prob']:.2f} "
          f"runway={a['runway_days']:.0f}d overdue_ar=${a['overdue_ar']:,.0f}")
_, d = call("GET", "/api/account/SMB-0112")
show(d["health"]); print("briefing:", d["briefing"]); print("overdue invoices:")
for i in d["invoices"][:8]:
    print("  ", i)
_, d = call("GET", "/api/search?q=" + urllib.parse.quote("owner worried about making payroll"))
for r in d:
    print("  ", r)
_, d = call("POST", "/api/copilot", {"account_id": "SMB-0112",
                                      "question": "Should the owner cut staff or chase receivables?"})
print("answer:\n" + str(d.get("answer") or d)); print("grounding:", d.get("grounding"), "| latency_ms:", d.get("latency_ms"))
_, d = call("POST", "/api/copilot", {"account_id": "SMB-0112",
                                      "question": "Owner SSN is 123-45-6789 and card 4111 1111 1111 1111, check their credit?"})
show(d)
_, d = call("POST", "/api/actions", {"account_id": "SMB-0112", "agent_id": "AG-01",
                                      "action_type": "send_ar_reminders", "note": "Reminders for 8 overdue invoices (Stark Retail first)"})
show(d)
_, d = call("GET", "/api/account/SMB-0112"); print("actions now on account:", d["actions"][:3])
_, d = call("POST", "/api/genie", {"question": "Which West region accounts have less than 45 days of runway?"})
print("genie text:", d.get("text")); print("genie sql:\n", d.get("sql")); print("columns:", d.get("columns"))
for r in d.get("rows", [])[:10]:
    print("  ", r)
print(f"  ... {len(d.get('rows', []))} rows")
