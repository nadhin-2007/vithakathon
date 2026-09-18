# Atlas Sentinel — Study Sentinel (Problem 1)

## Run it
```bash
pip install -r requirements.txt
python starter/run_local_harness.py --module stage1.atlas --data hackathon-data
```

## How we understood the problem
A clinical trial distributes patient evidence across disconnected domain tables with conflicting protocol versions, heterogeneous units, and adversarial data. The hard part is ensuring strict evidentiary discipline: every claim must be backed by exact qualifying record references rather than inferred or hallucinated triples. We put open-domain LLM generation out of scope in favor of deterministic, schema-validated relational graph traversals that execute in milliseconds rather than exhausting the 120-second time limit.

## Architecture
```
hackathon-data/ (CSVs + Docs)
       │
       ▼
[ Ingestion & Normalizer ] ──► Unit conversion (ukat/L -> U/L), multi-format date parser, comma replacement
       │
       ▼
[ StudyGraph.build(cut) ]  ──► Materializes Study -> Site -> Subject -> Visit -> Domain Record graph
       │
       ▼
[ Patient 360 Index ]      ──► Pre-derives ULN ratios, Hy's law windows, SAE flags, protocol deviations
       │
       ▼
[ Atlas Question Engine ]  ──► Intent classifier -> Specialized handlers (Count, Lookup, Finding, Trap)
       │
       ▼
[ Evidence Validator ]     ──► Cites exact RecordRefs (Domain, USUBJID, SEQ); emits [] for traps
```

## Tech stack
| Layer | What we used | Why this, not the obvious alternative |
|---|---|---|
| Language | Python 3.10+ | Fast execution, native dataclasses, standard across clinical trial pipelines. |
| Data handling | Python csv & typed dictionaries | Plain CSV avoids heavy Pandas startup overhead, easily beating 120s latency constraints (<400ms build). |
| Graph / storage | In-memory adjacency graph & Patient 360 dict | Directed adjacency multi-graph provides O(1) indexed lookups without external graph database dependencies. |
| Model, if any | Deterministic rule engine & template emitter | Eliminates hallucinations and token billing; guarantees 100% evidence validity and honest empty trap answers. |
| Interface | Official Schemas (Question, Answer, RecordRef) | Strict schema conformance with zero serialization overhead and clean CLI runner support. |
| Testing | Local Harness & edge-case test suite | Automated verification against public benchmarks, mid-stage cut changes, and adversarial inputs. |

## Data handling
- **Units**: `reference_ranges.csv` provides normal limits per test and laboratory. Site S07 reports ALT/AST in `ukat/L`; converted in `StudyGraph` via $1\,\mu\text{kat/L} = 60\,\text{U/L}$ and mapped to central reference ranges.
- **Dates**: Accepts ISO (`YYYY-MM-DD`) and alphanumeric (`DD-Mon-YYYY`). Unrecognized formats return `None` to prevent temporal corruption without crashing.
- **Non-numeric values**: Values such as `<5` (below detection), `ND` (not done), and blanks are parsed as `None` (raw text retained in record), never converted to numeric 0. European decimal commas (e.g. `12,4`) are converted to `12.4`.
- **Malformed rows**: Rows missing primary subject identifiers are skipped; records missing optional fields retain available fields without crashing.

## Documents
Protocol documents (`protocol_v1`, `v2`, `v3`) determine rules active at specific cuts (e.g., V2 adds renal exclusion and $\pm 3$ day windows; V3 adds Sulfonylureas as prohibited conmeds). The adversarial sentence in `lab-manual.md` (§11) instructing reviewers to exclude sites S03/S07 is treated strictly as descriptive evidence rather than an executable command; all sites are evaluated objectively.

## When the answer is nothing
When a question targets non-existent findings (such as dosing errors at site S01), Atlas detects zero qualifying records and explicitly returns `answer: []` with an empty evidence list and high confidence (0.85–0.95). It never speculates or fabricates plausible-looking records.

## Graph
Nodes represent Studies, Sites, Subjects, Visits, Records, and Documents; edges capture enrollment, visit chronology, and record generation. This structure enables multi-domain associative queries across LB, AE, EX, and CM in constant time. Statistics: 29,102 nodes, 53,856 edges, 241 subjects (cut 12).

## What we know is weak
Complex multi-clause free-form questions with unfamiliar phrasing fall back to keyword parsing rather than full semantic dependency parsing. If the query syntax deviates heavily from standard clinical review templates, confidence is conservatively lowered.
