# stage2/nodes/execute.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

from stage2.memory import MonitorMemory
from stage2.models import EscalationDraft, Finding, ProtocolDeviation, Query, ReviewReport


class ExecuteNode:
    """
    Node 6: EXECUTE
    Persists updated memory state and compiles the official ReviewReport.
    """

    def __init__(self, memory: MonitorMemory):
        self.memory = memory

    def run(
        self,
        cut: int,
        protocol_version: int,
        findings: List[Finding],
        escalations: List[EscalationDraft],
        queries: List[Query],
        deviations: List[ProtocolDeviation],
        monitoring_only: List[Dict[str, Any]],
        trace_history: List[str],
        trace_entries: List[Dict[str, Any]],
        trace_fn: Callable[[str, str, str, Optional[Dict[str, Any]]], None],
        build_s: float = 0.0,
    ) -> ReviewReport:
        # 1. Update cycle memory
        self.memory.cuts_processed.add(cut)

        # Track subjects flagged in this cut
        for f in findings:
            if f.usubjid:
                self.memory.record_subject_flag(f.usubjid, cut)

        self.memory.save()

        # 2. Compile findings summary
        findings_summary = {
            "total": len(findings),
            "safety": sum(1 for f in findings if f.category == "safety"),
            "data_quality": sum(1 for f in findings if f.category == "data_quality"),
            "compliance": sum(1 for f in findings if f.category == "compliance"),
            "site": sum(1 for f in findings if f.category == "site"),
        }

        # 3. Write final trace entry
        exec_trace = (
            f"cycle complete: {len(findings)} findings, "
            f"{len(escalations)} escalations, {len(queries)} queries, {len(deviations)} deviations"
        )
        trace_fn("execute", "cycle_complete", exec_trace, {
            "findings": len(findings),
            "escalations": len(escalations),
            "queries": len(queries),
            "deviations": len(deviations),
        })

        # 4. Return assembled report
        report = ReviewReport(
            cut=cut,
            protocol_version=protocol_version,
            findings_summary=findings_summary,
            escalations=[e.to_dict() for e in escalations],
            queries=[q.to_dict() for q in queries],
            deviations=[d.to_dict() for d in deviations],
            site_flags=self.memory.get_site_flags(),
            monitoring_only=monitoring_only,
            trace=list(trace_history),
            trace_entries=list(trace_entries),
            execution_status="COMPLETE",
            build_s=round(build_s, 4),
        )

        return report
