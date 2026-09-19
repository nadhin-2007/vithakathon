# stage2/memory.py
from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple


class MonitorMemory:
    """
    Persistent state surviving between run_cycle calls and application restarts.
    Ensures zero duplicate queries, zero repeated escalations, rejection memory,
    and automatic escalation for multi-cycle flagged subjects/sites.
    """

    def __init__(self, storage_path: str = "stage2_memory.json"):
        self.storage_path = os.path.abspath(storage_path)
        self.queries_raised: Set[Tuple[str, str, str]] = set()  # (domain, usubjid, seq)
        self.escalations_made: Dict[str, Dict[str, Any]] = {}   # "code|usubjid" -> dict
        self.rejected_escalations: Dict[str, str] = {}          # "code|usubjid" -> reason
        self.subject_cycle_flags: Dict[str, List[int]] = {}     # usubjid -> [cut1, cut2]
        self.site_recurring_issues: Dict[str, List[int]] = {}   # site_id -> [cut1, cut2]
        self.cuts_processed: Set[int] = set()
        self.site_flags: Dict[str, Dict[str, Any]] = {}
        self.load()

    def reset(self):
        """Clears memory state and removes persistent file (for fresh test runs)."""
        self.queries_raised.clear()
        self.escalations_made.clear()
        self.rejected_escalations.clear()
        self.subject_cycle_flags.clear()
        self.site_recurring_issues.clear()
        self.cuts_processed.clear()
        self.site_flags.clear()
        if os.path.exists(self.storage_path):
            try:
                os.remove(self.storage_path)
            except OSError:
                pass

    def load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.queries_raised = {tuple(q) for q in data.get("queries_raised", [])}
            self.escalations_made = data.get("escalations_made", {})
            self.rejected_escalations = data.get("rejected_escalations", {})
            self.subject_cycle_flags = data.get("subject_cycle_flags", {})
            self.site_recurring_issues = data.get("site_recurring_issues", {})
            self.cuts_processed = set(data.get("cuts_processed", []))
            self.site_flags = data.get("site_flags", {})
        except Exception:
            pass

    def save(self):
        data = {
            "queries_raised": [list(q) for q in self.queries_raised],
            "escalations_made": self.escalations_made,
            "rejected_escalations": self.rejected_escalations,
            "subject_cycle_flags": self.subject_cycle_flags,
            "site_recurring_issues": self.site_recurring_issues,
            "cuts_processed": sorted(self.cuts_processed),
            "site_flags": self.site_flags,
        }
        dir_name = os.path.dirname(self.storage_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # 1. Queries
    def has_query(self, domain: str, usubjid: str, seq: Any) -> bool:
        return (str(domain).strip().upper(), str(usubjid).strip(), str(seq).strip()) in self.queries_raised

    def record_query(self, domain: str, usubjid: str, seq: Any):
        self.queries_raised.add((str(domain).strip().upper(), str(usubjid).strip(), str(seq).strip()))
        self.save()

    # 2. Escalations
    def _escalation_key(self, code: str, usubjid: Optional[str]) -> str:
        return f"{str(code).strip()}|{str(usubjid or '').strip()}"

    def has_escalation(self, code: str, usubjid: Optional[str]) -> bool:
        return self._escalation_key(code, usubjid) in self.escalations_made

    def is_rejected(self, code: str, usubjid: Optional[str]) -> bool:
        return self._escalation_key(code, usubjid) in self.rejected_escalations

    def record_escalation(self, code: str, usubjid: Optional[str], record: Dict[str, Any]):
        key = self._escalation_key(code, usubjid)
        self.escalations_made[key] = record
        if record.get("decision") == "REJECTED":
            self.rejected_escalations[key] = record.get("reason", "Rejected by monitor")
        self.save()

    # 3. Multi-cycle Subject Tracking
    def record_subject_flag(self, usubjid: str, cut: int) -> int:
        u = str(usubjid).strip()
        if u not in self.subject_cycle_flags:
            self.subject_cycle_flags[u] = []
        if cut not in self.subject_cycle_flags[u]:
            self.subject_cycle_flags[u].append(cut)
            self.save()
        return len(self.subject_cycle_flags[u])

    def get_subject_cycle_count(self, usubjid: str) -> int:
        return len(self.subject_cycle_flags.get(str(usubjid).strip(), []))

    # 4. Multi-cycle Site Tracking
    def record_site_issue(self, site_id: str, cut: int, issue_type: str = "general") -> int:
        s = str(site_id).strip()
        if s not in self.site_recurring_issues:
            self.site_recurring_issues[s] = []
        if cut not in self.site_recurring_issues[s]:
            self.site_recurring_issues[s].append(cut)
        if len(self.site_recurring_issues[s]) >= 2:
            self.site_flags[s] = {
                "site_id": s,
                "status": "RECURRING_PROBLEMS",
                "cycles_affected": list(self.site_recurring_issues[s]),
                "reason": f"Site {s} accumulated violations across cycles {self.site_recurring_issues[s]}"
            }
        self.save()
        return len(self.site_recurring_issues[s])

    def get_site_flags(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.site_flags)
