#!/usr/bin/env python3
"""Synthetic raw data for the SMB Cash-Flow Copilot (100% fake, seeded, deterministic).

An SMB accounting SaaS platform: each SMB's bank feed, invoices (AR), bills (AP) and agent call notes land as
raw CSV drops: out/<batch>/<entity>/<entity>_<batch>.csv. batch_1 = initial load (as of 2026-11-18);
batch_2 = 2 more days of transactions + new invoices (incremental ingest). account_outcomes = prior-period
label (cash shortfall within 60 days) for ML. Hidden risk tier drives balances, AR overdue bias and inflows.
"""
import datetime as dt
import random
import sys
from pathlib import Path

random.seed(7)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "out")
TODAY = dt.date(2026, 11, 18)
N_ACCT = 1500
HERO_ID = "SMB-0112"

from common import *  # noqa: F401,F403  reference pools (REGIONS, AGENTS, CUSTOMERS, VENDORS, NOTES, ...) + helpers


def write(entity, batch, header, rows):
    return write_csv(OUT, entity, batch, header, rows)


def txn_rows(a, start_id, days_back, n, day_offset=0):
    return make_txns(TODAY, a, start_id, days_back, n, day_offset)




# --- accounts
accounts, used = [], set()
for i in range(1, N_ACCT + 1):
    ind = random.choice(INDUSTRIES)
    # 40 prefixes x 3 suffixes x 10 industries = 1,200 combos < N_ACCT, so add a
    # location qualifier once the plain combos run out (bounded attempts, no infinite loop)
    for attempt in range(200):
        name = f"{random.choice(PREFIX)} {random.choice(SUFFIX[ind])}"
        if attempt > 20:
            name += f" of {random.choice(['Austin', 'Boise', 'Dayton', 'Fresno', 'Mesa', 'Reno', 'Salem', 'Tulsa'])}"
        if name not in used and name != "Granite Goods":
            break
    else:
        name = f"{name} #{i}"
    used.add(name)
    region = random.choice(REGIONS)
    agent = random.choice([a for a in AGENTS if a[2] == region])
    plan = random.choices(PLANS, weights=[35, 30, 25, 10])[0]
    risk = random.choices(["high", "watch", "healthy"], weights=[16, 24, 60])[0]
    bal = {"high": random.randint(-6000, 12000), "watch": random.randint(8000, 40000),
           "healthy": random.randint(30000, 220000)}[risk]
    a = dict(account_id=f"SMB-{i:04d}", business_name=name, industry=ind, region=region,
             plan_tier=plan, agent_id=agent[0],
             signup_date=(TODAY - dt.timedelta(days=random.randint(60, 1800))).isoformat(),
             revenue_band={"Starter": "$0-250K", "Growth": "$250K-1M", "Pro": "$1-5M",
                           "Enterprise": "$5M+"}[plan],
             current_balance=bal, risk=risk)
    if a["account_id"] == HERO_ID:  # planted demo hero
        a.update(business_name="Granite Goods", industry="Retail", region="West",
                 plan_tier="Growth", agent_id="AG-01", revenue_band="$250K-1M",
                 current_balance=21500, risk="high")
    slug = a["business_name"].lower().replace(" & ", "").replace(" ", "")
    a["owner_email"] = f"owner@{slug}.example.com"
    a["tax_id"] = fake_ein()
    accounts.append(a)

n_acct = write("smb_accounts", "batch_1",
               ["account_id", "business_name", "industry", "region", "plan_tier", "agent_id",
                "signup_date", "revenue_band", "current_balance", "owner_email", "tax_id"],
               [[a[k] for k in ["account_id", "business_name", "industry", "region", "plan_tier",
                                "agent_id", "signup_date", "revenue_band", "current_balance",
                                "owner_email", "tax_id"]] for a in accounts])
write("success_agents", "batch_1", ["agent_id", "agent_name", "region"], AGENTS)

# --- invoices (AR)
inv, inv2, iid = [], [], 1
for a in accounts:
    if a["account_id"] == HERO_ID:
        # 8 overdue invoices = $89,040 stuck in AR, plus a few paid/open
        for amt, cust, ago in HERO_OVERDUE:
            issue = TODAY - dt.timedelta(days=ago)
            inv.append([f"INV-{iid:07d}", a["account_id"], cust, amt, issue.isoformat(),
                        (issue + dt.timedelta(days=30)).isoformat(), "overdue", ""])
            iid += 1
        for amt, st in [(5200, "paid"), (4100, "paid"), (6300, "open")]:
            issue = TODAY - dt.timedelta(days=20)
            inv.append([f"INV-{iid:07d}", a["account_id"], "Acme Corp", amt, issue.isoformat(),
                        (issue + dt.timedelta(days=30)).isoformat(), st,
                        (issue + dt.timedelta(days=12)).isoformat() if st == "paid" else ""])
            iid += 1
        continue
    bias = {"high": 0.45, "watch": 0.22, "healthy": 0.06}[a["risk"]]
    for _ in range(random.randint(8, 30)):
        issue = TODAY - dt.timedelta(days=random.randint(1, 180))
        terms = random.choice([15, 30, 45, 60])
        due = issue + dt.timedelta(days=terms)
        amt = round(random.uniform(250, 16000), 2)
        r = random.random()
        if due < TODAY and r < bias:
            st, paid = "overdue", ""
        elif due < TODAY and r < bias + 0.7:
            st, paid = "paid", (due - dt.timedelta(days=random.randint(0, 20))).isoformat()
        elif due >= TODAY and r < 0.4:
            st, paid = "paid", (issue + dt.timedelta(days=random.randint(1, terms))).isoformat()
        else:
            st, paid = "open", ""
        inv.append([f"INV-{iid:07d}", a["account_id"], random.choice(CUSTOMERS), amt,
                    issue.isoformat(), due.isoformat(), st, paid])
        iid += 1
    if random.random() < 0.25:  # batch 2: newly issued invoices
        for d in (1, 2):
            issue = TODAY + dt.timedelta(days=d)
            inv2.append([f"INV-{iid:07d}", a["account_id"], random.choice(CUSTOMERS),
                         round(random.uniform(250, 9000), 2), issue.isoformat(),
                         (issue + dt.timedelta(days=30)).isoformat(), "open", ""])
            iid += 1
H_INV = ["invoice_id", "account_id", "customer_name", "amount", "issue_date", "due_date",
         "status", "paid_date"]
n_inv = write("invoices", "batch_1", H_INV, inv)
n_inv2 = write("invoices", "batch_2", H_INV, inv2)

# --- bills (AP)
bills, bid = [], 1
for a in accounts:
    for _ in range(random.randint(5, 18)):
        issue = TODAY - dt.timedelta(days=random.randint(1, 120))
        due = issue + dt.timedelta(days=random.choice([15, 30, 45]))
        amt = round(random.uniform(150, 11000), 2)
        if a["account_id"] == HERO_ID:
            amt = round(amt * 0.8, 2)
        st = (random.choices(["paid", "overdue"], weights=[85, 15])[0] if due < TODAY
              else random.choices(["open", "paid"], weights=[70, 30])[0])
        bills.append([f"BILL-{bid:07d}", a["account_id"], random.choice(VENDORS), amt,
                      issue.isoformat(), due.isoformat(), st, due.isoformat() if st == "paid" else ""])
        bid += 1
n_bill = write("bills", "batch_1", ["bill_id", "account_id", "vendor_name", "amount", "issue_date",
                                    "due_date", "status", "paid_date"], bills)

# --- bank transactions
txn, txn2, tid = [], [], 1
for a in accounts:
    if a["account_id"] == HERO_ID:
        # last 90 days: $60,000 in, $109,500 out => net -$16,500/mo => ~39-day runway
        for k in range(12):
            txn.append([f"TXN-{tid:08d}", HERO_ID, (TODAY - dt.timedelta(days=3 + 7 * k)).isoformat(),
                        5000.0, "credit", "Customer Payment", "Customer Payment - Granite Goods"])
            tid += 1
        for k, (cat, amt) in enumerate(HERO_DEBITS):
            txn.append([f"TXN-{tid:08d}", HERO_ID, (TODAY - dt.timedelta(days=2 + 5 * k)).isoformat(),
                        float(amt), "debit", cat, f"{cat} - Granite Goods"])
            tid += 1
        continue
    rows = txn_rows(a, tid, 120, random.randint(40, 110))
    txn += rows
    tid += len(rows)
    rows2 = txn_rows(a, tid, 1, random.randint(0, 3), day_offset=2)
    rows2 = [r for r in rows2 if r[2] > TODAY.isoformat()]
    txn2 += rows2
    tid += len(rows2)
H_TXN = ["txn_id", "account_id", "txn_date", "amount", "direction", "category", "description"]
n_txn = write("bank_transactions", "batch_1", H_TXN, txn)
n_txn2 = write("bank_transactions", "batch_2", H_TXN, txn2)

# --- agent notes
notes, nid = [], 1
for a in accounts:
    k = 3 if a["account_id"] == HERO_ID else random.randint(1, 3)
    for j in range(k):
        txt = random.choice(NOTES[a["risk"]])
        if a["account_id"] == HERO_ID:
            txt = HERO_NOTES[j]
        notes.append([f"NOTE-{nid:05d}", a["account_id"], a["agent_id"],
                      (TODAY - dt.timedelta(days=random.randint(1, 90))).isoformat(), txt])
        nid += 1
n_note = write("account_notes", "batch_1",
               ["note_id", "account_id", "agent_id", "created_date", "note_text"], notes)

# --- outcome labels (prior period)
outc = []
for a in accounts:
    p = {"high": 0.72, "watch": 0.30, "healthy": 0.06}[a["risk"]]
    outc.append([a["account_id"], (TODAY - dt.timedelta(days=60)).isoformat(),
                 1 if random.random() < p else 0])
n_out = write("account_outcomes", "batch_1",
              ["account_id", "snapshot_date", "cash_shortfall_60d"], outc)

print(f"accounts={n_acct} invoices={n_inv}+{n_inv2} bills={n_bill} txns={n_txn}+{n_txn2} "
      f"notes={n_note} outcomes={n_out}")
print("hidden risk mix:", {r: sum(a['risk'] == r for a in accounts) for r in ['high', 'watch', 'healthy']})
