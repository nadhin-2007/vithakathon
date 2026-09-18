from dataclasses import dataclass, field, asdict
from typing import Any, List, Optional, Union

@dataclass
class RecordRef:
    domain: str
    usubjid: Optional[str] = None
    seq: Optional[Union[int, str]] = None
    document: Optional[str] = None
    section: Optional[str] = None

    def to_dict(self) -> dict:
        d = {'domain': self.domain}
        if self.usubjid is not None:
            d['usubjid'] = str(self.usubjid)
        if self.seq is not None:
            try:
                d['seq'] = int(self.seq)
            except (ValueError, TypeError):
                d['seq'] = self.seq
        if self.document is not None:
            d['document'] = str(self.document)
        if self.section is not None:
            d['section'] = str(self.section)
        return d

@dataclass
class Question:
    question_id: str
    text: str
    question_type: Optional[str] = None
    cut: Optional[int] = None
    kind: Optional[str] = None

    def __post_init__(self):
        if self.kind is None and self.question_type is not None:
            self.kind = self.question_type
        elif self.question_type is None and self.kind is not None:
            self.question_type = self.kind

def question_from_mapping(raw: dict) -> Question:
    return Question(
        question_id=str(raw.get("question_id", "")),
        text=str(raw.get("text", "")),
        kind=raw.get("kind"),
        question_type=raw.get("question_type") or raw.get("kind"),
        cut=raw.get("cut"),
    )

@dataclass
class Answer:
    question_id: str
    answer: Any
    text: str
    evidence: List[RecordRef] = field(default_factory=list)
    confidence: float = 1.0
    steps_used: int = 0
    tokens_used: int = 0

    def to_dict(self) -> dict:
        ev_list = []
        for e in self.evidence:
            if isinstance(e, RecordRef):
                ev_list.append(e.to_dict())
            elif isinstance(e, dict):
                ev_list.append(e)
            else:
                ev_list.append(asdict(e))
        return {
            'question_id': self.question_id,
            'answer': self.answer,
            'text': self.text,
            'evidence': ev_list,
            'confidence': round(float(self.confidence), 4),
            'steps_used': int(self.steps_used),
            'tokens_used': int(self.tokens_used),
        }


def question_from_mapping(data: dict) -> Question:
    return Question(
        question_id=str(data.get("question_id") or data.get("id") or ""),
        text=str(data.get("text") or data.get("question") or ""),
        question_type=data.get("question_type") or data.get("kind") or data.get("type"),
        cut=data.get("cut"),
        kind=data.get("kind") or data.get("question_type") or data.get("type"),
    )
