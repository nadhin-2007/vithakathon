#!/usr/bin/env python3
"""Local ATLAS harness: build the graph, answer public questions, write artifacts."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starter.schemas import Answer, Question, question_from_mapping


def load_module(dotted: str):
    return importlib.import_module(dotted)


def evidence_exists(graph, evidence) -> bool:
    ok = True
    for item in evidence or []:
        domain = item.domain if hasattr(item, "domain") else item.get("domain")
        if domain == "DOC":
            document = item.document if hasattr(item, "document") else item.get("document")
            if document and document not in graph.documents:
                ok = False
            continue
        usubjid = item.usubjid if hasattr(item, "usubjid") else item.get("usubjid")
        seq = item.seq if hasattr(item, "seq") else item.get("seq")
        if usubjid is None or seq is None:
            ok = False
            continue
        if (domain, usubjid, int(seq)) not in graph.records:
            ok = False
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="stage1.atlas")
    parser.add_argument("--data", default="hackathon-data")
    parser.add_argument("--questions", default=str(ROOT / "starter" / "public_questions.json"))
    parser.add_argument("--out", default="stage1_public.json")
    parser.add_argument("--stats", default="graph_stats.json")
    parser.add_argument("--cut", type=int, default=None)
    args = parser.parse_args(argv)

    mod = load_module(args.module)
    data_dir = args.data
    if not Path(data_dir).exists() and (ROOT / data_dir).exists():
        data_dir = str(ROOT / data_dir)

    graph = mod.StudyGraph(data_dir)
    t0 = time.perf_counter()
    stats = graph.build(args.cut)
    build_s = time.perf_counter() - t0
    Path(args.stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    agent = mod.Atlas(graph)
    results = []
    breaches = 0
    valid_ev = 0
    for raw in questions:
        q = question_from_mapping(raw)
        start = time.perf_counter()
        ans = agent.answer(q)
        elapsed = time.perf_counter() - start
        if elapsed > 120:
            breaches += 1
        if not isinstance(ans, Answer):
            ans = Answer(
                question_id=q.question_id,
                answer=getattr(ans, "answer", None),
                text=getattr(ans, "text", str(ans)),
                evidence=list(getattr(ans, "evidence", []) or []),
                confidence=float(getattr(ans, "confidence", 0) or 0),
                steps_used=int(getattr(ans, "steps_used", 0) or 0),
                tokens_used=int(getattr(ans, "tokens_used", 0) or 0),
            )
        ev_ok = evidence_exists(agent.graph, ans.evidence)
        if ev_ok:
            valid_ev += 1
        dump = ans.to_dict()
        dump["elapsed_s"] = round(elapsed, 4)
        dump["evidence_exists"] = ev_ok
        results.append(dump)
        print(f"{q.question_id} kind={q.kind:7} conf={ans.confidence:.2f} ev={ev_ok} t={elapsed:.3f}s answer={ans.answer!r}"[:220])
        print(f"  {ans.text[:180]}")

    payload = {
        "stats": stats,
        "build_s": round(build_s, 4),
        "n_questions": len(results),
        "evidence_exist_rate": (valid_ev / len(results)) if results else 0,
        "time_breaches": breaches,
        "answers": results,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out} and {args.stats}")
    print(json.dumps({k: payload[k] for k in ("stats", "evidence_exist_rate", "time_breaches")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
