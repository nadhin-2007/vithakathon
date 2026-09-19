# stage2/server.py
"""
Interactive Clinical Trial Monitoring Dashboard & Web Server.
Pure Python standard library implementation (no external dependencies required).

Provides:
- Web UI for judges and clinical monitors
- Live cycle execution control (Cuts 1-6, Protocol Versions 1-3)
- Interactive Study Sentinel Chatbot (ask any clinical question with evidence citations)
- Real-time Trace console
- Human Gate screen (Approve / Reject / Clarify escalations interactively)
- Deviations & Compliance overview
- Queries & Site Audit Trail
- REST API for programmatic testing & chat queries
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from stage1.atlas import Atlas, StudyGraph
from stage2.crew import ReviewCrew
from stage2.models import ReviewReport
from starter.schemas import Question


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATLAS — Clinical Trial Sentinel & Monitor Cockpit</title>
<style>
:root {
  --bg: #0d1117;
  --card: #161b22;
  --border: #30363d;
  --text: #c9d1d9;
  --heading: #f0f6fc;
  --accent: #58a6ff;
  --critical: #f85149;
  --high: #d29922;
  --medium: #e3b341;
  --low: #8b949e;
  --success: #3fb950;
  --user-msg: #1f6feb;
  --bot-msg: #21262d;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding: 24px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 24px;
}
.header h1 {
  font-size: 1.6rem;
  color: var(--heading);
  display: flex;
  align-items: center;
  gap: 12px;
}
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}
.badge-critical { background: rgba(248,81,73,0.2); color: var(--critical); border: 1px solid var(--critical); }
.badge-high { background: rgba(210,153,34,0.2); color: var(--high); border: 1px solid var(--high); }
.badge-success { background: rgba(63,185,80,0.2); color: var(--success); border: 1px solid var(--success); }
.badge-accent { background: rgba(88,166,255,0.2); color: var(--accent); border: 1px solid var(--accent); }

.controls-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}
.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
label { font-size: 0.9rem; font-weight: 500; color: var(--heading); }
select, button {
  background: #21262d;
  color: var(--heading);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}
select:focus, button:focus { outline: none; border-color: var(--accent); }
button.primary {
  background: #238636;
  border-color: rgba(240,246,252,0.1);
  color: white;
  font-weight: 600;
}
button.primary:hover { background: #2ea043; }
button.danger {
  background: #da3633;
  color: white;
  font-weight: 600;
}
button.danger:hover { background: #f85149; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--heading);
}
.stat-label {
  font-size: 0.8rem;
  color: var(--low);
  text-transform: uppercase;
  margin-top: 4px;
}

/* Chatbot Section */
.chat-panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  margin-bottom: 24px;
}
.chat-header {
  padding: 14px 18px;
  background: #1c2128;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  color: var(--heading);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chat-messages {
  padding: 16px;
  height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #0d1117;
}
.chat-bubble {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 0.92rem;
  line-height: 1.5;
  word-wrap: break-word;
}
.chat-bubble.user {
  align-self: flex-end;
  background: var(--user-msg);
  color: white;
  border-bottom-right-radius: 2px;
}
.chat-bubble.bot {
  align-self: flex-start;
  background: var(--bot-msg);
  color: var(--text);
  border: 1px solid var(--border);
  border-bottom-left-radius: 2px;
}
.chat-bubble.bot strong.title {
  color: var(--heading);
  display: block;
  margin-bottom: 4px;
}
.evidence-tag {
  display: inline-block;
  padding: 2px 6px;
  background: rgba(88,166,255,0.15);
  color: var(--accent);
  border-radius: 4px;
  font-size: 0.78rem;
  margin-top: 6px;
  margin-right: 4px;
  font-family: monospace;
}
.meta-tag {
  font-size: 0.78rem;
  color: var(--low);
  margin-top: 6px;
}

.chat-quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px;
  background: #161b22;
  border-top: 1px solid var(--border);
}
.chip {
  background: #21262d;
  color: var(--accent);
  border: 1px solid #30363d;
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}
.chip:hover {
  background: rgba(88,166,255,0.15);
  border-color: var(--accent);
}

.chat-input-bar {
  display: flex;
  padding: 12px 16px;
  background: #1c2128;
  border-top: 1px solid var(--border);
  gap: 12px;
}
.chat-input-bar input {
  flex: 1;
  background: #0d1117;
  color: var(--heading);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 0.92rem;
  outline: none;
}
.chat-input-bar input:focus { border-color: var(--accent); }

.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 24px;
}
@media (max-width: 900px) {
  .main-grid { grid-template-columns: 1fr; }
}

.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.panel-header {
  padding: 14px 18px;
  background: #1c2128;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  color: var(--heading);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-body {
  padding: 16px;
  overflow-y: auto;
  max-height: 440px;
}

/* Trace Terminal */
.trace-log {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.85rem;
  line-height: 1.7;
}
.trace-row {
  display: flex;
  gap: 12px;
  border-bottom: 1px solid rgba(48,54,61,0.4);
  padding: 4px 0;
}
.trace-node {
  font-weight: 600;
  color: var(--accent);
  min-width: 120px;
}
.trace-text { color: var(--text); }

/* Escalation Item */
.esc-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 12px;
  background: #1c2128;
}
.esc-card.critical { border-left: 4px solid var(--critical); }
.esc-card.high { border-left: 4px solid var(--high); }
.esc-title {
  font-weight: 600;
  color: var(--heading);
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.esc-desc { font-size: 0.88rem; margin-bottom: 10px; }

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
th, td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
th {
  background: #1c2128;
  color: var(--heading);
  font-weight: 600;
}
tr:hover { background: rgba(88,166,255,0.05); }

#spinner {
  display: none;
  font-size: 0.9rem;
  color: var(--accent);
}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>STUDY-042 Clinical Trial Sentinel & Monitor <span class="badge badge-accent">Live</span></h1>
    <div style="font-size:0.85rem; color:var(--low); margin-top:4px;">
      Multi-agent deterministic review & evidence-backed question answering (Stage 1 Atlas + Stage 2 Monitor Crew)
    </div>
  </div>
  <div>
    <span class="badge badge-success" id="stateBadge">Ready</span>
  </div>
</div>

<div class="controls-bar">
  <div class="control-group">
    <label for="cutSelect">Data Cut:</label>
    <select id="cutSelect">
      <option value="1">Cut 1 (Protocol v1)</option>
      <option value="2">Cut 2 (Protocol v1)</option>
      <option value="3">Cut 3 (Protocol v1)</option>
      <option value="4">Cut 4 (Protocol v1)</option>
      <option value="5">Cut 5 (Protocol v2)</option>
      <option value="6" selected>Cut 6 (Protocol v2/v3)</option>
    </select>
  </div>

  <div class="control-group">
    <label for="protoSelect">Protocol Version:</label>
    <select id="protoSelect">
      <option value="1">Version 1 (Initial)</option>
      <option value="2" selected>Version 2 (Safety Amendment)</option>
      <option value="3">Version 3 (Visit Windows)</option>
    </select>
  </div>

  <button class="primary" id="runBtn" onclick="runCycle()">&#9654; Run Review Cycle</button>
  <button class="danger" onclick="resetMemory()">&#8635; Reset Memory</button>
  <span id="spinner">&#9203; Executing review crew across 6 nodes...</span>
</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value" id="statFindings">0</div>
    <div class="stat-label">Total Findings</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" id="statEscalations" style="color:var(--critical)">0</div>
    <div class="stat-label">Escalations</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" id="statQueries" style="color:var(--accent)">0</div>
    <div class="stat-label">Site Queries</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" id="statDeviations" style="color:var(--high)">0</div>
    <div class="stat-label">Deviations</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" id="statGraphNodes">29,102</div>
    <div class="stat-label">Study Graph Nodes</div>
  </div>
</div>

<!-- Interactive Chat Assistant -->
<div class="chat-panel">
  <div class="chat-header">
    <span>💬 Interactive Study Sentinel & Question Answering</span>
    <span class="badge badge-accent">Stage 1 + 2 Online</span>
  </div>
  <div class="chat-messages" id="chatMessages">
    <div class="chat-bubble bot">
      <strong class="title">Atlas AI Sentinel:</strong>
      Welcome! You can ask any clinical question about STUDY-042 or enter commands. Every answer is backed by exact record evidence from the study graph without hallucinations.
    </div>
  </div>

  <div class="chat-quick-chips">
    <span style="font-size:0.8rem; color:var(--low); align-self:center;">Quick Prompts:</span>
    <button class="chip" onclick="sendQuickChat('How many subjects discontinued due to an adverse event?')">Discontinued by AE</button>
    <button class="chip" onclick="sendQuickChat('Which subjects are Hy\'s law candidates?')">Hy's Law Candidates</button>
    <button class="chip" onclick="sendQuickChat('Which subjects have dosing errors at site S09?')">Site S09 Dosing Errors</button>
    <button class="chip" onclick="sendQuickChat('Are there any dosing errors at site S01?')">Site S01 Trap Check</button>
    <button class="chip" onclick="sendQuickChat('Which subjects received prohibited concomitant medications?')">Prohibited Conmeds</button>
    <button class="chip" onclick="sendQuickChat('run cycle')">▶ Run Review Cycle</button>
    <button class="chip" onclick="sendQuickChat('status')">Memory Status</button>
  </div>

  <div class="chat-input-bar">
    <input type="text" id="chatInput" placeholder="Ask any question (e.g. 'How many subjects discontinued due to AE?') or type 'run cycle'..." onkeydown="if(event.key==='Enter') sendChat()">
    <button class="primary" id="chatSendBtn" onclick="sendChat()">Send</button>
  </div>
</div>

<div class="main-grid">
  <!-- Human Gate / Escalations Panel -->
  <div class="panel">
    <div class="panel-header">
      <span>&#9878; Human Gate &mdash; Medical Monitor Screen</span>
      <span class="badge badge-critical" id="escBadge">0 Pending</span>
    </div>
    <div class="panel-body" id="escalationsContainer">
      <div style="color:var(--low); text-align:center; padding:40px 0;">No active escalations. Run a cycle to evaluate.</div>
    </div>
  </div>

  <!-- Real-time Trace Log -->
  <div class="panel">
    <div class="panel-header">
      <span>&#9998; Real-time Multi-agent Audit Trace</span>
      <span style="font-size:0.8rem; color:var(--low);" id="traceCount">0 events</span>
    </div>
    <div class="panel-body trace-log" id="traceContainer">
      <div style="color:var(--low); padding:10px;">Pipeline idle. Awaiting cycle trigger...</div>
    </div>
  </div>
</div>

<!-- Deviations Table -->
<div class="panel" style="margin-bottom:24px;">
  <div class="panel-header">
    <span>&#128203; Protocol Deviations by Category</span>
    <span class="badge badge-high" id="devBadge">0 Deviations</span>
  </div>
  <div class="panel-body" style="max-height:350px;">
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Subject</th>
          <th>Site</th>
          <th>Category</th>
          <th>Protocol</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody id="deviationsTable">
        <tr><td colspan="6" style="text-align:center; color:var(--low);">No deviations loaded.</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
// Chat Functionality
async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;

  const chatContainer = document.getElementById('chatMessages');
  const cut = parseInt(document.getElementById('cutSelect').value);
  const proto = parseInt(document.getElementById('protoSelect').value);

  // Append user bubble
  chatContainer.innerHTML += `
    <div class="chat-bubble user">
      ${escapeHtml(msg)}
    </div>
  `;
  input.value = '';
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Append temporary thinking bubble
  const thinkId = 'think_' + Date.now();
  chatContainer.innerHTML += `
    <div class="chat-bubble bot" id="${thinkId}">
      <em style="color:var(--low);">&#9203; Querying Atlas study graph...</em>
    </div>
  `;
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, cut: cut, protocol_version: proto})
    });
    const data = await res.json();
    const thinkElem = document.getElementById(thinkId);
    if (thinkElem) thinkElem.remove();

    let ansHtml = `
      <div class="chat-bubble bot">
        <strong class="title">Atlas Sentinel:</strong>
        <div>${formatText(data.text || JSON.stringify(data.answer))}</div>
    `;

    if (data.evidence && data.evidence.length > 0) {
      ansHtml += `<div style="margin-top:6px;"><strong style="font-size:0.8rem; color:var(--low);">CITED EVIDENCE (${data.evidence.length} records):</strong><br>`;
      ansHtml += data.evidence.slice(0, 10).map(e => `
        <span class="evidence-tag">[${e.domain}] ${e.usubjid || ''} seq ${e.seq || ''}</span>
      `).join('');
      if (data.evidence.length > 10) {
        ansHtml += `<span class="evidence-tag">+${data.evidence.length - 10} more</span>`;
      }
      ansHtml += `</div>`;
    }

    if (data.confidence !== undefined) {
      ansHtml += `
        <div class="meta-tag">
          Confidence: ${(data.confidence * 100).toFixed(0)}% &bull; Steps: ${data.steps || 1}
        </div>
      `;
    }

    ansHtml += `</div>`;
    chatContainer.innerHTML += ansHtml;
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // If a cycle was run via chat, update the rest of the cockpit
    if (data.report) {
      renderReport(data.report);
    }
  } catch (err) {
    const thinkElem = document.getElementById(thinkId);
    if (thinkElem) thinkElem.remove();
    chatContainer.innerHTML += `
      <div class="chat-bubble bot" style="border-color:var(--critical);">
        <strong class="title" style="color:var(--critical);">Error:</strong>
        <div>${escapeHtml(err.message)}</div>
      </div>
    `;
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
}

function sendQuickChat(text) {
  document.getElementById('chatInput').value = text;
  sendChat();
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatText(text) {
  return escapeHtml(text).replace(/\\n/g, '<br>');
}

// Pipeline Execution
async function runCycle() {
  const cut = parseInt(document.getElementById('cutSelect').value);
  const proto = parseInt(document.getElementById('protoSelect').value);
  const btn = document.getElementById('runBtn');
  const spinner = document.getElementById('spinner');

  btn.disabled = true;
  spinner.style.display = 'inline';
  document.getElementById('stateBadge').textContent = 'Processing...';

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cut: cut, protocol_version: proto})
    });
    const data = await res.json();
    renderReport(data);
  } catch (err) {
    alert('Error running cycle: ' + err.message);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    document.getElementById('stateBadge').textContent = 'Completed';
  }
}

async function resetMemory() {
  if (!confirm("Are you sure you want to reset Stage 2 persistent memory?")) return;
  await fetch('/api/reset', {method: 'POST'});
  alert("Memory state reset to clean initial state.");
  location.reload();
}

function renderReport(report) {
  // Stats
  document.getElementById('statFindings').textContent = report.findings_summary?.total || 0;
  document.getElementById('statEscalations').textContent = report.escalations?.length || 0;
  document.getElementById('statQueries').textContent = report.queries?.length || 0;
  document.getElementById('statDeviations').textContent = report.deviations?.length || 0;

  // Escalations
  const escContainer = document.getElementById('escalationsContainer');
  document.getElementById('escBadge').textContent = `${report.escalations?.length || 0} Processed`;
  if (!report.escalations || report.escalations.length === 0) {
    escContainer.innerHTML = '<div style="color:var(--low); text-align:center; padding:40px 0;">Zero new escalations (all resolved or in monitoring).</div>';
  } else {
    escContainer.innerHTML = report.escalations.map(e => `
      <div class="esc-card ${e.severity === 'CRITICAL' ? 'critical' : 'high'}">
        <div class="esc-title">
          <span>${e.code} &bull; ${e.usubjid || e.site_id || 'SITE'}</span>
          <span class="badge ${e.decision === 'APPROVED' ? 'badge-success' : 'badge-critical'}">${e.decision || e.status}</span>
        </div>
        <div class="esc-desc">${e.summary}</div>
        <div style="font-size:0.8rem; color:var(--low); margin-bottom:6px;">
          <strong>Monitor Decision:</strong> ${e.decision_reason || 'Under review'}
        </div>
        ${e.clarification_response ? `<div style="font-size:0.8rem; color:var(--accent); background:#111; padding:6px; border-radius:4px;"><strong>Graph Clarification:</strong> ${e.clarification_response}</div>` : ''}
      </div>
    `).join('');
  }

  // Trace
  const traceContainer = document.getElementById('traceContainer');
  document.getElementById('traceCount').textContent = `${report.trace?.length || 0} events`;
  if (report.trace && report.trace.length > 0) {
    traceContainer.innerHTML = report.trace.map(line => {
      const parts = line.split(/\\s{2,}/);
      const node = parts[0] || 'pipeline';
      const msg = parts.slice(1).join(' ') || line;
      return `
        <div class="trace-row">
          <div class="trace-node">[${node}]</div>
          <div class="trace-text">${msg}</div>
        </div>
      `;
    }).join('');
    traceContainer.scrollTop = traceContainer.scrollHeight;
  }

  // Deviations Table
  const devTable = document.getElementById('deviationsTable');
  document.getElementById('devBadge').textContent = `${report.deviations?.length || 0} Deviations`;
  if (report.deviations && report.deviations.length > 0) {
    devTable.innerHTML = report.deviations.slice(0, 50).map(d => `
      <tr>
        <td><strong>${d.id}</strong></td>
        <td>${d.usubjid || 'N/A'}</td>
        <td>${d.site_id || 'N/A'}</td>
        <td><span class="badge badge-accent">${d.category}</span></td>
        <td>v${d.protocol_version}</td>
        <td>${d.description}</td>
      </tr>
    `).join('');
  }
}
</script>
</body>
</html>
"""


class MonitorServerHandler(BaseHTTPRequestHandler):
    crew: Optional[ReviewCrew] = None
    latest_report: Optional[ReviewReport] = None

    def _set_json_headers(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
            return

        if path == "/api/status":
            self._set_json_headers(200)
            res = {
                "status": "ready",
                "team_key": self.crew.team_key if self.crew else "",
                "cuts_processed": list(self.crew.memory.cuts_processed) if self.crew else [],
                "site_flags": self.crew.memory.get_site_flags() if self.crew else {},
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/report":
            self._set_json_headers(200)
            if self.latest_report:
                self.wfile.write(json.dumps(self.latest_report.to_dict()).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({"status": "no_report_yet"}).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(post_body) if post_body else {}
        except json.JSONDecodeError:
            body = {}

        if path == "/api/run":
            cut = int(body.get("cut", 6))
            protocol_version = int(body.get("protocol_version", 2))

            if self.crew:
                report = self.crew.run_cycle(cut=cut, protocol_version=protocol_version)
                MonitorServerHandler.latest_report = report
                self._set_json_headers(200)
                self.wfile.write(json.dumps(report.to_dict()).encode("utf-8"))
            else:
                self._set_json_headers(500)
                self.wfile.write(json.dumps({"error": "Crew not initialized"}).encode("utf-8"))
            return

        if path == "/api/chat":
            msg = (body.get("message") or "").strip()
            cut = int(body.get("cut", 6))
            protocol_version = int(body.get("protocol_version", 2))

            if not msg:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"error": "Message is required"}).encode("utf-8"))
                return

            lower = msg.lower()

            # Handle direct commands
            if lower in {"run", "run cycle", "run review cycle", "start cycle"}:
                if self.crew:
                    report = self.crew.run_cycle(cut=cut, protocol_version=protocol_version)
                    MonitorServerHandler.latest_report = report
                    reply = {
                        "text": f"✅ Cycle review complete under protocol v{protocol_version} on cut {cut}.\n\n"
                                f"• Findings: {report.findings_summary['total']}\n"
                                f"• Escalations: {len(report.escalations)}\n"
                                f"• Queries: {len(report.queries)}\n"
                                f"• Deviations: {len(report.deviations)}\n"
                                f"• Duplicates suppressed: {len(report.queries) == 0 and len(self.crew.memory.queries_raised) > 0}",
                        "answer": report.findings_summary,
                        "confidence": 1.0,
                        "evidence": [],
                        "steps": 6,
                        "report": report.to_dict(),
                    }
                    self._set_json_headers(200)
                    self.wfile.write(json.dumps(reply).encode("utf-8"))
                    return

            if lower in {"status", "memory", "stats"}:
                if self.crew:
                    reply = {
                        "text": f"📊 System Memory Status:\n"
                                f"• Cuts processed: {list(self.crew.memory.cuts_processed)}\n"
                                f"• Historical queries recorded: {len(self.crew.memory.queries_raised)}\n"
                                f"• Escalations made: {len(self.crew.memory.escalations_made)}\n"
                                f"• Rejections remembered: {len(self.crew.memory.rejected_escalations)}\n"
                                f"• Site flags: {list(self.crew.memory.site_flags.keys()) or 'None'}",
                        "answer": {"cuts": list(self.crew.memory.cuts_processed)},
                        "confidence": 1.0,
                        "evidence": [],
                        "steps": 1,
                    }
                    self._set_json_headers(200)
                    self.wfile.write(json.dumps(reply).encode("utf-8"))
                    return

            # Default: Query Atlas Stage 1 engine
            if self.crew and self.crew.atlas:
                self.crew.atlas.graph.build(cut=cut)
                if protocol_version and protocol_version != self.crew.atlas.graph.protocol_version:
                    self.crew.atlas.graph.protocol_version = protocol_version
                    self.crew.atlas.graph._parse_protocol_rules()

                q = Question(question_id="Q-CHAT", text=msg, cut=cut)
                ans = self.crew.atlas.answer(q)
                ev_list = [e.to_dict() if hasattr(e, "to_dict") else e for e in ans.evidence]
                reply = {
                    "text": ans.text,
                    "answer": ans.answer,
                    "confidence": ans.confidence,
                    "evidence": ev_list,
                    "steps": getattr(ans, "steps_used", getattr(ans, "steps", 1)),
                }
                self._set_json_headers(200)
                self.wfile.write(json.dumps(reply).encode("utf-8"))
            else:
                self._set_json_headers(500)
                self.wfile.write(json.dumps({"error": "Atlas engine not initialized"}).encode("utf-8"))
            return

        if path == "/api/reset":
            if self.crew:
                self.crew.memory.reset()
                MonitorServerHandler.latest_report = None
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"status": "reset_complete"}).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def start_server(port: int = 8080, data_dir: str = "hackathon-data"):
    print(f"Initializing Stage 1 StudyGraph & Atlas from '{data_dir}'...")
    graph = StudyGraph(data_dir)
    atlas = Atlas(graph)

    print("Initializing Stage 2 ReviewCrew...")
    crew = ReviewCrew(
        hub_url="http://127.0.0.1:8000",
        gateway_url="http://127.0.0.1:8001",
        team_key="ATLAS_CREW",
        atlas=atlas,
    )
    MonitorServerHandler.crew = crew

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, MonitorServerHandler)
    print(f"\n========================================================")
    print(f"  STUDY-042 MONITOR Dashboard & Chatbot running at:")
    print(f"  http://127.0.0.1:{port}")
    print(f"========================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATLAS Stage 2 Monitor Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port to serve dashboard on")
    parser.add_argument("--data", type=str, default="hackathon-data", help="Data directory")
    args = parser.parse_args()
    start_server(port=args.port, data_dir=args.data)
