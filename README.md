# ATLAS — Clinical Trial Sentinel & Continuous Study Monitor

## Run Instructions

### Problem 1 — Stage 1 (Study Sentinel & Question Answering)
```bash
pip install -r requirements.txt
python starter/run_local_harness.py --module stage1.atlas --data hackathon-data
```

### Problem 2 — Stage 2 (MONITOR Crew & 12 Verification Tests)
```bash
# Run all 12 Stage 2 validation tests (deterministic, zero external API keys needed):
python -m unittest tests/test_stage2.py

# Launch the interactive Human Gate Cockpit & Audit Trace Web UI:
python -m stage2.server --port 8080
```
Open `http://127.0.0.1:8080` in any browser to review pending escalations, approve/reject/clarify in real time, and view audit traces.

---

## How we understood the problem
Clinical trial monitoring distributes safety, compliance, and demographic evidence across disconnected, asynchronous domain tables with shifting protocol amendments, non-standard units, and adversarial data. The critical challenge is evidentiary and operational discipline: every signal must cite exact source records, queries must never duplicate, and human-in-the-loop decisions (Approved, Rejected, Clarify) must be strictly respected. We rejected open-domain generative LLMs in favor of deterministic, schema-validated multi-agent graphs that run locally in milliseconds without token costs or hallucinations.

---

## Architecture
ATLAS runs two tightly integrated, deterministic stages:

```
STAGE 1 (Study Graph & Sentinel)
hackathon-data/ ──► Normalizer (Units/Dates) ──► StudyGraph ──► Patient360 ──► Question Engine

STAGE 2 (Six-Node MONITOR Review Crew)
StudyGraph ──► 1. DETECT (Safety/Quality/Compliance/Site)
           ──► 2. MEDICAL REVIEW (SAE hospitalisation rule, Hy's baseline, multi-cycle)
           ──► 3. DATA MANAGER (Record-cited queries, deduplication via memory)
           ──► 4. COMPLIANCE (Protocol v1/v2/v3 rules, site dosing clustering)
           ──► 5. HUMAN GATE (Monitor interactive loop: APPROVED / REJECTED / CLARIFY)
           ──► 6. EXECUTE (ReviewReport synthesis & MonitorMemory persistence)
```

1. **Stage 1 (Atlas)** builds an in-memory multidimensional graph (29,102 nodes, 53,856 edges across 241 subjects) with pre-indexed ULN ratios, visit schedules, and adverse event timelines.
2. **Stage 2 (ReviewCrew)** coordinates six nodes in strict sequence per cycle, backed by persistent disk memory (`stage2_memory.json`):
   - **DETECT**: Extracts candidate safety, data-quality, and compliance findings using Stage 1 unchanged.
   - **MEDICAL REVIEW**: Enforces the protocol section 6 hospitalisation rule (`AESHOSP=Y` + `AESER=N` $\to$ critical `SAE_MISCODED`), suppresses false Hy's Law alarms when screening transaminases are pre-elevated, and flags multi-cycle repeat subjects.
   - **DATA MANAGER**: Formulates specific record-cited queries and enforces zero query repetition across identical cuts.
   - **COMPLIANCE**: Dynamically enforces the protocol version in force (e.g. v2 renal exclusion creatinine $> 1.5$ mg/dL) and detects site-level clustered errors (Site S09).
   - **HUMAN GATE**: Evaluates medical monitor responses: confirms `APPROVED`, downgrades `REJECTED` to permanent monitoring, and answers `CLARIFY` by querying the study graph (screening lab baselines, conmeds) and resubmitting.
   - **EXECUTE**: Commits memory state and compiles official `ReviewReport`.

---

## Tech stack
| Layer | What we used | Why this, not the obvious alternative |
|---|---|---|
| Language | Python 3.10+ | Fast execution, native dataclasses, standard across clinical trial pipelines. |
| Data handling | Python csv & typed dictionaries | Plain CSV avoids heavy Pandas startup overhead, executing builds in <400ms. |
| Graph / storage | In-memory adjacency graph & Patient 360 | Directed adjacency multi-graph provides O(1) indexed lookups without external Neo4j/DBMS. |
| State Memory | `MonitorMemory` (Atomic JSON) | Zero database setup; guarantees zero duplicate queries/escalations and survives restarts. |
| Model / Reasoning | Deterministic clinical rule engine | Eliminates LLM hallucinations and latency; guarantees 100% evidence accuracy and zero cost. |
| User Interface | Embedded Single-Page HTML/JS Dashboard | Pure Python standard library `http.server`; runs anywhere with zero `npm`/`pip` dependencies. |
| Testing | Python `unittest` test suite | Standard library test runner verifying all 12 hackathon specifications in ~15s. |

---

## Data handling
- **Units**: Normal ranges loaded from `reference_ranges.csv`. Site S07 reports ALT/AST in `ukat/L`; converted via $1\,\mu\text{kat/L} = 60\,\text{U/L}$ and mapped to central reference ranges.
- **Dates**: Accepts ISO (`YYYY-MM-DD`) and alphanumeric (`DD-Mon-YYYY`, `DD/MM/YYYY`). Unrecognized formats return `None` to prevent temporal corruption without crashing.
- **Non-numeric values**: Strings such as `<5`, `ND` (not done), and blanks are parsed as `None` (preserving raw values in `fields`), never coerced to 0. European decimal commas (`12,4`) are normalized to decimal points (`12.4`).
- **Malformed rows**: Missing primary identifiers are safely skipped; missing optional fields retain available fields without crashing.

---

## Documents
Protocol documents (`protocol_v1`, `v2`, `v3`) define amendment boundaries:
- **Protocol v1**: Initial baseline; $\pm 7$-day visit windows; baseline prohibited medications.
- **Protocol v2**: Safety amendment adding renal exclusion (creatinine $> 1.5$ mg/dL) and tightening eligibility.
- **Protocol v3**: Tightens visit window tolerances to $\pm 3$ days; adds sulfonylureas to prohibited conmeds.
The adversarial sentence in `lab-manual.md` (§11) instructing reviewers to exclude sites S03/S07 is treated strictly as descriptive evidence rather than an executable instruction; all sites are evaluated objectively.

---

## When the answer is nothing
When a query or question targets non-existent clinical findings (e.g. dosing errors at site S01), Atlas identifies zero qualifying records and explicitly returns `answer: []` with an empty evidence list and high confidence (0.85–0.95). It never speculates, extrapolates, or fabricates plausible records.

---

## Graph
Nodes represent Studies, Sites, Subjects, Visits, Records, and Protocol Documents; edges capture enrollment, visit chronology, and record creation. This structure enables multi-domain associative queries across LB, AE, EX, and CM in constant time. Build stats: 29,102 nodes, 53,856 edges, 241 subjects (cut 12).

---

## What we know is weak
Free-form medical queries with novel syntactic phrasing rely on regular expression token mapping rather than deep semantic parsing. On Stage 2, if an external monitor API is unreachable, the system relies on local simulated decision ledgers rather than initiating asynchronous webhook retries.
