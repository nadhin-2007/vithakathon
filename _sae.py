import csv
from pathlib import Path
with open(Path(r'D:\vit\atlas\hackathon-data\data\AE.csv'), newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['AESER']=='Y' or r['AESHOSP']=='Y':
            print(r['USUBJID'], r['AESEQ'], r['AETERM'], r['AESEV'], r['AESER'], r['AESHOSP'], r['AESTDTC'])
