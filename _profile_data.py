import csv
from collections import Counter
from pathlib import Path

data = Path(r"D:\vit\atlas\hackathon-data\data")


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


for fn in sorted(data.glob("*.csv")):
    rows = read_csv(fn)
    cols = list(rows[0].keys()) if rows else []
    print("=" * 80)
    print(fn.name, "rows", len(rows), "cols", cols)
    miss = {c: sum(1 for r in rows if (r.get(c) or "").strip() == "") for c in cols}
    print("missing", {k: v for k, v in miss.items() if v})
    seq_col = next((c for c in cols if c.endswith("SEQ") or c.lower() == "seq"), None)
    if "USUBJID" in cols and seq_col:
        keys = [(r["USUBJID"], r[seq_col]) for r in rows]
        print("unique USUBJID+seq", len(set(keys)), "dups", len(keys) - len(set(keys)))
    if "USUBJID" in cols:
        print("n_subjects", len(set(r["USUBJID"] for r in rows)))
    if "cut_available" in cols:
        cuts = Counter(r["cut_available"] for r in rows)
        print("cut_available", dict(sorted(cuts.items(), key=lambda x: int(x[0] or 0))))
    if "corrected_at_cut" in cols:
        n = sum(1 for r in rows if (r.get("corrected_at_cut") or "").strip())
        print("n_corrected_at_cut", n)
