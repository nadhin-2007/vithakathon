import csv
from collections import defaultdict
from pathlib import Path
from statistics import pstdev

data = Path(r"D:\vit\atlas\hackathon-data\data")

def read(n):
    with open(data/n, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

dm=read('DM.csv')
ae=read('AE.csv')
vs=read('VS.csv')
lb=read('LB.csv')
site={r['USUBJID']:r['SITEID'] for r in dm}
ae_c=defaultdict(int)
for r in ae:
    ae_c[site[r['USUBJID']]] += 1
print('AE per site', dict(sorted(ae_c.items())))
n_site=defaultdict(int)
for r in dm:
    n_site[r['SITEID']]+=1
print('n per site', dict(n_site))

# pulse regularity
for sid in sorted(n_site):
    vals=[]
    for r in vs:
        if site.get(r['USUBJID'])==sid and r['VSTESTCD']=='PULSE':
            try:
                vals.append(float(r['VSORRES']))
            except: pass
    if vals:
        print(sid, 'pulse mean', round(sum(vals)/len(vals),2), 'sd', round(pstdev(vals),3), 'n', len(vals), 'uniq', len(set(vals)))
