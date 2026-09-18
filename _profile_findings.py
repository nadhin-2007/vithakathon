import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

data = Path(r"D:\vit\atlas\hackathon-data\data")


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(v):
    v = (v or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def parse_num(v):
    v = (v or "").strip()
    if not v or v.upper() in {"ND", "NA", "N/A"} or v.startswith("<") or v.startswith(">"):
        return None
    v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


dm = read_csv(data / "DM.csv")
lb = read_csv(data / "LB.csv")
ex = read_csv(data / "EX.csv")
ae = read_csv(data / "AE.csv")
cm = read_csv(data / "CM.csv")
ranges = read_csv(data / "reference_ranges.csv")

# comma decimals
comma = [r for r in lb if "," in (r.get("LBORRES") or "")]
print("comma LBORRES", len(comma), comma[:5])

# duplicate identity
keys = defaultdict(list)
for r in dm:
    keys[(r["DMINIT"], r["BRTHDTC"], r["SEX"])].append(r["USUBJID"])
dups = {k: v for k, v in keys.items() if len(v) > 1}
print("identity dups", dups)

# extra S05
print("S05 subjects", [r["USUBJID"] for r in dm if r["SITEID"] == "S05"])

# missing WEEK8
ex_by = defaultdict(set)
for r in ex:
    ex_by[r["USUBJID"]].add(r["VISIT"])
visits = {"BASELINE", "WEEK2", "WEEK4", "WEEK8", "WEEK12", "WEEK16", "WEEK20", "WEEK24", "EOS"}
for uid, vs in sorted(ex_by.items()):
    miss = visits - vs
    if miss:
        print("missing EX", uid, miss, "arm", next(d["ARM"] for d in dm if d["USUBJID"] == uid))

# 20mg
print("20mg rows")
for r in ex:
    if r["EXDOSE"] == "20":
        print(r)

# Hy's law
uln = {}
for r in ranges:
    uln[(r["LBTESTCD"], r["UNIT"].lower(), r["LAB"])] = float(r["HIGH"])
print("uln", uln)

site = {r["USUBJID"]: r["SITEID"] for r in dm}


def lab_id(r):
    return "S07" if r["LBORRESU"].lower() in {"ukat/l", "µkat/l", "ukatl"} else "CENTRAL"


def value_xuln(r):
    num = parse_num(r["LBORRES"])
    if num is None:
        return None
    unit = r["LBORRESU"]
    test = r["LBTESTCD"]
    lab = lab_id(r)
    key = (test, unit.lower(), lab)
    if key not in uln:
        # convert ukat to U/L
        if unit.lower() in {"ukat/l", "µkat/l"}:
            num = num * 60
            unit = "U/L"
            lab = "CENTRAL"
            key = (test, "u/l", "CENTRAL")
        else:
            return None
    high = uln.get(key) or uln.get((test, unit.lower(), "CENTRAL"))
    if not high:
        return None
    return num / high


by_subj = defaultdict(list)
for r in lb:
    if r["LBTESTCD"] in {"ALT", "AST", "BILI"}:
        x = value_xuln(r)
        dt = parse_date(r["LBDTC"])
        by_subj[r["USUBJID"]].append((r, x, dt))

hys = []
for uid, recs in by_subj.items():
    trans = [(r, x, dt) for r, x, dt in recs if r["LBTESTCD"] in {"ALT", "AST"} and x is not None and x > 3]
    bili = [(r, x, dt) for r, x, dt in recs if r["LBTESTCD"] == "BILI" and x is not None and x > 2]
    for tr, tx, tdt in trans:
        for br, bx, bdt in bili:
            if tdt and bdt and abs((tdt - bdt).days) <= 14:
                hys.append((uid, site[uid], tr["VISIT"], tr["LBTESTCD"], tx, br["VISIT"], bx, (tdt - bdt).days))
                break
print("hys count unique subj", len(set(h[0] for h in hys)), "pairs", len(hys))
print("hys sample", hys[:15])

# screening exclusion ALT/AST >2 ULN, creat>1.5, age, hba1c
excl = []
for r in dm:
    uid = r["USUBJID"]
    age = int(r["AGE"])
    hba = parse_num(r["SCR_HBA1C"])
    if age < 18 or age > 75:
        excl.append((uid, "AGE", age))
    if hba is None or hba < 7.0 or hba > 10.5:
        excl.append((uid, "HBA1C", hba))
print("dm eligibility flags", excl)

scr_labs = [r for r in lb if r["VISIT"] == "SCREENING"]
for r in scr_labs:
    if r["LBTESTCD"] in {"ALT", "AST"}:
        x = value_xuln(r)
        if x is not None and x > 2:
            print("hepatic excl", r["USUBJID"], r["LBTESTCD"], r["LBORRES"], r["LBORRESU"], x)
    if r["LBTESTCD"] == "CREAT":
        n = parse_num(r["LBORRES"])
        if n is not None and n > 1.5:
            print("renal excl", r["USUBJID"], n)

print("glucocorticoid", [ (r["USUBJID"], r["CMTRT"], r["CMSTDTC"]) for r in cm if r["CMCLAS"]=="SYSTEMIC_GLUCOCORTICOID"])
print("su", [(r["USUBJID"], r["CMTRT"], r["CMSTDTC"]) for r in cm if r["CMCLAS"]=="SULFONYLUREA"])

# AE dates vs first dose
first_dose = {}
for r in ex:
    d = parse_date(r["EXSTDTC"])
    if d:
        first_dose[r["USUBJID"]] = min(first_dose.get(r["USUBJID"], d), d)
print("AE before first dose")
for r in ae:
    d = parse_date(r["AESTDTC"])
    fd = first_dose.get(r["USUBJID"])
    if d and fd and d < fd:
        print(r["USUBJID"], r["AESEQ"], r["AESTDTC"], "first", fd.date(), r["AETERM"])
