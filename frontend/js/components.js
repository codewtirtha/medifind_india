/**
 * MediFind India — UI Component Builders
 * ─────────────────────────────────────────────────────────────
 * Pure functions that create / mutate DOM elements.
 * Every CSS class name here matches styles.css exactly.
 * No framework — just fast, readable vanilla DOM manipulation.
 */

'use strict';

// ═══════════════════════════════════════════════════════════════
//  MICRO-HELPERS
// ═══════════════════════════════════════════════════════════════

/** Create element with optional class and attributes. */
function _el(tag, cls, attrs = {}) {
  const e = document.createElement(tag);
  if (cls)  e.className = cls;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

/** Escape a string for safe innerHTML insertion. */
function _esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

/** Format a number as Indian Rupees. */
function _inr(n) {
  if (!n || n <= 0) return 'N/A';
  return `₹${parseFloat(n).toFixed(2)}`;
}

/** Shortcut for getElementById. */
const $  = (id)  => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);


// ═══════════════════════════════════════════════════════════════
//  VALIDATION CARD
// ═══════════════════════════════════════════════════════════════

function Components_renderValidationSuccess(data) {
  const card = $('validationCard');
  if (!card) return;

  const brand   = data.brand_name || data.medicine || 'Unknown';
  const generic = data.generic_name || '';
  const mfr     = data.manufacturer || '';
  const cat     = data.category || data.therapeutic_class || '';
  const price   = _inr(data.typical_price_inr || data.price_inr);
  const comp    = Array.isArray(data.composition) ? data.composition : [];
  const srcs    = (data.source_urls || []).slice(0, 2);

  const chips = [
    mfr   ? `<span class="vc-chip">🏭 ${_esc(mfr)}</span>` : '',
    cat   ? `<span class="vc-chip">💊 ${_esc(cat)}</span>` : '',
    price !== 'N/A' ? `<span class="vc-chip">💰 ${_esc(price)}</span>` : '',
    comp.length ? `<span class="vc-chip highlight">${_esc(comp.join(' + '))}</span>` : '',
  ].filter(Boolean).join('');

  const srcLinks = srcs.map(u => {
    try {
      return `<a class="source-pill" href="${_esc(u)}" target="_blank" rel="noopener">🔗 ${_esc(new URL(u).hostname.replace('www.', ''))}</a>`;
    } catch { return ''; }
  }).join('');

  card.innerHTML = `
    <div class="vc-success">
      <div class="vc-icon">✅</div>
      <div class="vc-info">
        <div class="vc-brand">${_esc(brand)}</div>
        ${generic ? `<div class="vc-generic">${_esc(generic)}</div>` : ''}
        <div class="vc-chips">${chips}</div>
        ${srcLinks ? `<div class="vc-chips" style="margin-top:8px">${srcLinks}</div>` : ''}
      </div>
    </div>`;
}

function Components_renderValidationFailed(data) {
  const card = $('validationCard');
  if (!card) return;

  card.innerHTML = `
    <div class="vc-error">
      <div class="vc-error-icon">❌</div>
      <div>
        <div class="vc-error-title">Medicine Not Found in India</div>
        <div class="vc-error-desc">
          ${_esc(data.reason || 'Could not locate this medicine in Indian pharmaceutical databases.')}
          ${data.suggestion
            ? `<br><br>💡 Did you mean: <strong>${_esc(data.suggestion)}</strong>?`
            : ''}
          <br><span style="color:var(--text-4);font-size:12px">
            Try an Indian brand name (Crocin, Augmentin) or INN generic name.
          </span>
        </div>
      </div>
    </div>`;
}


// ═══════════════════════════════════════════════════════════════
//  THINKING STREAM  (Orchestrator chain-of-thought)
// ═══════════════════════════════════════════════════════════════

function Components_appendThinking(text) {
  const stream = $('thinkingStream');
  if (!stream) return;

  // Append raw text — CSS handles white-space:pre-wrap & font-mono
  stream.textContent += text;

  const body = $('thinkingBody');
  if (body && !body.classList.contains('collapsed'))
    body.scrollTop = body.scrollHeight;
}

function Components_finalizeThinking(text) {
  const resp = $('orchestratorResponse');
  const body = $('orchestratorResponseBody');
  if (!resp || !body) return;

  body.textContent = text;   // or-body uses pre-wrap mono
  resp.classList.remove('hidden');
}


// ═══════════════════════════════════════════════════════════════
//  ALTERNATIVES DISCOVERY GRID
// ═══════════════════════════════════════════════════════════════

function Components_renderAlternatives(alts) {
  const grid = $('alternativesGrid');
  if (!grid) return;

  grid.innerHTML = '';
  alts.forEach((alt, i) => {
    const pill = _el('div', 'alt-pill');
    pill.id = `alt-pill-${i + 1}`;
    pill.style.animationDelay = `${i * 55}ms`;

    pill.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div class="alt-pill-number">Alt ${i + 1}</div>
        <span id="alt-status-${i + 1}" aria-label="status" style="font-size:13px">⏳</span>
      </div>
      <div class="alt-pill-name">${_esc(alt.brand_name || alt.generic_name)}</div>
      ${alt.manufacturer    ? `<div class="alt-pill-reason">🏭 ${_esc(alt.manufacturer)}</div>`    : ''}
      ${alt.therapeutic_reason ? `<div class="alt-pill-reason" style="margin-top:3px">${_esc(alt.therapeutic_reason)}</div>` : ''}`;

    grid.appendChild(pill);
  });
}

function Components_updateAlternativeStatus(agentId, emoji) {
  const el = $(`alt-status-${agentId}`);
  if (el) el.textContent = emoji;
}


// ═══════════════════════════════════════════════════════════════
//  AGENT HUB  (10 research-agent cards)
// ═══════════════════════════════════════════════════════════════

const _agentRefs = {};   // agentId → { card, bodyEl, thoughtEl, statusEl, toolCount }

function Components_createAgentCard(agentId, drugName, reason) {
  const hub = $('agentHub');
  if (!hub) return;

  const card = _el('div', 'agent-card');
  card.id = `agent-card-${agentId}`;
  card.innerHTML = `
    <div class="ac-header">
      <div class="ac-id-badge">A${agentId}</div>
      <div class="ac-drug-name" title="${_esc(drugName)}">${_esc(drugName)}</div>
      <div class="ac-status" id="ac-status-${agentId}">Initialising</div>
    </div>
    <div class="ac-body" id="ac-body-${agentId}">
      <div class="ac-thought" id="ac-thought-${agentId}"></div>
    </div>`;

  hub.appendChild(card);

  _agentRefs[agentId] = {
    card,
    bodyEl:    $(`ac-body-${agentId}`),
    thoughtEl: $(`ac-thought-${agentId}`),
    statusEl:  $(`ac-status-${agentId}`),
    toolCount: 0,
  };
}

/** Update status label + card border state. */
function Components_updateAgentStatus(agentId, label, state) {
  const r = _agentRefs[agentId];
  if (!r) return;

  if (r.statusEl) {
    r.statusEl.textContent = label;
    r.statusEl.className   = `ac-status${state ? ` ${state}` : ''}`;
  }

  const cls = {
    active: 'agent-card active',
    thinking: 'agent-card active',
    calling:  'agent-card active',
    done:  'agent-card done',
    error: 'agent-card error',
  };
  r.card.className = cls[state] || 'agent-card';
}

/** Stream a reasoning thought into the agent card. */
function Components_addAgentThought(agentId, thought) {
  const r = _agentRefs[agentId];
  if (!r || !r.thoughtEl) return;

  // Keep last 300 chars so the card stays compact
  r.thoughtEl.textContent = (r.thoughtEl.textContent + thought).slice(-300);
  Components_updateAgentStatus(agentId, 'Reasoning…', 'thinking');
}

/** Show a tool call badge, replacing the previous one. */
function Components_addAgentToolCall(agentId, tool, purpose, input) {
  const r = _agentRefs[agentId];
  if (!r || !r.bodyEl) return;

  r.toolCount++;
  // Remove previous tool-call div (replace to keep card compact)
  r.bodyEl.querySelectorAll('.ac-tool-call').forEach(e => e.remove());

  const short = typeof input === 'object'
    ? JSON.stringify(input).slice(0, 70)
    : String(input || '').slice(0, 70);

  const row = _el('div', 'ac-tool-call');
  row.innerHTML = `
    <span class="act-icon">🔧</span>
    <span class="act-name">${_esc(tool)}</span>
    <span class="act-input">${_esc(purpose || short)}</span>`;
  r.bodyEl.appendChild(row);

  Components_updateAgentStatus(agentId, `→ ${tool}`, 'calling');
}

/** Append source links after a tool result arrives. */
function Components_addAgentToolResult(agentId, tool, sources) {
  const r = _agentRefs[agentId];
  if (!r || !r.bodyEl || !sources?.length) return;

  // Remove old sources; append new
  r.bodyEl.querySelectorAll('.ac-sources').forEach(e => e.remove());

  const div = _el('div', 'ac-sources');
  sources.slice(0, 3).forEach(u => {
    try {
      const host = new URL(u).hostname.replace('www.', '');
      const a = _el('a', 'source-pill', { href: u, target: '_blank', rel: 'noopener' });
      a.textContent = `🔗 ${host}`;
      div.appendChild(a);
    } catch {}
  });
  r.bodyEl.appendChild(div);
}

/** Collapse card to compact result view once agent finishes. */
function Components_setAgentComplete(agentId, data) {
  const r = _agentRefs[agentId];
  if (!r) return;

  r.card.className = 'agent-card done compact';
  if (r.statusEl) {
    r.statusEl.textContent = '✅ Done';
    r.statusEl.className   = 'ac-status done';
  }

  // Rebuild body as a tidy result block
  const srcs  = r.bodyEl.querySelector('.ac-sources');
  r.bodyEl.innerHTML = '';

  const comp  = Array.isArray(data.composition)
    ? data.composition.join(' + ')
    : (data.composition || '');
  const price = _inr(data.price_inr);

  const res = _el('div', 'ac-result');
  res.innerHTML = `
    <div class="acr-composition">Composition: <span>${_esc(comp) || 'Not found'}</span></div>
    <div class="acr-price">${_esc(price)}</div>`;
  r.bodyEl.appendChild(res);
  if (srcs) r.bodyEl.appendChild(srcs);
}


// ═══════════════════════════════════════════════════════════════
//  SIMILARITY BARS
// ═══════════════════════════════════════════════════════════════

function Components_addSimilarityBar(data, index) {
  const container = $('similarityBars');
  if (!container) return;

  const score = Math.min(Math.round(data.composite_score || 0), 100);
  const name  = data.drug_name || 'Unknown';

  const row = _el('div', 'sim-bar-row');
  row.style.animationDelay = `${index * 80}ms`;
  row.innerHTML = `
    <div class="sim-bar-label">${_esc(name)}</div>
    <div class="sim-bar-track">
      <div class="sim-bar-fill"></div>
    </div>
    <div class="sim-bar-score">${score}%</div>`;

  container.appendChild(row);

  // Trigger CSS transition after the element is painted
  requestAnimationFrame(() => {
    const fill = row.querySelector('.sim-bar-fill');
    if (fill) fill.style.width = `${score}%`;
  });
}


// ═══════════════════════════════════════════════════════════════
//  FINAL RESULTS GRID
// ═══════════════════════════════════════════════════════════════

function Components_renderResults(results) {
  const grid = $('resultsGrid');
  if (!grid) return;

  grid.innerHTML = '';
  results.forEach((r, i) => grid.appendChild(_buildResultCard(r, i + 1)));
}

function _buildResultCard(result, rank) {
  const MEDAL = { 1: '🥇', 2: '🥈', 3: '🥉' };
  const RCLASS = { 1: 'gold', 2: 'silver', 3: 'bronze' };

  const card  = _el('div', `result-card rank-${rank}`);
  card.style.animationDelay = `${(rank - 1) * 55}ms`;

  const brand    = result.brand_name || result.generic_name || 'Unknown';
  const generic  = result.generic_name || '';
  const mfr      = result.manufacturer || '';
  const comp     = Array.isArray(result.composition)
    ? result.composition : (result.composition ? [result.composition] : []);
  const common   = (result.common_ingredients || []).map(s => s.toLowerCase());
  const price    = _inr(result.price_inr);
  const cScore   = Math.round(result.composite_score || 0);
  const compSim  = Math.round(result.composition_similarity || 0);
  const priceSim = Math.round(result.price_similarity || 0);
  const srcs     = (result.source_urls || []).slice(0, 3);

  const compTags = comp.map(c => {
    const isCommon = common.some(ci => ci.includes(c.toLowerCase()) || c.toLowerCase().includes(ci));
    return `<span class="rc-comp-tag${isCommon ? ' common' : ''}">${_esc(c)}</span>`;
  }).join('');

  const srcLinks = srcs.map(u => {
    try {
      const host = new URL(u).hostname.replace('www.', '');
      return `<a href="${_esc(u)}" target="_blank" rel="noopener">${_esc(host)}</a>`;
    } catch { return ''; }
  }).join('');

  card.innerHTML = `
    <div class="rc-rank ${RCLASS[rank] || 'normal'}">${MEDAL[rank] || `#${rank}`}</div>
    <div class="rc-main">
      <div class="rc-drug-name">${_esc(brand)}</div>
      ${generic && generic !== brand ? `<div class="rc-generic">${_esc(generic)}</div>` : ''}
      ${mfr ? `<div class="rc-generic">🏭 ${_esc(mfr)}</div>` : ''}
      <div class="rc-composition">${compTags || '<span class="rc-comp-tag">Composition N/A</span>'}</div>
      ${srcLinks ? `<div class="rc-sources">${srcLinks}</div>` : ''}
    </div>
    <div class="rc-scores">
      <div class="rc-composite">${cScore}%</div>
      <div class="rc-composite-label">Composite Score</div>
      <div class="rc-score-row">
        <span class="rc-score-label">Comp.</span>
        <div class="rc-score-mini-bar">
          <div class="rc-score-mini-fill comp" style="width:${compSim}%"></div>
        </div>
        <span style="font-size:10px;color:var(--blue)">${compSim}%</span>
      </div>
      <div class="rc-score-row">
        <span class="rc-score-label">Price</span>
        <div class="rc-score-mini-bar">
          <div class="rc-score-mini-fill price" style="width:${priceSim}%"></div>
        </div>
        <span style="font-size:10px;color:var(--green)">${priceSim}%</span>
      </div>
      <div class="rc-price">${price}</div>
    </div>`;

  return card;
}


// ═══════════════════════════════════════════════════════════════
//  TOOL CALL AUDIT LOG
// ═══════════════════════════════════════════════════════════════

const TOOL_ICONS = {
  validate_medicine_india: '🔬',
  search_drug_composition: '🧪',
  search_drug_price:       '💰',
  google_search_grounding: '🌐',
};

function Components_renderToolLog(calls) {
  const log   = $('toolLog');
  const badge = $('toolCountBadge');
  if (!log) return;

  log.innerHTML = '';
  if (badge) badge.textContent = `${calls.length} calls`;

  calls.forEach((call, i) => {
    const item = _el('div', 'tool-log-item');
    item.style.animationDelay = `${i * 22}ms`;

    const icon  = TOOL_ICONS[call.tool] || '🔧';
    const agent = call.agent || 'Orchestrator';
    const srcs  = (call.sources || []).slice(0, 3).map(u => {
      try {
        const host = new URL(u).hostname.replace('www.', '');
        return `<a class="tli-badge" href="${_esc(u)}" target="_blank" rel="noopener"
                   style="text-decoration:none">🔗 ${_esc(host)}</a>`;
      } catch { return ''; }
    }).join('');

    item.innerHTML = `
      <div class="tli-icon">${icon}</div>
      <div class="tli-content">
        <div class="tli-tool">${_esc(call.tool)}</div>
        <div class="tli-purpose">${_esc(call.purpose || '')}</div>
        <div class="tli-meta">
          <span class="tli-badge agent">${_esc(agent)}</span>
          ${srcs}
        </div>
      </div>`;

    log.appendChild(item);
  });
}


// ═══════════════════════════════════════════════════════════════
//  ERROR TOAST
// ═══════════════════════════════════════════════════════════════

function Components_showToast(msg, duration = 7000) {
  const toast = $('errorToast');
  const text  = $('toastMsg');
  if (!toast || !text) return;

  text.textContent = msg;
  toast.classList.remove('hidden');

  clearTimeout(toast._tid);
  if (duration > 0)
    toast._tid = setTimeout(() => toast.classList.add('hidden'), duration);
}
