#!/usr/bin/env python3
"""Synthetic raw data for the SMB Cash-Flow Copilot (100% fake, seeded).

Scenario: a small-business accounting SaaS platform ("the platform") whose
Customer Success Agents look after a book of SMB customers. Each SMB connects
its bank feed and sends invoices / pays bills through the platform.

Writes raw CSV "landing" files the way an upstream system would drop them:
  out/<batch>/<entity>/<entity>_<batch>.csv
batch_1 = initial load (as of 2026-11-18); batch_2 = two more days of bank
transactions + newly issued invoices (lands later to show incremental ingest).

Also writes account_outcomes (historical label: did the SMB hit a cash
shortfall in the following 60 days in the prior period) for ML training.
"""
import csv
import datetime as dt
import random
import sys
from pathlib import Path

random.seed(7)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "out")
TODAY = dt.date(2026, 11, 18)
N_ACCT = 1500
HERO_ID = "SMB-0112"

REGIONS = ["West", "Midwest", "Northeast", "South"]
INDUSTRIES = ["Construction", "Professional Services", "Retail", "Restaurant",
              "Healthcare Services", "E-commerce", "Marketing Agency",
              "Home Services", "Manufacturing", "Nonprofit"]
PLANS = ["Starter", "Growth", "Pro", "Enterprise"]
PREFIX = ["Summit", "Blue Harbor", "Oakline", "Riverstone", "Bright Path", "Ironwood",
          "Copperfield", "Silver Peak", "Meadowlark", "Northgate", "Cedar & Co",
          "Lantern", "Highland", "Maple Grove", "Vista", "Anchor", "Redwood",
          "Compass", "Willow Creek", "Sunset", "Harbor Point", "Evergreen",
          "Trailhead", "Beacon", "Foxglove", "Juniper", "Kestrel", "Larkspur",
          "Mosaic", "Pinecrest", "Quarry", "Saltmarsh", "Tidewater", "Umber",
          "Wildrose", "Yarrow", "Zephyr", "Brookside", "Driftwood", "Elmstead"]
SUFFIX = {"Construction": ["Builders", "Contracting", "Construction LLC"],
          "Professional Services": ["Consulting", "Advisors", "Partners"],
          "Retail": ["Goods", "Supply Co", "Mercantile"],
          "Restaurant": ["Kitchen", "Bistro", "Eatery"],
          "Healthcare Services": ["Clinic", "Health Group", "Wellness"],
          "E-commerce": ["Online", "Direct", "Commerce"],
          "Marketing Agency": ["Media", "Creative", "Marketing"],
          "Home Services": ["Home Services", "Plumbing & HVAC", "Landscaping"],
          "Manufacturing": ["Manufacturing", "Fabrication", "Industries"],
          "Nonprofit": ["Foundation", "Community Fund", "Alliance"]}
AGENTS = [("AG-01", "Priya Nair", "West"), ("AG-02", "Marcus Webb", "West"),
          ("AG-03", "Elena Park", "West"),
          ("AG-04", "Dana Kowalski", "Midwest"), ("AG-05", "Tom Alvarez", "Midwest"),
          ("AG-06", "Ravi Shah", "Midwest"),
          ("AG-07", "Grace Lin", "Northeast"), ("AG-08", "Jamal Carter", "Northeast"),
          ("AG-09", "Hannah Weiss", "Northeast"),
          ("AG-10", "Sofia Rossi", "South"), ("AG-11", "Ben Okafor", "South"),
          ("AG-12", "Lucia Torres", "South")]
INC_CAT = ["Customer Payment", "Product Sales", "Service Revenue", "Refund Reversal"]
EXP_CAT = ["Payroll", "Rent", "Supplies", "Software Subscriptions", "Utilities",
           "Marketing", "Insurance", "Loan Payment", "Taxes", "Travel"]
CUSTOMERS = ["Acme Corp", "Globex", "Initech", "Umbrella LLC", "Wayne Ent", "Stark Retail",
             "Hooli", "Pied Piper", "Vandelay Industries", "Wonka Supply", "Nakatomi",
             "Cyberdyne", "Soylent", "Tyrell Group", "Gekko & Co", "Duff Distributors"]
VENDORS = ["PayrollPro", "Metro Office Leasing", "OfficeMart", "CloudSuite", "City Power & Light",
           "AdReach", "SafeHarbor Insurance", "Community Bank Loan", "State Tax Board",
           "RideFleet", "BulkBuy Wholesale", "FiberNet", "DocuStack", "ShopCart"]
NOTES = {
    "high": [
        "Owner flagged a cash crunch; payroll due next week and receivables are piling up. Discussed invoice reminders.",
        "Business is carrying large overdue receivables from a single customer. Recommended deposit terms on new work.",
        "Seasonal dip hit hard and the balance is close to zero. Explored a line of credit and invoice financing.",
        "Late supplier payments are causing stress. Set up bill scheduling to smooth outflows.",
        "Owner asked whether to lay off staff; walked through collecting overdue invoices first.",
    ],
    "watch": [
        "Growth is steady but margins are tightening. Suggested reviewing recurring software spend.",
        "Customer occasionally pays late. Turned on automatic payment reminders.",
        "Expanding headcount soon; wants a runway forecast before hiring.",
        "Asked about invoice financing options to bridge a 30-day gap.",
    ],
    "healthy": [
        "Strong quarter. Owner interested in upgrading plan for advanced reporting.",
        "Cash position healthy; exploring reinvestment into marketing.",
        "Happy customer with good payment discipline. Candidate for a case study.",
        "Wants better dashboards for their bookkeeper. Demoed reports.",
    ],
}


def write(entity, batch, header, rows):
    d = OUT / batch / entity
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{entity}_{batch}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def fake_ein():
    return f"{random.randint(10, 99)}-{random.randint(1000000, 9999999)}"


# ---------------------------------------------------------------- accounts
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

# ---------------------------------------------------------------- invoices (AR)
inv, inv2, iid = [], [], 1
for a in accounts:
    if a["account_id"] == HERO_ID:
        # 8 overdue invoices = $89,040 stuck in AR, plus a few paid/open
        for amt, cust, ago in [(18400, "Stark Retail", 75), (14250, "Stark Retail", 68),
                               (12800, "Vandelay Industries", 62), (11600, "Globex", 58),
                               (9900, "Stark Retail", 52), (8740, "Initech", 49),
                               (7350, "Globex", 46), (6000, "Hooli", 41)]:
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

# ---------------------------------------------------------------- bills (AP)
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

# ---------------------------------------------------------------- bank transactions
def txn_rows(a, start_id, days_back, n, day_offset=0):
    p_credit = {"high": 0.33, "watch": 0.42, "healthy": 0.50}[a["risk"]]
    rows = []
    for k in range(n):
        d = TODAY + dt.timedelta(days=day_offset) - dt.timedelta(days=random.randint(0, days_back))
        if random.random() < p_credit:
            direction, cat, amt = "credit", random.choice(INC_CAT), round(random.uniform(300, 12000), 2)
        else:
            direction, cat, amt = "debit", random.choice(EXP_CAT), round(random.uniform(100, 8000), 2)
        rows.append([f"TXN-{start_id + k:08d}", a["account_id"], d.isoformat(), amt, direction,
                     cat, f"{cat} - {a['business_name'][:14]}"])
    return rows


txn, txn2, tid = [], [], 1
for a in accounts:
    if a["account_id"] == HERO_ID:
        # last 90 days: $60,000 in, $109,500 out => net -$16,500/mo => ~39-day runway
        for k in range(12):
            txn.append([f"TXN-{tid:08d}", HERO_ID, (TODAY - dt.timedelta(days=3 + 7 * k)).isoformat(),
                        5000.0, "credit", "Customer Payment", "Customer Payment - Granite Goods"])
            tid += 1
        for k, (cat, amt) in enumerate([("Payroll", 9000)] * 6 + [("Rent", 6500)] * 3 +
                                       [("Supplies", 4300)] * 6 + [("Loan Payment", 3400)] * 3):
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

# ---------------------------------------------------------------- agent notes
notes, nid = [], 1
for a in accounts:
    k = 3 if a["account_id"] == HERO_ID else random.randint(1, 3)
    for j in range(k):
        txt = random.choice(NOTES[a["risk"]])
        if a["account_id"] == HERO_ID:
            txt = ["Owner says sales are fine but cash is tight; considering cutting two staff.",
                   "Largest customer (Stark Retail) is 30+ days late on several invoices.",
                   "Asked about a short-term loan to cover December payroll."][j]
        notes.append([f"NOTE-{nid:05d}", a["account_id"], a["agent_id"],
                      (TODAY - dt.timedelta(days=random.randint(1, 90))).isoformat(), txt])
        nid += 1
n_note = write("account_notes", "batch_1",
               ["note_id", "account_id", "agent_id", "created_date", "note_text"], notes)

# ---------------------------------------------------------------- outcome labels (prior period)
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
