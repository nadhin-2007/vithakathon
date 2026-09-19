# stage2/nodes/detect.py
from __future__ import annotations
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from stage1.atlas import Atlas, parse_date, parse_lab_number, DEFAULT_VISIT_DAYS
from stage2.models import Finding, TraceEntry


class DetectNode:
    """
    Node 1: DETECT
    Uses Stage 1 Atlas unchanged to detect all safety, data-quality,
    compliance, and site-level findings in the requested data cut.
    """

    def __init__(self, atlas: Atlas):
        self.atlas = atlas

    def run(
        self,
        cut: int,
        protocol_version: int,
        trace_fn: Callable[[str, str, str, Optional[Dict[str, Any]]], None],
    ) -> List[Finding]:
        graph = self.atlas.graph
        # Ensure graph is built at this cut
        graph.build(cut=cut)
        if protocol_version and protocol_version != graph.protocol_version:
            graph.protocol_version = protocol_version
            graph._parse_protocol_rules()

        findings: List[Finding] = []

        # 1. Safety Findings: SAE_MISCODED (AESHOSP=Y and AESER=N)
        for usubjid, s_obj in graph.subjects.items():
            site_id = s_obj.siteid
            for rec in s_obj.records.get("AE", []):
                fields = rec.fields
                hosp = (fields.get("AESHOSP") or "").strip().upper() == "Y"
                ser = (fields.get("AESER") or "").strip().upper() == "Y"
                term = fields.get("AETERM", "Adverse Event")
                seq = rec.seq

                if hosp and not ser:
                    # Critical finding: hospitalisation makes event serious under protocol section 6
                    f = Finding(
                        code="SAE_MISCODED",
                        category="safety",
                        usubjid=usubjid,
                        site_id=site_id,
                        severity="CRITICAL",
                        summary=f"'{term}' has AESHOSP=Y but AESER=N. Hospitalisation makes this serious under protocol section 6; 24-hour reporting clock applies.",
                        evidence=[{"domain": "AE", "usubjid": usubjid, "seq": seq}],
                        cut=cut,
                        protocol_version=protocol_version,
                        metadata={"term": term, "aeshosp": "Y", "aeser": "N", "record": fields},
                    )
                    findings.append(f)
                elif ser:
                    f = Finding(
                        code="SAE_REPORTED",
                        category="safety",
                        usubjid=usubjid,
                        site_id=site_id,
                        severity="HIGH",
                        summary=f"Serious adverse event reported: '{term}'.",
                        evidence=[{"domain": "AE", "usubjid": usubjid, "seq": seq}],
                        cut=cut,
                        protocol_version=protocol_version,
                        metadata={"term": term, "aeser": "Y"},
                    )
                    findings.append(f)

        # 2. Safety Findings: Hy's Law candidates
        hl_hits = self.atlas._hys_law_hits()
        for hit in hl_hits:
            usubjid = hit["usubjid"]
            site_id = graph.subjects[usubjid].siteid if usubjid in graph.subjects else ""
            ev_list = [e.to_dict() if hasattr(e, "to_dict") else e for e in hit["evidence"]]

            # Check screening baseline transaminases
            s_obj = graph.subjects.get(usubjid)
            screening_alt = None
            screening_high = False
            if s_obj:
                for lb in s_obj.records.get("LB", []):
                    if (lb.fields.get("VISIT") or "").strip().upper() == "SCREENING":
                        if (lb.fields.get("LBTESTCD") or "").strip().upper() in {"ALT", "AST"}:
                            interpreted = graph._interpret_lab(lb, s_obj)
                            val = interpreted.canonical_value if interpreted.canonical_value is not None else interpreted.value
                            if val is not None:
                                screening_alt = val
                            if interpreted.xuln is not None and interpreted.xuln > 1.5:
                                screening_high = True

            f = Finding(
                code="HYS_LAW_CANDIDATE",
                category="safety",
                usubjid=usubjid,
                site_id=site_id,
                severity="HIGH",
                summary=f"Potential Hy's law criteria met: {hit['summary']}",
                evidence=ev_list,
                cut=cut,
                protocol_version=protocol_version,
                metadata={
                    "screening_alt": screening_alt,
                    "screening_high": screening_high,
                    "summary": hit["summary"],
                },
            )
            findings.append(f)

        # 3. Data Quality Findings: Pre-dose AEs (AESTDTC < RFSTDTC)
        for usubjid, s_obj in graph.subjects.items():
            rfstdtc_str = s_obj.fields.get("RFSTDTC")
            rfstdtc_dt = parse_date(rfstdtc_str) if rfstdtc_str else None
            site_id = s_obj.siteid
            if not rfstdtc_dt:
                continue
            for rec in s_obj.records.get("AE", []):
                ae_start = rec.date
                fields = rec.fields
                if ae_start and ae_start < rfstdtc_dt:
                    term = fields.get("AETERM", "Adverse Event")
                    start_str = fields.get("AESTDTC", "")
                    first_str = rfstdtc_str or str(rfstdtc_dt.date())
                    f = Finding(
                        code="PRE_DOSE_AE",
                        category="data_quality",
                        usubjid=usubjid,
                        site_id=site_id,
                        severity="MEDIUM",
                        summary=f"AE '{term}' starts {start_str}, before first dose {first_str}. Please verify the AE start date against source and correct or confirm.",
                        evidence=[{"domain": "AE", "usubjid": usubjid, "seq": rec.seq}],
                        cut=cut,
                        protocol_version=protocol_version,
                        metadata={"term": term, "ae_start": start_str, "first_dose": first_str},
                    )
                    findings.append(f)

        # 4. Data Quality / Compliance: Dosing errors
        dose_hits = self.atlas._dosing_error_hits()
        for hit in dose_hits:
            rec = hit["record"]
            usubjid = hit["usubjid"]
            site_id = graph.subjects[usubjid].siteid if usubjid in graph.subjects else ""
            fields = rec.fields
            f = Finding(
                code="DOSING_ERROR",
                category="data_quality",
                usubjid=usubjid,
                site_id=site_id,
                severity="HIGH",
                summary=f"Administered dose {hit['dose']} mg differs from scheduled {hit['expected']} mg at {fields.get('VISIT')}.",
                evidence=[{"domain": "EX", "usubjid": usubjid, "seq": rec.seq}],
                cut=cut,
                protocol_version=protocol_version,
                metadata={"dose": hit["dose"], "expected": hit["expected"], "visit": fields.get("VISIT")},
            )
            findings.append(f)

        # 5. Data Quality: Duplicate Subjects (double enrollment)
        dup_hits = self.atlas._q_duplicates(None, "", "list").get("answer", [])
        for dup in dup_hits:
            usubjid = dup if isinstance(dup, str) else dup.get("usubjid", "")
            if not usubjid:
                continue
            site_id = graph.subjects[usubjid].siteid if usubjid in graph.subjects else ""
            f = Finding(
                code="DUPLICATE_SUBJECT",
                category="data_quality",
                usubjid=usubjid,
                site_id=site_id,
                severity="MEDIUM",
                summary=f"Subject confirmed duplicate enrollment matching another subject record.",
                evidence=[{"domain": "DM", "usubjid": usubjid, "seq": 1}],
                cut=cut,
                protocol_version=protocol_version,
                metadata={"usubjid": usubjid},
            )
            findings.append(f)

        # 6. Compliance Findings: Prohibited Concomitant Medications
        proh_hits = self.atlas._prohibited_hits()
        for hit in proh_hits:
            usubjid = hit["usubjid"]
            site_id = graph.subjects[usubjid].siteid if usubjid in graph.subjects else ""
            rec = hit.get("record")
            ev_list = [{"domain": rec.domain, "usubjid": usubjid, "seq": rec.seq}] if rec else []
            rule = hit.get("rule", "Prohibited medication")
            f = Finding(
                code="PROHIBITED_MEDICATION",
                category="compliance",
                usubjid=usubjid,
                site_id=site_id,
                severity="HIGH",
                summary=f"Prohibited concomitant medication taken: {rule}.",
                evidence=ev_list,
                cut=cut,
                protocol_version=protocol_version,
                metadata={"rule": rule},
            )
            findings.append(f)

        # 7. Compliance Findings: Visit window deviations
        win_days = int(graph.rules.get("visit_window_days", 7))
        for subject in graph.subjects.values():
            start = parse_date(subject.fields.get("RFSTDTC"))
            if not start:
                continue
            for visit, dt in subject.visits.items():
                sched = DEFAULT_VISIT_DAYS.get(visit)
                if sched is None:
                    continue
                expected = start + timedelta(days=sched)
                delta = abs((dt - expected).days)
                if delta > win_days:
                    recs = [
                        rec
                        for domain in ("VS", "LB", "EX", "EG")
                        for rec in subject.records.get(domain, [])
                        if rec.visit == visit and rec.date
                    ]
                    ev = [{"domain": recs[0].domain, "usubjid": subject.usubjid, "seq": recs[0].seq}] if recs else []
                    f = Finding(
                        code="VISIT_WINDOW_DEVIATION",
                        category="compliance",
                        usubjid=subject.usubjid,
                        site_id=subject.siteid,
                        severity="LOW",
                        summary=f"Visit {visit} occurred {delta} days from target (limit ±{win_days} days under v{protocol_version}).",
                        evidence=ev,
                        cut=cut,
                        protocol_version=protocol_version,
                        metadata={"visit": visit, "diff_days": delta, "allowed_days": win_days},
                    )
                    findings.append(f)

        # 8. Compliance Findings: Eligibility & Renal Exclusions
        creat_lim = graph.rules.get("creat_excl_mgdl")
        screen_alt_x = float(graph.rules.get("screen_alt_x", 2.0))
        for subject in graph.subjects.values():
            reasons = []
            ev_list = []
            age, _ = parse_lab_number(subject.fields.get("AGE"))
            if age is not None and (age < graph.rules.get("age_min", 18) or age > graph.rules.get("age_max", 75)):
                reasons.append(f"Age {age}")
                if subject.records.get("DM"):
                    ev_list.append({"domain": "DM", "usubjid": subject.usubjid, "seq": 1})
            for lv in graph.lab_values(subject.usubjid):
                if lv.record.visit != "SCREENING":
                    continue
                if lv.test in {"ALT", "AST"} and lv.xuln is not None and lv.xuln > screen_alt_x:
                    reasons.append(f"{lv.test} {lv.xuln:.1f}x ULN")
                    ev_list.append({"domain": "LB", "usubjid": subject.usubjid, "seq": lv.record.seq})
                if creat_lim is not None and lv.test in {"CREAT", "CREATININE"}:
                    cval = lv.canonical_value if lv.canonical_value is not None else lv.value
                    if cval is not None and cval > creat_lim:
                        reasons.append(f"Screening Creatinine {cval} mg/dL > {creat_lim}")
                        ev_list.append({"domain": "LB", "usubjid": subject.usubjid, "seq": lv.record.seq})
            if reasons:
                is_renal = any("Creatinine" in r for r in reasons)
                code_name = "RENAL_EXCLUSION_DEVIATION" if is_renal else "ELIGIBILITY_DEVIATION"
                f = Finding(
                    code=code_name,
                    category="compliance",
                    usubjid=subject.usubjid,
                    site_id=subject.siteid,
                    severity="HIGH" if is_renal else "MEDIUM",
                    summary="; ".join(reasons),
                    evidence=ev_list,
                    cut=cut,
                    protocol_version=protocol_version,
                    metadata={"reasons": reasons},
                )
                findings.append(f)

        # 9. Site-level Patterns: Dosing clustering & Implausible regularity
        site_dosing_count = {}
        for hit in dose_hits:
            u = hit["usubjid"]
            sid = graph.subjects[u].siteid if u in graph.subjects else ""
            if sid:
                site_dosing_count[sid] = site_dosing_count.get(sid, 0) + 1

        for sid, count in site_dosing_count.items():
            if count >= 3:
                f = Finding(
                    code="IMPLAUSIBLE_SITE_PATTERN",
                    category="site",
                    usubjid=None,
                    site_id=sid,
                    severity="HIGH",
                    summary=f"Site {sid} shows recurring dosing errors affecting multiple subjects ({count} dose records with 20 mg).",
                    evidence=[],
                    cut=cut,
                    protocol_version=protocol_version,
                    metadata={"site_id": sid, "affected_records": count},
                )
                findings.append(f)

        # Write trace entry immediately
        n_safety = sum(1 for f in findings if f.category == "safety")
        n_data = sum(1 for f in findings if f.category == "data_quality")
        n_comp = sum(1 for f in findings if f.category == "compliance")
        n_site = sum(1 for f in findings if f.category == "site")
        total = len(findings)

        trace_msg = (
            f"{total} findings under protocol v{protocol_version} - "
            f"safety {n_safety}, data {n_data}, compliance {n_comp}, site {n_site}"
        )
        trace_fn("detect", "findings_detected", trace_msg, {"total": total, "safety": n_safety, "data": n_data, "compliance": n_comp, "site": n_site})

        return findings
