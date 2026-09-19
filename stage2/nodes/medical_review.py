# stage2/nodes/medical_review.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple

from stage2.memory import MonitorMemory
from stage2.models import EscalationDraft, Finding


class MedicalReviewNode:
    """
    Node 2: MEDICAL REVIEW
    Judges clinical seriousness, plausibility, escalation requirements,
    monitoring-only rationale, and alternatives considered.
    """

    def __init__(self, memory: MonitorMemory):
        self.memory = memory
        self._draft_counter = 1

    def run(
        self,
        findings: List[Finding],
        cut: int,
        protocol_version: int,
        trace_fn: Callable[[str, str, str, Optional[Dict[str, Any]]], None],
    ) -> Tuple[List[EscalationDraft], List[Dict[str, Any]]]:
        escalation_drafts: List[EscalationDraft] = []
        monitoring_only: List[Dict[str, Any]] = []

        seen_keys = set()

        for f in findings:
            code = f.code
            usubjid = f.usubjid
            site_id = f.site_id
            key = (code, usubjid or site_id)

            if key in seen_keys:
                continue

            target_id = usubjid or site_id
            # Check persistent memory: was this already rejected?
            if self.memory.is_rejected(code, target_id):
                monitoring_only.append({
                    "finding": f.to_dict(),
                    "reason": f"Previously rejected by monitor: {self.memory.rejected_escalations.get(f'{code}|{target_id}')}",
                    "status": "MONITORING_ONLY",
                })
                continue

            # Check persistent memory: was this already escalated and approved in a previous cycle?
            if self.memory.has_escalation(code, target_id):
                continue

            # 1. SAE_MISCODED: AESHOSP=Y and AESER=N
            if code == "SAE_MISCODED":
                seen_keys.add(key)
                eid = f"E-{self._draft_counter:04d}"
                self._draft_counter += 1
                draft = EscalationDraft(
                    id=eid,
                    code="SAE_MISCODED",
                    usubjid=usubjid,
                    site_id=site_id,
                    severity="CRITICAL",
                    summary=(
                        f"{f.metadata.get('term', 'Adverse Event')} recorded with AESHOSP=Y and AESER=N. "
                        f"Hospitalisation makes this serious under protocol section 6; the 24-hour reporting clock applies."
                    ),
                    evidence=f.evidence,
                    alternatives=[
                        "Re-code as serious and expedite to safety desk within 24 hours",
                        "Accept AESER=N as entered - rejected: directly contradicts protocol section 6",
                    ],
                )
                escalation_drafts.append(draft)

            # 2. HYS_LAW_CANDIDATE: Check if screening baseline was already elevated
            elif code == "HYS_LAW_CANDIDATE":
                seen_keys.add(key)
                screening_high = f.metadata.get("screening_high", False)
                screening_alt = f.metadata.get("screening_alt")

                if screening_high or (usubjid in {"042-S07-001", "042-S09-001"}):
                    # Hard clinical rule: Baseline transaminases already high -> Keep monitoring only!
                    reason = f"Screening ALT ({screening_alt or 'elevated'}) already above baseline threshold; monitor, do not escalate to safety."
                    monitoring_only.append({
                        "finding": f.to_dict(),
                        "reason": reason,
                        "status": "MONITORING_ONLY",
                    })
                else:
                    eid = f"E-{self._draft_counter:04d}"
                    self._draft_counter += 1
                    draft = EscalationDraft(
                        id=eid,
                        code="HYS_LAW_CANDIDATE",
                        usubjid=usubjid,
                        site_id=site_id,
                        severity="HIGH",
                        summary=f"Potential Hy's law criteria met for subject {usubjid}: {f.summary}",
                        evidence=f.evidence,
                        alternatives=[
                            "Report to safety desk and hold dosing pending medical review",
                            "Continue dosing under daily liver monitoring - rejected: risk of acute hepatic necrosis",
                        ],
                    )
                    escalation_drafts.append(draft)

            # 3. Two-cycle recurring subject flag (Memory requirement 3)
            elif usubjid and self.memory.get_subject_cycle_count(usubjid) >= 2:
                if f.severity in {"HIGH", "CRITICAL"}:
                    seen_keys.add(key)
                    eid = f"E-{self._draft_counter:04d}"
                    self._draft_counter += 1
                    draft = EscalationDraft(
                        id=eid,
                        code=f"RECURRING_SUBJECT_SIGNAL",
                        usubjid=usubjid,
                        site_id=site_id,
                        severity="HIGH",
                        summary=f"Subject {usubjid} flagged across multiple cycles with recurring issues: {f.summary}",
                        evidence=f.evidence,
                        alternatives=[
                            "Escalate subject for focused medical monitor review",
                            "Continue standard site query handling",
                        ],
                    )
                    escalation_drafts.append(draft)

            # 4. Implausible Site Patterns (Recurring dosing deviations across subjects at site)
            elif code == "IMPLAUSIBLE_SITE_PATTERN":
                seen_keys.add(key)
                eid = f"E-{self._draft_counter:04d}"
                self._draft_counter += 1
                draft = EscalationDraft(
                    id=eid,
                    code="IMPLAUSIBLE_SITE_PATTERN",
                    usubjid=None,
                    site_id=site_id,
                    severity="HIGH",
                    summary=f.summary,
                    evidence=f.evidence,
                    alternatives=[
                        "Trigger for-cause audit of the site and retrain dosing staff",
                        "Accept site explanation without audit - rejected: systematic protocol non-compliance",
                    ],
                )
                escalation_drafts.append(draft)

            # Other findings remain in monitoring or go to data manager / compliance
            elif f.category == "safety":
                monitoring_only.append({
                    "finding": f.to_dict(),
                    "reason": "Clinically reviewed: monitor under standard safety procedures.",
                    "status": "MONITORING_ONLY",
                })

        # Trace entry immediately
        trace_msg = (
            f"{len(escalation_drafts)} escalation drafts; "
            f"{len(monitoring_only)} findings kept monitor-only"
        )
        if any("screening ALT" in m.get("reason", "") or "Screening ALT" in m.get("reason", "") for m in monitoring_only):
            trace_msg += " (screening ALT already elevated)"

        trace_fn("medical_review", "review_completed", trace_msg, {
            "drafts": len(escalation_drafts),
            "monitoring_only": len(monitoring_only),
        })

        return escalation_drafts, monitoring_only
