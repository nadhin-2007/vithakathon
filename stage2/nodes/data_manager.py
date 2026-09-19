# stage2/nodes/data_manager.py
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple

from stage2.api_client import ReviewApiClient
from stage2.memory import MonitorMemory
from stage2.models import Finding, Query


class DataManagerNode:
    """
    Node 3: DATA MANAGER
    Converts genuine data-quality findings into actionable, specific,
    record-cited queries via POST /queries. Ensures zero duplicate queries.
    """

    def __init__(self, api_client: ReviewApiClient, memory: MonitorMemory):
        self.api_client = api_client
        self.memory = memory
        self._query_counter = 1

    def run(
        self,
        findings: List[Finding],
        cut: int,
        trace_fn: Callable[[str, str, str, Optional[Dict[str, Any]]], None],
    ) -> List[Query]:
        queries_raised: List[Query] = []
        duplicates_prevented = 0
        confirmed_by_site = 0
        unanswered_by_site = 0

        # Filter for data-quality findings
        dq_findings = [f for f in findings if f.category == "data_quality"]

        seen_in_cycle = set()

        for f in dq_findings:
            if not f.evidence:
                continue

            for ev in f.evidence:
                domain = ev.get("domain", "")
                usubjid = ev.get("usubjid", f.usubjid or "")
                seq = ev.get("seq", 1)
                key = (domain, usubjid, str(seq))

                # Check duplicate prevention
                if key in seen_in_cycle or self.memory.has_query(domain, usubjid, seq):
                    duplicates_prevented += 1
                    continue

                seen_in_cycle.add(key)

                # Craft specific, actionable query text
                if f.code == "PRE_DOSE_AE":
                    term = f.metadata.get("term", "Adverse Event")
                    ae_start = f.metadata.get("ae_start", "")
                    first_dose = f.metadata.get("first_dose", "")
                    text = f"AE '{term}' starts {ae_start}, before first dose {first_dose}. Please verify the AE start date against source and correct or confirm."
                elif f.code == "DOSING_ERROR":
                    dose = f.metadata.get("dose", "")
                    expected = f.metadata.get("expected", "")
                    visit = f.metadata.get("visit", "")
                    text = f"EX record at {visit} shows dose {dose} mg, differing from assigned protocol dose {expected} mg. Please check source worksheet and correct transcription or confirm protocol deviation."
                elif f.code == "DUPLICATE_SUBJECT":
                    dup_of = f.metadata.get("duplicate_of", "another subject")
                    text = f"Subject demographics match {dup_of} (same initials, DOB, and sex). Please verify patient identity against source records to confirm single enrollment compliance."
                elif f.code == "MISSING_EXPOSURE":
                    visit = f.metadata.get("visit", "scheduled visit")
                    text = f"Exposure administration record is missing for {visit}. Please verify dosing log and submit missing entry or confirm non-compliance."
                else:
                    text = f"{f.summary} Please verify against source records and correct or confirm."

                qid = f"Q-{self._query_counter:04d}"
                self._query_counter += 1

                q = Query(
                    id=qid,
                    usubjid=usubjid,
                    domain=domain,
                    seq=seq,
                    cut=cut,
                    text=text,
                )

                # Send via API client (with automatic fallback to site_replies.json)
                resp = self.api_client.post_query(q)
                if resp:
                    q.status = resp.get("status", "ANSWERED")
                    q.response = resp.get("response", "")

                if q.status == "CLOSED":
                    confirmed_by_site += 1
                elif q.status == "ANSWERED":
                    confirmed_by_site += 1
                else:
                    unanswered_by_site += 1

                # Save to persistent memory
                self.memory.record_query(domain, usubjid, seq)
                queries_raised.append(q)

        # Write trace entry immediately
        trace_msg = (
            f"{len(queries_raised)} queries raised "
            f"({confirmed_by_site} confirmed by site, {unanswered_by_site} unanswered); "
            f"{duplicates_prevented} duplicates prevented"
        )
        trace_fn("data_manager", "queries_dispatched", trace_msg, {
            "queries": len(queries_raised),
            "confirmed": confirmed_by_site,
            "unanswered": unanswered_by_site,
            "duplicates_prevented": duplicates_prevented,
        })

        return queries_raised
