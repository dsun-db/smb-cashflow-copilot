#!/usr/bin/env python3
"""Export executed notebook tasks from a job run into .ipynb files WITH their outputs (text), plus
a job-run summary. Usage: python3 scripts/export_run_notebooks.py <job_run_id>"""
import base64, html, json, os, re, subprocess, sys, urllib.parse

PROFILE = os.getenv("DATABRICKS_PROFILE", "fevm-0dcqtv")
RUN = sys.argv[1]


def cli(*a):
    return json.loads(subprocess.run(["databricks", *a, "-p", PROFILE, "-o", "json"], capture_output=True,
                                     text=True, check=True).stdout)


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s))


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _one(r):
    t, d = r.get("type"), r.get("data")
    if t == "table":
        cols = [c.get("name") for c in r.get("schema", [])]
        rows = d or []
        return "\n".join([" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in row) for row in rows[:50]])
    if t == "mimeBundle" and isinstance(d, dict):
        txt = d.get("text/plain", "")
        return None if txt.startswith("Downloading artifacts") else txt
    if t == "html":
        return strip_html(d)
    if t == "error" or r.get("errorSummary"):
        return "ERROR: " + strip_html(str(r.get("errorSummary") or d))
    if isinstance(d, str):
        return ANSI.sub("", d)
    return None


def result_text(res):
    if not res:
        return None
    items = res["data"] if res.get("type") == "listResults" else [res]
    parts = [p for p in (_one(i) for i in items) if p and p.strip()]
    parts = [p for p in parts if not p.startswith("Note: you may need to restart")]
    return "\n".join(parts) or None


run = cli("jobs", "get-run", RUN)
summary = [f"# Job run {RUN} ({run.get('run_name')}) - {run['state'].get('result_state')}",
           f"start={run.get('start_time')} end={run.get('end_time')} (epoch ms)", ""]
for t in sorted(run["tasks"], key=lambda t: t.get("start_time", 0)):
    dur = (t.get("end_time", 0) - t.get("start_time", 0)) / 1000
    summary.append(f"{t['task_key']:<40} {t['state'].get('result_state', ''):<8} {dur:7.1f}s")
    if "notebook_task" not in t:
        continue
    out = cli("jobs", "export-run", str(t["run_id"]), "--views-to-export", "CODE")
    page = out["views"][0]["content"]
    m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", page)
    model = json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode()))
    cells = []
    for c in model["commands"]:
        src = c.get("command", "")
        if src.startswith("%md"):
            cells.append({"cell_type": "markdown", "metadata": {}, "source": src[3:].strip()})
            continue
        txt = result_text(c.get("results"))
        outputs = [{"output_type": "stream", "name": "stdout", "text": txt}] if txt else []
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": c.get("position"),
                      "source": src, "outputs": outputs})
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
          "metadata": {"databricks_job_run_id": RUN, "task_run_id": t["run_id"], "task_key": t["task_key"]}}
    name = os.path.basename(t["notebook_task"]["notebook_path"])
    path = f"notebooks/executed/{name}.executed.ipynb"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(nb, open(path, "w"), indent=1)
    summary.append(f"    -> exported {path} ({len(cells)} cells, {sum(bool(c.get('outputs')) for c in cells)} with output)")
open("evidence/03_job_run_summary.log", "w").write("\n".join(summary) + "\n")
print("\n".join(summary))
