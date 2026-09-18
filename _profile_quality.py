import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

data = Path(r"D:\vit\atlas\hackathon-data\data")


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


lb = read_csv(data / "LB.csv")
print("LBTESTCD", Counter(r["LBTESTCD"] for r in lb))
print("LBORRESU", Counter(r["LBORRESU"] for r in lb))
nonnum = []
for r in lb:
    v = (r.get("LBORRES") or "").strip()
    if not v:
        nonnum.append(("EMPTY", r["LBTESTCD"], r["LBORRESU"], r["USUBJID"], r["LBSEQ"]))
        continue
    try:
        float(v.replace(",", "."))
    except ValueError:
        nonnum.append((v, r["LBTESTCD"], r["LBORRESU"], r["USUBJID"], r["LBSEQ"]))
print("nonnumeric_or_empty", len(nonnum))
print(Counter(x[0] for x in nonnum))
print("sample nonnum", nonnum[:20])

print("units by test")
by = defaultdict(Counter)
for r in lb:
    by[r["LBTESTCD"]][r["LBORRESU"]] += 1
for t, c in by.items():
    print(t, dict(c))

ae = read_csv(data / "AE.csv")
print("AESER", Counter(r["AESER"] for r in ae))
print("AESHOSP", Counter(r["AESHOSP"] for r in ae))
print("AESER vs AESHOSP mismatches")
for r in ae:
    if r["AESHOSP"] == "Y" and r["AESER"] != "Y":
        print("hosp_not_ser", r["USUBJID"], r["AESEQ"], r["AETERM"], r["AESER"], r["AESHOSP"])
    if r["AESER"] == "Y" and r["AESHOSP"] != "Y":
        print("ser_not_hosp", r["USUBJID"], r["AESEQ"], r["AETERM"], r["AESER"], r["AESHOSP"])

cm = read_csv(data / "CM.csv")
print("CMCLAS", Counter(r["CMCLAS"] for r in cm))

ex = read_csv(data / "EX.csv")
print("EXDOSE", Counter(r["EXDOSE"] for r in ex))
print("EXTRT", Counter(r["EXTRT"] for r in ex))
print("EXDOSU", Counter(r["EXDOSU"] for r in ex))

dm = read_csv(data / "DM.csv")
print("ARM", Counter(r["ARM"] for r in dm))
print("SITEID", Counter(r["SITEID"] for r in dm))
print("SEX", Counter(r["SEX"] for r in dm))
print("AGE min max", min(int(r["AGE"]) for r in dm), max(int(r["AGE"]) for r in dm))
print("RFSTDTC formats sample")
print(Counter(len(r["RFSTDTC"]) for r in dm))
print("non-iso dates DM", [r["RFSTDTC"] for r in dm if "-" in r["RFSTDTC"] and not r["RFSTDTC"][:4].isdigit()][:10])
print("other formats", [r["RFSTDTC"] for r in dm if not r["RFSTDTC"][:4].isdigit()][:20])

ds = read_csv(data / "DS.csv")
print("DSDECOD", Counter(r["DSDECOD"] for r in ds))
dm_ids = {r["USUBJID"] for r in dm}
ds_ids = {r["USUBJID"] for r in ds}
print("DM not in DS", dm_ids - ds_ids)
print("DS not in DM", ds_ids - dm_ids)

# date formats
import re
iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
dmon = re.compile(r"^\d{2}-[A-Z]{3}-\d{4}$", re.I)
for name, field, rows in [
    ("DM", "RFSTDTC", dm),
    ("AE", "AESTDTC", ae),
    ("EX", "EXSTDTC", ex),
    ("LB", "LBDTC", lb),
    ("DS", "DSSTDTC", ds),
]:
    c = Counter()
    for r in rows:
        v = (r.get(field) or "").strip()
        if not v:
            c["empty"] += 1
        elif iso.match(v):
            c["iso"] += 1
        elif dmon.match(v):
            c["dmon"] += 1
        else:
            c["other:" + v] += 1
    print(name, field, dict(c))

# visits
print("LB VISIT", Counter(r["VISIT"] for r in lb))
print("EX VISIT", Counter(r["VISIT"] for r in ex))

# json replies keys sample
sr = json.loads(Path(r"D:\vit\atlas\hackathon-data\responses\site_replies.json").read_text(encoding="utf-8"))
md = json.loads(Path(r"D:\vit\atlas\hackathon-data\responses\monitor_decisions.json").read_text(encoding="utf-8"))
print("site_replies keys", list(sr.keys()))
print("n replies", len(sr.get("replies", {})))
print("monitor keys", list(md.keys()))
print("n decisions", len(md.get("decisions", {})))
codes = Counter(k.split("|")[0] for k in md.get("decisions", {}))
print("finding codes", dict(codes))
print("decision outcomes", Counter(v[0] for v in md.get("decisions", {}).values()))
