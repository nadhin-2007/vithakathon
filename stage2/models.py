# stage2/models.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

try:
    from starter.schemas import RecordRef
except ImportError:
    from schemas import RecordRef


@dataclass
class Finding:
    code: str
    category: str  # 'safety', 'data_quality', 'compliance', 'site'
    usubjid: Optional[str] = None
    site_id: Optional[str] = None
    severity: str = 'MEDIUM'  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    summary: str = ''
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    cut: int = 1
    protocol_version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EscalationDraft:
    id: str
    code: str
    usubjid: Optional[str]
    site_id: Optional[str]
    severity: str
    summary: str
    evidence: List[Dict[str, Any]]
    alternatives: List[str]
    clarification_requested: Optional[str] = None
    clarification_response: Optional[str] = None
    decision: Optional[str] = None  # 'APPROVED', 'REJECTED', 'CLARIFY'
    decision_reason: Optional[str] = None
    status: str = 'PENDING'  # 'PENDING', 'APPROVED', 'REJECTED', 'MONITORING'
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Query:
    id: str
    usubjid: str
    domain: str
    seq: Union[int, str]
    cut: int
    text: str
    status: str = 'OPEN'  # 'OPEN', 'CLOSED', 'ANSWERED'
    response: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolDeviation:
    id: str
    usubjid: str
    site_id: str
    category: str  # 'visit_window', 'prohibited_medication', 'eligibility', 'renal_exclusion', 'dose'
    description: str
    protocol_version: int
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceEntry:
    node: str
    action: str
    text: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    subject: Optional[str] = None
    site: Optional[str] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    protocol_version: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.node:<15} {self.text}"


@dataclass
class ReviewReport:
    cut: int
    protocol_version: int
    findings_summary: Dict[str, int]
    escalations: List[Dict[str, Any]]
    queries: List[Dict[str, Any]]
    deviations: List[Dict[str, Any]]
    site_flags: Dict[str, Any]
    monitoring_only: List[Dict[str, Any]]
    trace: List[str]
    trace_entries: List[Dict[str, Any]]
    execution_status: str = 'COMPLETE'
    build_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
