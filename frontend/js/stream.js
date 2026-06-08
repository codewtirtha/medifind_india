/**
 * MediFind India — SSE Stream Handler
 * ─────────────────────────────────────────────────────────────
 * Manages the EventSource connection and routes every server-sent
 * event to the correct Components_* function and UI state change.
 *
 * Emitted event types (from orchestrator.py):
 *   pipeline_start | phase | heartbeat | complete | error
 *   validation_success | validation_failed
 *   orchestrator_thinking | orchestrator_response | orchestrator_error | orchestrator_fallback
 *   alternatives_found | no_alternatives
 *   agent_deploy | agent_start | agent_thinking | tool_call | tool_result
 *   agent_complete | agent_done
 *   similarity_score | final_results | tool_summary
 */

'use strict';

class MediStream {
  constructor() {
    this._es          = null;    // EventSource
    this._active      = false;
    this._agentsDone  = 0;
    this._totalAgents = 0;
    this._simIndex    = 0;      // similarity bar insertion order
    this._respBuf     = '';     // accumulated orchestrator response text

    // Public callbacks — wired by main.js
    this.onStart    = null;  // fn(medicineName)
    this.onComplete = null;  // fn(success: bool)
    this.onError    = null;  // fn(message: string)
  }

  // ══════════════════════════════════════════════════════════════
  //  PUBLIC API
  // ══════════════════════════════════════════════════════════════

  connect(medicine) {
    this.disconnect();
    this._reset();

    const url = `/api/search?medicine=${encodeURIComponent(medicine)}`;
    this._es = new EventSource(url);
    this._active = true;

    this._es.onmessage = (e) => this._dispatch(e);
    this._es.onerror   = ()  => {
      if (!this._active) return;
      this.disconnect();
      if (this.onError) this.onError('Connection lost — please try again.');
    };
  }

  disconnect() {
    if (this._es) { this._es.close(); this._es = null; }
    this._active = false;
  }

  // ══════════════════════════════════════════════════════════════
  //  INTERNAL — routing
  // ══════════════════════════════════════════════════════════════

  _reset() {
    this._agentsDone  = 0;
    this._totalAgents = 0;
    this._simIndex    = 0;
    this._respBuf     = '';
  }

  _dispatch(raw) {
    let ev;
    try { ev = JSON.parse(raw.data); } catch { return; }

    const handlers = {
      // ── Lifecycle ────────────────────────────────────────────
      pipeline_start:        () => this._onPipelineStart(ev),
      phase:                 () => this._onPhase(ev),
      heartbeat:             () => {},     // keep-alive, no-op
      complete:              () => this._onComplete(),
      error:                 () => this._onStreamError(ev),

      // ── Validation ──────────────────────────────────────────
      validation_success:    () => this._onValOk(ev),
      validation_failed:     () => this._onValFail(ev),

      // ── Orchestrator ────────────────────────────────────────
      orchestrator_thinking: () => Components_appendThinking(ev.text || ''),
      orchestrator_response: () => this._onOrchResp(ev),
      orchestrator_error:    () => Components_showToast(`Orchestrator: ${ev.message}`),
      orchestrator_fallback: () => UI.setStatus(ev.message, true),

      // ── Alternatives ────────────────────────────────────────
      alternatives_found:    () => this._onAltsFound(ev),
      no_alternatives:       () => this._onNoAlts(ev),

      // ── Sub-Agents ──────────────────────────────────────────
      agent_deploy:    () => this._onAgentDeploy(ev),
      agent_start:     () => Components_updateAgentStatus(ev.agent_id, 'Running loop…', 'thinking'),
      agent_thinking:  () => Components_addAgentThought(ev.agent_id, ev.thought || ''),
      tool_call:       () => this._onToolCall(ev),
      tool_result:     () => Components_addAgentToolResult(ev.agent_id, ev.tool, ev.sources || []),
      agent_complete:  () => Components_setAgentComplete(ev.agent_id, ev.data || {}),
      agent_done:      () => this._onAgentDone(ev),

      // ── Similarity & Results ─────────────────────────────────
      similarity_score: () => Components_addSimilarityBar(ev, this._simIndex++),
      final_results:    () => this._onFinalResults(ev),
      tool_summary:     () => this._onToolSummary(ev),
    };

    const fn = handlers[ev.type];
    if (fn) fn();
  }

  // ══════════════════════════════════════════════════════════════
  //  HANDLERS
  // ══════════════════════════════════════════════════════════════

  _onPipelineStart(ev) {
    UI.showPipeline();
    UI.setStatus(`Researching: ${ev.medicine}`, true);
    UI.setProgress(5);
    if (this.onStart) this.onStart(ev.medicine);
  }

  _onPhase(ev) {
    const PCT = { validation: 10, discovery: 30, agents: 60, ranking: 85, results: 100 };
    UI.setProgress(PCT[ev.phase] || 0);
    UI.setStatus(ev.message, true);
    UI.activateStage(ev.phase);

    // Progressive section reveal
    if (ev.phase === 'discovery') {
      UI.show('thinkingSection');
    }
    if (ev.phase === 'agents') {
      UI.show('agentSection');
      // Once agents start, shrink the thinking panel
      const tb = document.getElementById('thinkingBody');
      if (tb) tb.classList.add('compact-mode');
    }
    if (ev.phase === 'ranking') {
      UI.show('similaritySection');
    }
  }

  _onValOk(ev) {
    UI.show('validationSection');
    Components_renderValidationSuccess(ev.data || { medicine: ev.medicine });
    UI.setStatus(`✅ Validated: ${ev.medicine}`, false);
    UI.completeStage('validation');
  }

  _onValFail(ev) {
    UI.show('validationSection');
    Components_renderValidationFailed(ev);
    UI.setStatus('❌ Medicine not found in India', false);
    UI.setProgress(100);
    UI.completeAllStages();
    if (this.onComplete) this.onComplete(false);
  }

  _onOrchResp(ev) {
    this._respBuf += (ev.text || '');
    Components_finalizeThinking(this._respBuf);
  }

  _onAltsFound(ev) {
    this._totalAgents = ev.count;
    UI.show('alternativesSection');
    Components_renderAlternatives(ev.alternatives);

    const badge = document.getElementById('agentCountBadge');
    if (badge) badge.textContent = `0 / ${ev.count} complete`;

    UI.setStatus(ev.message, true);
  }

  _onNoAlts() {
    Components_showToast('No alternatives found. Try a different medicine name.');
    if (this.onComplete) this.onComplete(false);
  }

  _onAgentDeploy(ev) {
    this._totalAgents = ev.total_agents;
    Components_createAgentCard(ev.agent_id, ev.drug_name, ev.therapeutic_reason);
    UI.setStatus(ev.message, true);
  }

  _onToolCall(ev) {
    Components_addAgentToolCall(ev.agent_id, ev.tool, ev.purpose, ev.input);
    UI.setStatus(`🔧 Agent ${ev.agent_id}: calling ${ev.tool}…`, true);
  }

  _onAgentDone(ev) {
    this._agentsDone++;
    const badge = document.getElementById('agentCountBadge');
    if (badge) badge.textContent = `${this._agentsDone} / ${this._totalAgents} complete`;
    Components_updateAlternativeStatus(ev.agent_id, '✅');

    if (this._agentsDone === this._totalAgents)
      UI.setStatus('🏆 All agents complete — computing scores…', true);
  }

  _onFinalResults(ev) {
    UI.setProgress(100);
    UI.completeAllStages();
    UI.show('resultsSection');
    Components_renderResults(ev.results || []);
    UI.setStatus(`🏆 ${ev.count} alternatives ranked`, false);
    UI.show('newSearchBtn');
  }

  _onToolSummary(ev) {
    UI.show('toolSummarySection');
    Components_renderToolLog(ev.all_tool_calls || []);
  }

  _onComplete() {
    this.disconnect();
    if (this.onComplete) this.onComplete(true);
  }

  _onStreamError(ev) {
    Components_showToast(ev.message || 'An error occurred. Please try again.');
    this.disconnect();
    if (this.onComplete) this.onComplete(false);
  }
}


// ═══════════════════════════════════════════════════════════════
//  UI — Centralised DOM state management
//  (shared by stream.js and main.js)
// ═══════════════════════════════════════════════════════════════

const UI = {
  show(id) {
    document.getElementById(id)?.classList.remove('hidden');
  },

  hide(id) {
    document.getElementById(id)?.classList.add('hidden');
  },

  showPipeline() {
    this.show('pipelineContainer');
    this.show('statusBanner');
    this.show('validationSection');
  },

  setStatus(text, spinning = true) {
    const t  = document.getElementById('statusText');
    const sp = document.getElementById('statusSpinner');
    if (t)  t.textContent = text;
    if (sp) sp.style.display = spinning ? 'block' : 'none';
  },

  setProgress(pct) {
    const f = document.getElementById('progressFill');
    if (f) f.style.width = `${pct}%`;
  },

  /** Mark stages before `stage` as done; `stage` itself as active. */
  activateStage(stage) {
    const ORDER = ['validation', 'discovery', 'agents', 'ranking', 'results'];
    const idx   = ORDER.indexOf(stage);
    document.querySelectorAll('.stage').forEach((el, i) => {
      el.classList.remove('active', 'done');
      if (i < idx)      el.classList.add('done');
      else if (i === idx) el.classList.add('active');
    });
  },

  completeStage(stage) {
    const el = document.querySelector(`[data-stage="${stage}"]`);
    if (el) { el.classList.remove('active'); el.classList.add('done'); }
  },

  completeAllStages() {
    document.querySelectorAll('.stage').forEach(el => {
      el.classList.remove('active');
      el.classList.add('done');
    });
  },

  /** Full pipeline reset — called before each new search. */
  resetPipeline() {
    // Hide all dynamic sections
    [
      'pipelineContainer', 'statusBanner',
      'validationSection', 'thinkingSection', 'alternativesSection',
      'agentSection', 'similaritySection', 'resultsSection', 'toolSummarySection',
    ].forEach(id => this.hide(id));

    // Clear all dynamic content areas
    [
      'validationCard', 'thinkingStream', 'orchestratorResponseBody',
      'alternativesGrid', 'agentHub', 'similarityBars', 'resultsGrid', 'toolLog',
    ].forEach(id => {
      const e = document.getElementById(id);
      if (e) e.innerHTML = '';
    });

    // Hide orchestrator response panel
    document.getElementById('orchestratorResponse')?.classList.add('hidden');

    // Reset progress
    this.setProgress(0);
    document.querySelectorAll('.stage').forEach(el => el.classList.remove('active', 'done'));
    document.querySelector('[data-stage="validation"]')?.classList.add('active');

    // Un-compact thinking body
    const tb = document.getElementById('thinkingBody');
    if (tb) tb.classList.remove('compact-mode', 'collapsed');

    // Reset agent count badge
    const badge = document.getElementById('agentCountBadge');
    if (badge) badge.textContent = '0 / 10 complete';
  },
};
