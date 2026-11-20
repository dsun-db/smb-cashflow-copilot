"""Reference pools (all names fictional) + helpers for the synthetic SMB data generator."""
import csv
import datetime as dt
import random
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

# Planted demo hero SMB-0112 "Granite Goods": 8 overdue invoices = $89,040 stuck in AR
HERO_OVERDUE = [(18400, "Stark Retail", 75), (14250, "Stark Retail", 68), (12800, "Vandelay Industries", 62),
                (11600, "Globex", 58), (9900, "Stark Retail", 52), (8740, "Initech", 49), (7350, "Globex", 46),
                (6000, "Hooli", 41)]
# last 90 days: 12 x $5,000 in vs $109,500 out => net -$16,500/mo => ~39-day runway on a $21,500 balance
HERO_DEBITS = ([("Payroll", 9000)] * 6 + [("Rent", 6500)] * 3 + [("Supplies", 4300)] * 6 + [("Loan Payment", 3400)] * 3)
HERO_NOTES = ["Owner says sales are fine but cash is tight; considering cutting two staff.",
              "Largest customer (Stark Retail) is 30+ days late on several invoices.",
              "Asked about a short-term loan to cover December payroll."]


def write_csv(OUT, entity, batch, header, rows):
    d = OUT / batch / entity
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{entity}_{batch}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def fake_ein():
    return f"{random.randint(10, 99)}-{random.randint(1000000, 9999999)}"



def make_txns(TODAY, a, start_id, days_back, n, day_offset=0):
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
