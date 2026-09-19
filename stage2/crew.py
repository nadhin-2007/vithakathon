# stage2/crew.py
from __future__ import annotations
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from stage1.atlas import Atlas
from stage2.api_client import ReviewApiClient
from stage2.memory import MonitorMemory
from stage2.models import ReviewReport, TraceEntry
from stage2.nodes.compliance import ComplianceNode
from stage2.nodes.data_manager import DataManagerNode
from stage2.nodes.detect import DetectNode
from stage2.nodes.execute import ExecuteNode
from stage2.nodes.human_gate import HumanGateNode
from stage2.nodes.medical_review import MedicalReviewNode


class ReviewCrew:
    """
    Multi-agent Clinical-Trial Review Crew for Stage 2 MONITOR.
    Orchestrates the six-node pipeline in strict logical order:
    DETECT -> MEDICAL REVIEW -> DATA MANAGER -> COMPLIANCE -> HUMAN GATE -> EXECUTE
    """

    def __init__(
        self,
        hub_url: Optional[str] = None,
        gateway_url: Optional[str] = None,
        team_key: str = "",
        atlas: Optional[Atlas] = None,
        memory_storage_path: str = "stage2_memory.json",
        memory_path: Optional[str] = None,
    ):
        self.hub_url = hub_url or ""
        self.gateway_url = gateway_url or ""
        self.team_key = team_key or "ATLAS_MONITOR_TEAM"
        self.atlas = atlas

        storage_path = memory_path or memory_storage_path
        data_dir = getattr(self.atlas.graph, "data_dir", "hackathon-data") if (self.atlas and hasattr(self.atlas, "graph")) else "hackathon-data"
        self.memory = MonitorMemory(storage_path=storage_path)
        self.api_client = ReviewApiClient(
            hub_url=self.hub_url,
            gateway_url=self.gateway_url,
            team_key=self.team_key,
            data_dir=data_dir,
        )

        # Initialize the six nodes
        self.node_detect = DetectNode(self.atlas)
        self.node_medical_review = MedicalReviewNode(self.memory)
        self.node_data_manager = DataManagerNode(self.api_client, self.memory)
        self.node_compliance = ComplianceNode(self.memory)
        self.node_human_gate = HumanGateNode(self.api_client, self.memory, self.atlas)
        self.node_execute = ExecuteNode(self.memory)

    def run_cycle(self, cut: int, protocol_version: Optional[int] = None) -> ReviewReport:
        t0 = time.perf_counter()

        # If protocol_version not explicitly given, derive from cut in StudyGraph
        if protocol_version is None:
            protocol_version = self.atlas.graph._protocol_version_for_cut(cut)

        trace_history: List[str] = []
        trace_entries: List[Dict[str, Any]] = []

        def trace_fn(node: str, action: str, text: str, details: Optional[Dict[str, Any]] = None):
            line = f"{node:<15} {text}"
            trace_history.append(line)
            entry = TraceEntry(
                node=node,
                action=action,
                text=text,
                protocol_version=protocol_version,
            )
            trace_entries.append(entry.to_dict())
            print(line)

        # -----------------------------------------------------------------
        # 1. DETECT
        # -----------------------------------------------------------------
        findings = self.node_detect.run(cut, protocol_version, trace_fn)

        # -----------------------------------------------------------------
        # 2. MEDICAL REVIEW
        # -----------------------------------------------------------------
        escalations, monitoring_only = self.node_medical_review.run(findings, cut, protocol_version, trace_fn)

        # -----------------------------------------------------------------
        # 3. DATA MANAGER
        # -----------------------------------------------------------------
        queries = self.node_data_manager.run(findings, cut, trace_fn)

        # -----------------------------------------------------------------
        # 4. COMPLIANCE
        # -----------------------------------------------------------------
        deviations, site_escalations = self.node_compliance.run(findings, cut, protocol_version, trace_fn)
        # Site-level escalations join the queue for medical monitor decision
        escalations.extend(site_escalations)

        # -----------------------------------------------------------------
        # 5. HUMAN GATE
        # -----------------------------------------------------------------
        final_escalations = self.node_human_gate.run(escalations, cut, protocol_version, trace_fn)

        # -----------------------------------------------------------------
        # 6. EXECUTE
        # -----------------------------------------------------------------
        build_s = time.perf_counter() - t0
        report = self.node_execute.run(
            cut=cut,
            protocol_version=protocol_version,
            findings=findings,
            escalations=final_escalations,
            queries=queries,
            deviations=deviations,
            monitoring_only=monitoring_only,
            trace_history=trace_history,
            trace_entries=trace_entries,
            trace_fn=trace_fn,
            build_s=build_s,
        )

        return report
