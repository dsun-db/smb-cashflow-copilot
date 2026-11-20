#!/usr/bin/env python3
"""Run SQL on a Databricks SQL warehouse via the Statement Execution API (CLI auth).

Usage:  python3 scripts/dbsql.py "SELECT ..."      or   python3 scripts/dbsql.py -f file.sql
Statements in a file are split on ';' at line end. Prints results as a text table,
so output can be tee'd into evidence/*.log.
Env: DATABRICKS_PROFILE, WAREHOUSE_ID, CATALOG, SCHEMA (defaults below).
"""
import json, os, subprocess, sys, time

PROFILE = os.getenv("DATABRICKS_PROFILE", "fevm-0dcqtv")
WH = os.getenv("WAREHOUSE_ID", "b7cf85f7d0eac200")
CAT = os.getenv("CATALOG", "serverless_stable_0dcqtv_catalog")
SCH = os.getenv("SCHEMA", "smb_cashflow")


def api(method, path, body=None):
    cmd = ["databricks", "api", method, path, "-p", PROFILE]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:1500])
    return json.loads(p.stdout or "{}")


def run(sql, max_rows=50):
    r = api("post", "/api/2.0/sql/statements",
            {"warehouse_id": WH, "statement": sql, "catalog": CAT, "schema": SCH,
             "wait_timeout": "50s", "on_wait_timeout": "CONTINUE"})
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(2)
        r = api("get", f"/api/2.0/sql/statements/{r['statement_id']}")
    if r["status"]["state"] != "SUCCEEDED":
        print("FAILED:", json.dumps(r["status"])[:1500])
        return False
    cols = [c["name"] for c in r.get("manifest", {}).get("schema", {}).get("columns", [])]
    rows = r.get("result", {}).get("data_array", []) or []
    if cols:
        w = [max(len(c), *(len(str(x[i])) for x in rows[:max_rows])) if rows else len(c)
             for i, c in enumerate(cols)]
        w = [min(x, 60) for x in w]
        print(" | ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
        print("-+-".join("-" * x for x in w))
        for row in rows[:max_rows]:
            print(" | ".join(("NULL" if v is None else str(v))[:60].ljust(w[i]) for i, v in enumerate(row)))
        print(f"({r.get('manifest', {}).get('total_row_count', len(rows))} rows)")
    else:
        print("OK")
    return True


if __name__ == "__main__":
    if sys.argv[1] == "-f":
        text = open(sys.argv[2]).read()
        stmts = [s.strip() for s in text.split(";\n") if s.strip() and not all(
            l.strip().startswith("--") or not l.strip() for l in s.strip().splitlines())]
    else:
        stmts = [sys.argv[1]]
    ok = True
    for s in stmts:
        print(f"\n>>> {s.strip()[:300]}")
        ok = run(s) and ok
    sys.exit(0 if ok else 1)
