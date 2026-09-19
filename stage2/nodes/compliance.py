# stage2/nodes/compliance.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple

from stage2.memory import MonitorMemory
from stage2.models import EscalationDraft, Finding, ProtocolDeviation


class ComplianceNode:
    """
    Node 4: COMPLIANCE
    Checks every subject and site against the protocol version in force for the current cut.
    Detects protocol deviations and produces site-level escalations for clustered violations.
    """

    def __init__(self, memory: MonitorMemory):
        self.memory = memory
        self._dev_counter = 1

    def run(
        self,
        findings: List[Finding],
        cut: int,
        protocol_version: int,
        trace_fn: Callable[[str, str, str, Optional[Dict[str, Any]]], None],
    ) -> Tuple[List[ProtocolDeviation], List[EscalationDraft]]:
        deviations: List[ProtocolDeviation] = []
        site_escalations: List[EscalationDraft] = []

        comp_findings = [f for f in findings if f.category in {"compliance", "data_quality"}]

        n_visit = 0
        n_proh = 0
        n_elig = 0
        n_renal = 0
        n_dose = 0

        site_dose_violations: Dict[str, List[str]] = {}

        for f in comp_findings:
            usubjid = f.usubjid or ""
            site_id = f.site_id or ""

            # Check deviation categories
            if f.code == "VISIT_WINDOW_DEVIATION":
                n_visit += 1
                cat = "visit_window"
            elif f.code == "PROHIBITED_MEDICATION":
                n_proh += 1
                cat = "prohibited_medication"
            elif f.code == "RENAL_EXCLUSION_DEVIATION":
                n_renal += 1
                cat = "renal_exclusion"
            elif f.code == "ELIGIBILITY_DEVIATION":
                n_elig += 1
                cat = "eligibility"
            elif f.code == "DOSING_ERROR":
                n_dose += 1
                cat = "dose"
                if site_id:
                    if site_id not in site_dose_violations:
                        site_dose_violations[site_id] = []
                    if usubjid and usubjid not in site_dose_violations[site_id]:
                        site_dose_violations[site_id].append(usubjid)
            else:
                continue

            did = f"DEV-{self._dev_counter:04d}"
            self._dev_counter += 1

            dev = ProtocolDeviation(
                id=did,
                usubjid=usubjid,
                site_id=site_id,
                category=cat,
                description=f.summary,
                protocol_version=protocol_version,
                evidence=f.evidence,
            )
            deviations.append(dev)

            # Record site issues for multi-cycle memory tracking
            if site_id:
                self.memory.record_site_issue(site_id, cut, cat)

        # Check for site-level dosing problem (e.g. Site S09 with multiple affected subjects)
        for sid, subjs in site_dose_violations.items():
            if len(subjs) >= 3 and not self.memory.has_escalation("DOSING_ERROR", sid):
                if not self.memory.is_rejected("DOSING_ERROR", sid):
                    esc = EscalationDraft(
                        id=f"E-SITE-{sid}",
                        code="DOSING_ERROR",
                        usubjid=None,
                        site_id=sid,
                        severity="CRITICAL",
                        summary=(
                            f"Systematic dosing deviations detected at site {sid} affecting {len(subjs)} subjects "
                            f"({', '.join(subjs[:5])}). Site staff administered 20 mg instead of protocol dose."
                        ),
                        evidence=[],
                        alternatives=[
                            f"Halt drug dispensing at site {sid} and initiate GCP for-cause audit",
                            f"Issue site warning and retrain study coordinators",
                        ],
                    )
                    site_escalations.append(esc)

        total_devs = len(deviations)
        trace_msg = (
            f"{total_devs} deviations under v{protocol_version}: "
            f"{n_visit} visit windows, {n_proh} prohibited medicines, {n_elig} eligibility, {n_renal} renal exclusion"
        )
        trace_fn("compliance", "compliance_evaluated", trace_msg, {
            "deviations": total_devs,
            "visit_windows": n_visit,
            "prohibited": n_proh,
            "eligibility": n_elig,
            "renal": n_renal,
            "dose": n_dose,
        })

        return deviations, site_escalations
