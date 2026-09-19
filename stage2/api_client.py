# stage2/api_client.py
from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from stage2.models import EscalationDraft, Query


class ReviewApiClient:
    """
    Client for interacting with the Trial Hub and Gateway.
    Implements GET /documents/protocol, POST /queries, and POST /escalations.
    Falls back gracefully to local responses (site_replies.json, monitor_decisions.json)
    when network is unavailable or running in standalone offline mode.
    """

    def __init__(
        self,
        hub_url: Optional[str] = None,
        gateway_url: Optional[str] = None,
        team_key: str = "",
        data_dir: str = "hackathon-data",
    ):
        self.hub_url = (hub_url or "").rstrip("/")
        self.gateway_url = (gateway_url or "").rstrip("/")
        self.team_key = team_key or "ATLAS_TEAM_KEY"
        self.data_dir = data_dir

        self._query_counter = 1
        self._escalation_counter = 1

        self.site_replies: Dict[str, Any] = {}
        self.monitor_decisions: Dict[str, Any] = {}
        self._server_reachable: Optional[bool] = None
        self._load_local_responses()

    def _load_local_responses(self):
        resp_dir = os.path.join(self.data_dir, "responses")
        if not os.path.exists(resp_dir):
            alt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hackathon-data", "responses")
            if os.path.exists(alt_dir):
                resp_dir = alt_dir

        sr_path = os.path.join(resp_dir, "site_replies.json")
        if os.path.exists(sr_path):
            try:
                with open(sr_path, "r", encoding="utf-8") as f:
                    self.site_replies = json.load(f)
            except Exception:
                pass

        md_path = os.path.join(resp_dir, "monitor_decisions.json")
        if os.path.exists(md_path):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    self.monitor_decisions = json.load(f)
            except Exception:
                pass

    def _http_request(self, base_url: str, endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not base_url or not base_url.startswith("http"):
            return None
        if self._server_reachable is False:
            return None

        url = f"{base_url}/{endpoint.lstrip('/')}"
        headers = {
            "X-Team-Key": self.team_key,
            "Content-Type": "application/json",
            "User-Agent": "Atlas-ReviewCrew/2.0",
        }
        data_bytes = json.dumps(payload).encode("utf-8") if payload else None

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if 200 <= resp.status < 300:
                    self._server_reachable = True
                    resp_text = resp.read().decode("utf-8")
                    return json.loads(resp_text)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            self._server_reachable = False
            return None
        except Exception:
            return None
        return None

    # 1. GET /documents/protocol
    def get_protocol(self, version: int = 1) -> Dict[str, Any]:
        res = self._http_request(self.gateway_url or self.hub_url, f"documents/protocol?version={version}", method="GET")
        if res:
            return res

        # Fallback to local documents
        doc_path = os.path.join(self.data_dir, "documents", f"protocol_v{version}.md")
        if os.path.exists(doc_path):
            with open(doc_path, "r", encoding="utf-8") as f:
                return {"version": version, "content": f.read()}
        return {"version": version, "content": f"STUDY-042 Clinical Study Protocol — Version {version}"}

    # 2. POST /queries
    def post_query(self, query: Query) -> Dict[str, Any]:
        payload = {
            "usubjid": query.usubjid,
            "domain": query.domain,
            "seq": query.seq,
            "cut": query.cut,
            "text": query.text,
        }
        res = self._http_request(self.gateway_url or self.hub_url, "queries", method="POST", payload=payload)
        if res and "status" in res:
            return res

        # Fallback to site_replies.json
        qid = f"Q-{self._query_counter:04d}"
        self._query_counter += 1

        lookup_key = f"{query.domain}|{query.usubjid}|{query.seq}"
        replies_dict = self.site_replies.get("replies", {})
        if lookup_key in replies_dict:
            status, text = replies_dict[lookup_key]
            return {"id": qid, "status": status, "response": text}

        # Check default fallback
        default_reply = self.site_replies.get("_default", ["ANSWERED", "Data verified against source documents. No change."])
        return {"id": qid, "status": default_reply[0], "response": default_reply[1]}

    # 3. POST /escalations
    def post_escalation(self, escalation: EscalationDraft) -> Dict[str, Any]:
        payload = {
            "code": escalation.code,
            "usubjid": escalation.usubjid,
            "severity": escalation.severity,
            "summary": escalation.summary,
            "evidence": escalation.evidence,
            "alternatives": escalation.alternatives,
        }
        if escalation.clarification_response:
            payload["clarification_response"] = escalation.clarification_response

        res = self._http_request(self.gateway_url or self.hub_url, "escalations", method="POST", payload=payload)
        if res and "decision" in res:
            return res

        # Fallback to monitor_decisions.json
        eid = escalation.id or f"E-{self._escalation_counter:04d}"
        self._escalation_counter += 1

        # If this is a clarification resubmission, monitor accepts the clarified data
        if escalation.clarification_response:
            return {
                "id": eid,
                "decision": "APPROVED",
                "reason": f"Clarification accepted: {escalation.clarification_response}. Action approved.",
            }

        lookup_key = f"{escalation.code}|{escalation.usubjid or ''}"
        decisions_dict = self.monitor_decisions.get("decisions", {})

        if lookup_key in decisions_dict:
            decision, reason = decisions_dict[lookup_key]
            return {"id": eid, "decision": decision, "reason": reason}

        # Check by site if code matches site level
        if escalation.site_id:
            site_key = f"{escalation.code}|{escalation.site_id}"
            if site_key in decisions_dict:
                decision, reason = decisions_dict[site_key]
                return {"id": eid, "decision": decision, "reason": reason}

        return {
            "id": eid,
            "decision": "APPROVED",
            "reason": "Medical monitor confirmed finding and approved escalation.",
        }
