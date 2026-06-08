/**
 * MediFind India — Application Bootstrap
 * ─────────────────────────────────────────────────────────────
 * Initialises the app, wires all user interactions, and manages
 * the high-level search lifecycle.
 *
 * Load order (per index.html):
 *   1. components.js  — DOM builders
 *   2. stream.js      — SSE handler + UI object
 *   3. main.js        — this file (boot)
 */

'use strict';

const App = {
  stream:    null,
  isRunning: false,

  // ══════════════════════════════════════════════════════════════
  //  BOOT
  // ══════════════════════════════════════════════════════════════

  init() {
    // Wire up the stream
    this.stream = new MediStream();
    this.stream.onStart    = (med) => this._onStart(med);
    this.stream.onComplete = (ok)  => this._onComplete(ok);
    this.stream.onError    = (msg) => this._onError(msg);

    // Bind all UI events
    this._bindSearchForm();
    this._bindHintChips();
    this._bindNewSearch();
    this._bindThinkingCollapse();

    // Mark the first progress stage as active
    document.querySelector('[data-stage="validation"]')?.classList.add('active');
  },

  // ══════════════════════════════════════════════════════════════
  //  EVENT BINDING
  // ══════════════════════════════════════════════════════════════

  _bindSearchForm() {
    document.getElementById('searchForm')?.addEventListener('submit', (e) => {
      e.preventDefault();
      const val = document.getElementById('medicineInput')?.value?.trim();
      if (val) this.search(val);
    });
  },

  _bindHintChips() {
    document.querySelectorAll('.hint-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const med = chip.dataset.medicine;
        if (!med) return;

        const inp = document.getElementById('medicineInput');
        if (inp) inp.value = med;
        this.search(med);
      });
    });
  },

  _bindNewSearch() {
    document.getElementById('newSearchBtn')?.addEventListener('click', () => {
      this._resetAll();
    });
  },

  _bindThinkingCollapse() {
    const btn  = document.getElementById('thinkingCollapseBtn');
    const body = document.getElementById('thinkingBody');
    if (!btn || !body) return;

    btn.addEventListener('click', () => {
      const nowCollapsed = body.classList.toggle('collapsed');
      btn.textContent = nowCollapsed ? '▼' : '▲';
      btn.setAttribute('aria-label', nowCollapsed ? 'Expand' : 'Collapse');
    });
  },

  // ══════════════════════════════════════════════════════════════
  //  SEARCH  (public entry point)
  // ══════════════════════════════════════════════════════════════

  search(medicine) {
    if (this.isRunning) {
      Components_showToast('A search is already running. Please wait or start a new search.');
      return;
    }
    if (!medicine?.trim()) {
      Components_showToast('Please enter a medicine name (e.g. Paracetamol 500mg).');
      return;
    }

    // Tear down any previous results and reset all state
    UI.resetPipeline();
    this._setBusy(true);

    // Start SSE stream
    this.stream.connect(medicine.trim());

    // Scroll the pipeline container into view after a brief delay
    setTimeout(() => {
      document.getElementById('pipelineContainer')?.scrollIntoView({
        behavior: 'smooth', block: 'start',
      });
    }, 180);
  },

  // ══════════════════════════════════════════════════════════════
  //  STREAM CALLBACKS
  // ══════════════════════════════════════════════════════════════

  _onStart(medicine) {
    // Called when pipeline_start event received
    document.title = `MediFind — ${medicine}`;
  },

  _onComplete(success) {
    this._setBusy(false);

    if (success) {
      // Scroll to the results section for immediate visibility
      setTimeout(() => {
        document.getElementById('resultsSection')?.scrollIntoView({
          behavior: 'smooth', block: 'start',
        });
      }, 400);
    }
    // Restore page title
    document.title = 'MediFind India — AI-Powered Medicine Alternative Finder';
  },

  _onError(msg) {
    this._setBusy(false);
    Components_showToast(msg);
  },

  // ══════════════════════════════════════════════════════════════
  //  STATE HELPERS
  // ══════════════════════════════════════════════════════════════

  /** Toggle the search button / input between busy and idle. */
  _setBusy(active) {
    this.isRunning = active;

    const btn     = document.getElementById('searchBtn');
    const input   = document.getElementById('medicineInput');
    const btnText = btn?.querySelector('.btn-text');
    const btnIcon = btn?.querySelector('.btn-icon');

    if (active) {
      btn?.setAttribute('disabled', '');
      if (input)   input.disabled  = true;
      if (btnText) btnText.textContent = 'Analysing';
      if (btnIcon) btnIcon.textContent = '⏳';
    } else {
      btn?.removeAttribute('disabled');
      if (input)   input.disabled  = false;
      if (btnText) btnText.textContent = 'Analyse';
      if (btnIcon) btnIcon.textContent = '→';
    }
  },

  /** Full reset — used by the "New Search" button. */
  _resetAll() {
    this.stream.disconnect();
    this.isRunning = false;
    this._setBusy(false);

    UI.resetPipeline();

    // Scroll back to the search hero
    document.getElementById('heroSection')?.scrollIntoView({
      behavior: 'smooth', block: 'start',
    });

    // Clear and focus the input
    const inp = document.getElementById('medicineInput');
    if (inp) {
      inp.value    = '';
      inp.disabled = false;
      setTimeout(() => inp.focus(), 300);
    }

    document.title = 'MediFind India — AI-Powered Medicine Alternative Finder';
  },
};

// ══════════════════════════════════════════════════════════════
//  Entry point
// ══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => App.init());
