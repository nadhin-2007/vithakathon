# stage2/server.py
"""
Interactive Clinical Trial Monitoring Dashboard & Web Server.
Pure Python standard library implementation (no external dependencies required).

Provides:
- Web UI for judges and clinical monitors
- Live cycle execution control (Cuts 1-6, Protocol Versions 1-3)
- Real-time Trace console
- Human Gate screen (Approve / Reject / Clarify escalations interactively)
- Deviations & Compliance overview
- Queries & Site Audit Trail
- REST API for programmatic testing
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


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATLAS Stage 2 — Clinical Trial Monitor Cockpit</title>
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
  max-height: 480px;
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
.esc-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

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
    <h1>STUDY-042 MONITOR Crew <span class="badge badge-accent">Stage 2 Live</span></h1>
    <div style="font-size:0.85rem; color:var(--low); margin-top:4px;">
      Multi-agent deterministic clinical review: Detect &bull; Medical Review &bull; Data Manager &bull; Compliance &bull; Human Gate &bull; Execute
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
  <span id="spinner">&#9203; Running crew across 6 nodes...</span>
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
    <div class="stat-value" id="statDuplicates">0</div>
    <div class="stat-label">Duplicates Suppressed</div>
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

<!-- Deviations and Queries Tabs -->
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
    print(f"  STUDY-042 MONITOR Dashboard running at:")
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
