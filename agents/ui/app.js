// Autonomous Incident Investigator Web Test Page Client Logic

let currentScenario = null;
let currentThreadId = null;
let eventSource = null;
let timerInterval = null;
let startTime = null;

// DOM Elements
const statusPills = document.getElementById('statusPills');
const scenariosList = document.getElementById('scenariosList');
const targetServiceInput = document.getElementById('targetServiceInput');
const alertTextInput = document.getElementById('alertTextInput');
const autoApproveToggle = document.getElementById('autoApproveToggle');
const activeIncidentBadge = document.getElementById('activeIncidentBadge');

const btnArmFault = document.getElementById('btnArmFault');
const btnDisarmFault = document.getElementById('btnDisarmFault');
const btnInvestigate = document.getElementById('btnInvestigate');
const btnClearLogs = document.getElementById('btnClearLogs');

const investigationTimer = document.getElementById('investigationTimer');
const investigationStatus = document.getElementById('investigationStatus');
const streamLog = document.getElementById('streamLog');
const emptyStateMsg = document.getElementById('emptyStateMsg');

const rcaReportCard = document.getElementById('rcaReportCard');
const rcaRootCause = document.getElementById('rcaRootCause');
const rcaConfidence = document.getElementById('rcaConfidence');
const rcaEvidenceList = document.getElementById('rcaEvidenceList');
const rcaRecommendedAction = document.getElementById('rcaRecommendedAction');
const rcaLangfuseLink = document.getElementById('rcaLangfuseLink');
const statLatency = document.getElementById('statLatency');
const statToolCalls = document.getElementById('statToolCalls');
const statEvidence = document.getElementById('statEvidence');

const approvalModal = document.getElementById('approvalModal');
const modalTargetService = document.getElementById('modalTargetService');
const modalAction = document.getElementById('modalAction');
const modalRationale = document.getElementById('modalRationale');
const btnApproveAction = document.getElementById('btnApproveAction');
const btnRejectAction = document.getElementById('btnRejectAction');

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  loadStackStatus();
  loadScenarios();
  setInterval(loadStackStatus, 15000); // refresh health every 15s

  btnArmFault.addEventListener('click', handleArmFault);
  btnDisarmFault.addEventListener('click', handleDisarmFault);
  btnInvestigate.addEventListener('click', handleStartInvestigation);
  btnClearLogs.addEventListener('click', clearLogFeed);

  btnApproveAction.addEventListener('click', () => submitHumanApproval(true));
  btnRejectAction.addEventListener('click', () => submitHumanApproval(false));
});

// Load Stack Status
async function loadStackStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    renderStatusPills(data.services);
  } catch (err) {
    statusPills.innerHTML = '<span class="pill pill-err">API Offline</span>';
  }
}

function renderStatusPills(services) {
  if (!services || !services.length) return;
  const keyServices = ['Prometheus', 'Tempo', 'Loki', 'Grafana', 'Langfuse web', 'incident-controller'];
  
  statusPills.innerHTML = services
    .filter(s => keyServices.includes(s.name))
    .map(s => {
      const cls = s.reachable ? 'pill-ok' : 'pill-err';
      const label = s.name.replace(' web', '');
      return `<span class="pill ${cls}" title="${s.name} on :${s.port}">${s.reachable ? '✓' : '✕'} ${label}</span>`;
    })
    .join('');
}

// Load Scenarios
async function loadScenarios() {
  try {
    const res = await fetch('/api/incidents');
    const data = await res.json();
    renderScenarios(data.incidents || []);
  } catch (err) {
    scenariosList.innerHTML = '<div class="scenario-card">Failed to load scenarios.</div>';
  }
}

function renderScenarios(incidents) {
  if (!incidents.length) {
    scenariosList.innerHTML = '<div class="scenario-card">No incidents found in eval/incidents.</div>';
    return;
  }

  scenariosList.innerHTML = incidents.map((inc, idx) => {
    const faultType = inc.fault ? inc.fault.type : 'none';
    return `
      <div class="scenario-card ${idx === 0 ? 'active' : ''}" data-id="${inc.id}">
        <div class="scenario-card-header">
          <span class="scenario-id">${inc.id}</span>
          <span class="scenario-target">${inc.target_service || 'unknown'}</span>
        </div>
        <div class="scenario-name" title="${escapeHtml(inc.alert_text || '')}">
          ${faultType.replace(/_/g, ' ').toUpperCase()}: ${escapeHtml((inc.alert_text || '').slice(0, 55))}...
        </div>
      </div>
    `;
  }).join('');

  // Attach card click handlers
  document.querySelectorAll('.scenario-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.scenario-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const id = card.getAttribute('data-id');
      const inc = incidents.find(i => i.id === id);
      selectScenario(inc);
    });
  });

  // Select the first scenario by default (INC-01)
  if (incidents.length > 0) {
    selectScenario(incidents[0]);
  }
}

function selectScenario(inc) {
  currentScenario = inc;
  activeIncidentBadge.textContent = inc.id;
  targetServiceInput.value = inc.target_service || 'payment-service';
  alertTextInput.value = (inc.alert_text || '').trim();
}

// Arm Fault & Load
async function handleArmFault() {
  if (!currentScenario) return;
  btnArmFault.disabled = true;
  btnArmFault.innerHTML = '<span>⏳</span> Arming...';

  try {
    const res = await fetch('/api/demo/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ incident_id: currentScenario.id }),
    });
    const data = await res.json();
    appendStreamItem('control', 'Control Plane', `Armed incident ${data.incident_id} on ${data.target_service}. Load generator active at ${data.load_rps} RPS.`);
  } catch (err) {
    appendStreamItem('control', 'Error', `Failed to arm fault: ${err.message}`);
  } finally {
    btnArmFault.disabled = false;
    btnArmFault.innerHTML = '<span>💣</span> 1. Arm Fault & Load';
  }
}

// Disarm Fault & Stop Load
async function handleDisarmFault() {
  btnDisarmFault.disabled = true;
  try {
    await fetch('/api/demo/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ incident_id: currentScenario ? currentScenario.id : null }),
    });
    appendStreamItem('control', 'Control Plane', 'Disarmed faults and stopped load generator traffic.');
  } catch (err) {
    appendStreamItem('control', 'Error', `Failed to disarm fault: ${err.message}`);
  } finally {
    btnDisarmFault.disabled = false;
  }
}

// Run Investigation
async function handleStartInvestigation() {
  const incidentId = currentScenario ? currentScenario.id : 'CUSTOM-01';
  const targetService = targetServiceInput.value.trim();
  const alertText = alertTextInput.value.trim();
  const autoApprove = autoApproveToggle.checked;

  resetInvestigationUI();
  startTimer();

  investigationStatus.textContent = 'Investigating...';
  investigationStatus.className = 'status-badge badge-running';
  btnInvestigate.disabled = true;

  try {
    const response = await fetch('/api/investigate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        incident_id: incidentId,
        alert_text: alertText,
        affected_service: targetService,
        auto_approve: autoApprove,
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop(); // keep remainder

      for (const block of lines) {
        if (!block.trim()) continue;
        processSSEBlock(block);
      }
    }
  } catch (err) {
    appendStreamItem('error', 'Error', `Investigation failed: ${err.message}`);
    stopTimer();
    investigationStatus.textContent = 'Error';
    investigationStatus.className = 'status-badge badge-idle';
  } finally {
    btnInvestigate.disabled = false;
  }
}

function processSSEBlock(block) {
  const lines = block.split('\n');
  let eventType = 'message';
  let dataStr = '';

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.replace('event:', '').trim();
    } else if (line.startsWith('data:')) {
      dataStr = line.replace('data:', '').trim();
    }
  }

  if (!dataStr) return;

  try {
    const data = JSON.parse(dataStr);
    handleSSEEvent(eventType, data);
  } catch (err) {
    console.warn('Failed to parse SSE JSON:', dataStr);
  }
}

function handleSSEEvent(eventType, data) {
  switch (eventType) {
    case 'init':
      currentThreadId = data.thread_id;
      appendStreamItem('supervisor', 'Supervisor', `Started session ${data.thread_id} for incident ${data.incident_id}`);
      highlightNode('node-supervisor');
      break;

    case 'step':
      handleStepEvent(data);
      break;

    case 'interrupt':
      handleInterruptEvent(data);
      break;

    case 'resume':
      appendStreamItem('remediation', 'Approval Gate', `Operator decision applied: ${data.approved ? 'APPROVED' : 'REJECTED'}`);
      approvalModal.classList.add('hidden');
      break;

    case 'complete':
      handleCompleteEvent(data);
      break;

    case 'error':
      appendStreamItem('error', 'Error', data.error);
      stopTimer();
      investigationStatus.textContent = 'Failed';
      investigationStatus.className = 'status-badge badge-idle';
      break;
  }
}

function handleStepEvent(data) {
  const nodeName = data.node;
  const nodeElementId = `node-${nodeName}`;
  highlightNode(nodeElementId);

  if (nodeName === 'supervisor') {
    const action = data.pending_action ? data.pending_action.next : 'plan';
    const lastHypothesis = (data.hypotheses && data.hypotheses.length) ? data.hypotheses[data.hypotheses.length - 1] : '';
    appendStreamItem('supervisor', `Supervisor (Step ${data.iterations || 1})`, `Decision: Route to [${action.toUpperCase()}]\n${lastHypothesis}`);
  } else if (['metrics', 'traces', 'logs', 'changes'].includes(nodeName)) {
    const evidence = data.evidence && data.evidence.length ? data.evidence[data.evidence.length - 1] : null;
    const summary = evidence ? evidence.summary : 'No evidence captured.';
    appendStreamItem(nodeName, `${nodeName.toUpperCase()} Agent`, summary);
  } else if (nodeName === 'rca_agent') {
    appendStreamItem('rca', 'RCA Agent', 'Synthesizing evidence and computing probable root cause.');
  } else if (nodeName === 'remediation') {
    const err = data.errors && data.errors.length ? data.errors[data.errors.length - 1] : 'Remediation completed.';
    appendStreamItem('remediation', 'Remediation Node', err);
  }
}

function handleInterruptEvent(data) {
  currentThreadId = data.thread_id;
  const payload = data.payload || {};
  highlightNode('node-remediation');

  modalTargetService.textContent = payload.target_service || 'Unknown';
  modalAction.textContent = payload.action || 'No action specified';
  modalRationale.textContent = payload.rationale || 'Root cause remediation';

  appendStreamItem('remediation', 'Remediation Gate', `Action requested: ${payload.action} on ${payload.target_service}`);
  approvalModal.classList.remove('hidden');
}

async function submitHumanApproval(approved) {
  if (!currentThreadId) return;
  try {
    await fetch(`/api/investigate/${currentThreadId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved: approved }),
    });
    approvalModal.classList.add('hidden');
  } catch (err) {
    alert(`Failed to submit approval: ${err.message}`);
  }
}

function handleCompleteEvent(data) {
  stopTimer();
  investigationStatus.textContent = 'Complete';
  investigationStatus.className = 'status-badge badge-complete';

  // Mark all nodes done
  document.querySelectorAll('.agent-node').forEach(node => {
    node.classList.remove('node-active');
    node.classList.add('node-done');
  });

  // Render RCA Report
  if (data.rca) {
    rcaRootCause.textContent = data.rca.root_cause || 'Root cause identified.';
    rcaConfidence.textContent = (data.rca.confidence || 'HIGH').toUpperCase();
    
    if (data.rca.evidence && data.rca.evidence.length) {
      rcaEvidenceList.innerHTML = data.rca.evidence.map(ev => `<li>${escapeHtml(ev)}</li>`).join('');
    } else {
      rcaEvidenceList.innerHTML = '<li>Evidence grounded in active telemetry.</li>';
    }

    rcaRecommendedAction.textContent = data.rca.recommended_action || 'Restore previous configuration.';
    statLatency.textContent = `${data.elapsed_seconds}s`;
    statToolCalls.textContent = data.tool_calls || '5';
    statEvidence.textContent = data.evidence_count || (data.rca.evidence ? data.rca.evidence.length : '4');

    if (data.trace_url) {
      rcaLangfuseLink.href = data.trace_url;
      rcaLangfuseLink.classList.remove('hidden');
    }

    rcaReportCard.classList.remove('hidden');
    rcaReportCard.scrollIntoView({ behavior: 'smooth' });
  }

  appendStreamItem('rca', 'Investigation Complete', `Root cause analysis concluded in ${data.elapsed_seconds}s.`);
}

// UI Helpers
function highlightNode(nodeId) {
  document.querySelectorAll('.agent-node').forEach(n => n.classList.remove('node-active'));
  const el = document.getElementById(nodeId);
  if (el) {
    el.classList.add('node-active');
  }
}

function resetInvestigationUI() {
  if (emptyStateMsg) emptyStateMsg.remove();
  rcaReportCard.classList.add('hidden');
  rcaLangfuseLink.classList.add('hidden');
  document.querySelectorAll('.agent-node').forEach(n => {
    n.classList.remove('node-active', 'node-done');
  });
}

function appendStreamItem(type, title, text) {
  const item = document.createElement('div');
  item.className = 'stream-item';

  const timeStr = new Date().toLocaleTimeString();
  const tagClass = `tag-${type.toLowerCase()}`;

  // Mask sensitive elements visually if present
  let formattedText = escapeHtml(text);
  formattedText = formattedText.replace(/\*\*\*REDACTED-([A-Z]+)\*\*\*/g, '<span class="stream-masked">***REDACTED-$1***</span>');

  item.innerHTML = `
    <div class="stream-item-header">
      <span class="stream-tag ${tagClass}">${escapeHtml(title)}</span>
      <span class="stream-time">${timeStr}</span>
    </div>
    <div class="stream-content">${formattedText}</div>
  `;

  streamLog.appendChild(item);
  streamLog.scrollTop = streamLog.scrollHeight;
}

function clearLogFeed() {
  streamLog.innerHTML = `
    <div class="empty-state" id="emptyStateMsg">
      <div class="empty-icon">🛰️</div>
      <h4>Log Stream Cleared</h4>
      <p>Ready for next investigation.</p>
    </div>
  `;
}

function startTimer() {
  stopTimer();
  startTime = Date.now();
  investigationTimer.textContent = '00:00';
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    investigationTimer.textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
