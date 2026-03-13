/* deck-detail.js — Standalone deck detail page logic. */

(async function() {
  // Extract deck ID from URL: /decks/:id
  const pathParts = window.location.pathname.split('/').filter(Boolean);
  if (pathParts.length < 2 || pathParts[0] !== 'decks') {
    document.getElementById('loading-state').innerHTML =
      '<div class="empty-state">Invalid deck URL. Expected /decks/:id</div>';
    return;
  }
  const deckId = pathParts[1];

  // Fetch deck data
  const deckRes = await fetch(`/api/decks/${encodeURIComponent(deckId)}`);
  if (!deckRes.ok) {
    const err = await deckRes.json().catch(() => ({}));
    document.getElementById('loading-state').innerHTML =
      `<div class="empty-state">${esc(err.error || 'Deck not found')}</div>`;
    return;
  }

  let deck = await deckRes.json();
  document.title = `${deck.name} — DeckDumpster`;

  // State
  let deckCards = [];
  let selectedCardIds = new Set();
  let pickerSelected = new Set();
  let editingDeckId = null;
  let activeRoleFilter = null;
  let activeTypeFilter = null;
  let currentView = 'grid';
  const COL_MIN = 1, COL_MAX = 12;
  let gridCols = parseInt(localStorage.getItem('deckGridCols'))
    || (window.innerWidth < 600 ? 2 : 5);

  // Build the page
  const layout = document.getElementById('deck-detail-layout');
  // Add delete button to site header
  const siteHeader = document.querySelector('.site-header');
  if (siteHeader) {
    const delBtn = document.createElement('button');
    delBtn.id = 'btn-delete';
    delBtn.className = 'danger';
    delBtn.style.cssText = 'font-size:0.8rem;padding:4px 12px;margin-left:auto';
    delBtn.textContent = 'Delete Deck';
    siteHeader.appendChild(delBtn);
  }

  layout.innerHTML = `
    <div class="deck-two-col">
      <div class="deck-col-main">
        <div class="deck-view-bar">
          <div class="zone-tabs" id="type-filters"></div>
          <div class="deck-view-controls">
            <div class="view-toggle-group">
              <button class="secondary" id="view-table-btn" title="Table view">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="1" width="14" height="3" rx="1"/>
                  <rect x="1" y="6" width="14" height="3" rx="1"/>
                  <rect x="1" y="11" width="14" height="3" rx="1"/>
                </svg>
              </button>
              <button class="secondary active" id="view-grid-btn" title="Grid view">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="1" width="6" height="6" rx="1"/>
                  <rect x="9" y="1" width="6" height="6" rx="1"/>
                  <rect x="1" y="9" width="6" height="6" rx="1"/>
                  <rect x="9" y="9" width="6" height="6" rx="1"/>
                </svg>
              </button>
            </div>
            <div class="col-controls" id="grid-size-wrap">
              <button class="col-btn" id="col-minus">&minus;</button>
              <div class="col-count" id="col-count"></div>
              <button class="col-btn" id="col-plus">+</button>
            </div>
          </div>
        </div>

        <div id="active-filter-banner" class="active-filter-banner" style="display:none"></div>

        <div id="card-display">
        <table class="card-table" id="card-table" style="display:none">
          <thead>
            <tr>
              <th><input type="checkbox" id="select-all"></th>
              <th>Name</th>
              <th>Role</th>
              <th>Set</th>
              <th>Mana</th>
              <th>Type</th>
              <th>Finish</th>
              <th>Condition</th>
            </tr>
          </thead>
          <tbody id="card-tbody"></tbody>
        </table>
        <div class="card-grid" id="card-grid"></div>
        </div>

        <div class="completeness-section" id="completeness-section" style="display:none">
          <div class="completeness-header" id="completeness-header">
            <h3>Expected Cards <span id="completeness-summary"></span></h3>
            <span id="completeness-toggle">&#9660;</span>
          </div>
          <div class="completeness-body" id="completeness-body"></div>
        </div>
      </div>

      <div class="deck-col-sidebar">
        <h2 id="deck-name"></h2>
        <div id="commander-display" class="commander-display"></div>
        <div class="deck-meta-grid" id="deck-meta"></div>

        <div class="sidebar-actions">
          <div class="sidebar-actions-row">
            <button class="secondary" id="btn-edit">Edit Metadata</button>
            <button class="secondary" id="btn-curve">Curve</button>
          </div>
          <button id="btn-generate-plan" style="display:none">Generate Plan</button>
          <button class="secondary" id="btn-weights" style="display:none">Edit Weights</button>
          <button id="btn-autofill" style="display:none">Autofill</button>
          <button id="btn-fill-lands" style="display:none">Fill Lands</button>
        </div>

        <div class="plan-section" id="plan-section" style="display:none">
          <div class="plan-header">
            <h3>Deck Plan</h3>
            <div class="plan-header-actions">
              <button class="secondary" id="btn-edit-plan" style="display:none;font-size:0.8rem;padding:4px 10px">Edit</button>
            </div>
          </div>
          <div class="plan-body" id="plan-body"></div>
        </div>
      </div>
    </div>

    <!-- Edit Deck Modal -->
    <div class="modal-backdrop" id="deck-modal">
      <div class="modal">
        <h3 id="modal-title">Edit Deck</h3>
        <div class="form-group">
          <label>Name *</label>
          <input type="text" id="f-name" placeholder="My Commander Deck">
        </div>
        <div class="form-group">
          <label>Format</label>
          <select id="f-format">
            <option value="">-- None --</option>
            <option value="commander">Commander / EDH</option>
            <option value="standard">Standard</option>
            <option value="modern">Modern</option>
            <option value="pioneer">Pioneer</option>
            <option value="legacy">Legacy</option>
            <option value="vintage">Vintage</option>
            <option value="pauper">Pauper</option>
          </select>
        </div>
        <div class="form-group">
          <label>Description</label>
          <textarea id="f-description" rows="2"></textarea>
        </div>
        <div class="form-group">
          <label><input type="checkbox" id="f-precon"> Preconstructed deck</label>
        </div>
        <div class="form-group">
          <label><input type="checkbox" id="f-hypothetical"> Hypothetical deck (cards not physically assigned)</label>
        </div>
        <div class="precon-fields" id="precon-fields" style="display:none">
          <div class="form-group">
            <label>Origin Set</label>
            <select id="f-origin-set">
              <option value="">-- None --</option>
              <option value="jmp">Jumpstart (JMP)</option>
              <option value="j22">Jumpstart 2022 (J22)</option>
              <option value="j25">Jumpstart 2025 (J25)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Theme</label>
            <input type="text" id="f-origin-theme" placeholder="e.g. Goblins, Angels">
          </div>
          <div class="form-group">
            <label>Variation</label>
            <input type="number" id="f-origin-variation" min="1" max="4" placeholder="1-4">
          </div>
        </div>
        <div class="form-group">
          <label>Sleeve Color</label>
          <input type="text" id="f-sleeve" placeholder="e.g. black dragon shield matte">
        </div>
        <div class="form-group">
          <label>Deck Box</label>
          <input type="text" id="f-deckbox" placeholder="e.g. Ultimate Guard Boulder 100+">
        </div>
        <div class="form-group">
          <label>Storage Location</label>
          <input type="text" id="f-location" placeholder="e.g. shelf 2, left side">
        </div>
        <div class="form-actions">
          <button id="btn-save-deck">Save</button>
          <button class="secondary" id="btn-cancel-edit">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Add Cards Modal -->
    <div class="modal-backdrop" id="add-cards-modal">
      <div class="modal">
        <h3>Add Cards to Deck</h3>
        <div class="form-group">
          <label>Zone</label>
          <select id="add-zone">
            <option value="mainboard">Mainboard</option>
            <option value="sideboard">Sideboard</option>
            <option value="commander">Commander</option>
          </select>
        </div>
        <div class="form-group">
          <label>Search your collection</label>
          <input type="text" id="picker-search" placeholder="Search by name...">
        </div>
        <div class="picker-cards" id="picker-cards"></div>
        <div class="form-actions">
          <button id="btn-add-picker">Add Selected</button>
          <button class="secondary" id="btn-cancel-add">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Expected List Import Modal -->
    <div class="modal-backdrop" id="expected-modal">
      <div class="modal">
        <h3>Import Expected Card List</h3>
        <div class="form-group">
          <label>Paste decklist (one card per line)</label>
          <textarea id="f-expected-list" rows="10" placeholder="1 Goblin Bushwhacker (ZEN) 125&#10;1 Raging Goblin (M10) 153&#10;6 Mountain (JMP) 62"></textarea>
        </div>
        <div id="expected-errors" style="color:#e74c3c;font-size:0.85rem;margin-bottom:8px"></div>
        <div class="form-actions">
          <button id="btn-import-expected-confirm">Import</button>
          <button class="secondary" id="btn-cancel-expected">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Autofill Suggestions Modal -->
    <div class="modal-backdrop" id="autofill-modal">
      <div class="modal" style="max-width:700px;max-height:80vh;overflow-y:auto">
        <h3>Autofill Suggestions</h3>
        <div id="autofill-body"><span class="spinner"></span> Finding cards...</div>
        <div class="form-actions">
          <button id="btn-autofill-add" disabled>Add Selected</button>
          <button class="secondary" id="btn-autofill-cancel">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Fill Lands Modal -->
    <div class="modal-backdrop" id="fill-lands-modal">
      <div class="modal fill-lands-modal">
        <h3>Land Suggestions</h3>
        <div id="fill-lands-body"><span class="spinner"></span> Finding lands...</div>
        <div class="form-actions">
          <button id="btn-fill-lands-add" disabled>Add All</button>
          <button class="secondary" id="btn-fill-lands-cancel">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Plan Variants Modal -->
    <div class="modal-backdrop" id="plan-variants-modal">
      <div class="modal" style="max-width:800px;max-height:85vh;overflow-y:auto">
        <h3>Choose a Deck Plan</h3>
        <div id="plan-variants-body"></div>
        <div class="form-actions">
          <button id="btn-save-plan" disabled>Save Selected Plan</button>
        </div>
      </div>
    </div>
    <!-- Curve Modal -->
    <div class="modal-backdrop" id="curve-modal">
      <div class="modal" style="max-width:600px">
        <h3>Mana Curve</h3>
        <div id="curve-chart"></div>
        <div id="curve-legend" class="curve-legend"></div>
        <div class="form-actions">
          <button class="secondary" id="btn-curve-close">Close</button>
        </div>
      </div>
    </div>

    <!-- Weights Modal -->
    <div class="modal-backdrop" id="weights-modal">
      <div class="modal" style="max-width:500px">
        <h3>Autofill Weights</h3>
        <p class="weights-desc">Adjust how cards are scored during autofill and replacement suggestions.</p>
        <div id="weights-body"></div>
        <div class="form-actions">
          <button id="btn-weights-save">Save</button>
          <button class="secondary" id="btn-weights-reset">Reset to Defaults</button>
          <button class="secondary" id="btn-weights-cancel">Cancel</button>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" id="replace-modal">
      <div class="modal replace-modal">
        <div class="replace-header">
          <h3>Replace: <span id="replace-card-name"></span> <span id="replace-card-roles" class="replace-roles"></span></h3>
          <button class="btn btn-ghost" id="replace-cancel">✕</button>
        </div>
        <div class="replace-tabs">
          <button class="replace-tab active" data-tab="role">Role</button>
          <button class="replace-tab" data-tab="type">Type</button>
          <button class="replace-tab" data-tab="search">Search</button>
        </div>
        <div class="replace-search-inputs" id="replace-search-form" style="display:none">
          <input placeholder="Name" id="rs-name">
          <input placeholder="Mana value" id="rs-cmc" type="number">
          <input placeholder="Set code" id="rs-set">
          <input placeholder="Type" id="rs-type">
          <input placeholder="Tag (e.g. removal)" id="rs-tag">
        </div>
        <div class="replace-grid-wrap">
          <div class="card-grid replace-card-grid" id="replace-grid"></div>
        </div>
        <div class="replace-confirm-bar">
          <span id="replace-selection-label">No card selected</span>
          <button class="btn btn-accent" id="replace-confirm" disabled>Confirm</button>
        </div>
      </div>
    </div>
  `;

  // --- Wire up event handlers ---

  // Type filter pills are wired dynamically in buildTypeFilters()

  // Select all checkbox
  document.getElementById('select-all').addEventListener('change', function() {
    deckCards.forEach(c => {
      if (this.checked) selectedCardIds.add(c.id);
      else selectedCardIds.delete(c.id);
    });
    renderCards();
  });

  // Header/sidebar buttons
  document.getElementById('btn-edit').addEventListener('click', showEditModal);
  document.getElementById('btn-curve').addEventListener('click', openCurveModal);
  document.getElementById('btn-generate-plan').addEventListener('click', generatePlan);
  document.getElementById('btn-autofill').addEventListener('click', runAutofill);
  document.getElementById('btn-weights').addEventListener('click', openWeightsModal);
  document.getElementById('btn-delete').addEventListener('click', deleteDeck);
  document.getElementById('btn-edit-plan').addEventListener('click', enterPlanEditMode);

  // Completeness header toggle
  document.getElementById('completeness-header').addEventListener('click', toggleCompleteness);

  // Modal save/cancel buttons
  document.getElementById('btn-save-deck').addEventListener('click', saveDeck);
  document.getElementById('btn-cancel-edit').addEventListener('click', () => closeModal('deck-modal'));
  document.getElementById('btn-add-picker').addEventListener('click', addSelectedPickerCards);
  document.getElementById('btn-cancel-add').addEventListener('click', () => closeModal('add-cards-modal'));
  document.getElementById('btn-import-expected-confirm').addEventListener('click', importExpectedList);
  document.getElementById('btn-cancel-expected').addEventListener('click', () => closeModal('expected-modal'));
  document.getElementById('btn-autofill-add').addEventListener('click', addAutofillCards);
  document.getElementById('btn-autofill-cancel').addEventListener('click', () => closeModal('autofill-modal'));
  document.getElementById('btn-fill-lands').addEventListener('click', runFillLands);
  document.getElementById('btn-fill-lands-add').addEventListener('click', addFillLandsCards);
  document.getElementById('btn-fill-lands-cancel').addEventListener('click', () => closeModal('fill-lands-modal'));
  document.getElementById('btn-weights-save').addEventListener('click', saveWeights);
  document.getElementById('btn-weights-reset').addEventListener('click', resetWeights);
  document.getElementById('btn-weights-cancel').addEventListener('click', () => closeModal('weights-modal'));
  document.getElementById('btn-curve-close').addEventListener('click', () => closeModal('curve-modal'));
  document.getElementById('btn-save-plan').addEventListener('click', savePlanVariant);
  document.getElementById('replace-cancel').addEventListener('click', () => closeModal('replace-modal'));
  document.getElementById('replace-confirm').addEventListener('click', confirmReplacement);

  // Replace tab switching
  let replaceActiveTab = 'role';
  let replaceCandidateData = { role: [], type: [], search: [] };
  document.querySelectorAll('.replace-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      replaceActiveTab = tab.dataset.tab;
      document.querySelectorAll('.replace-tab').forEach(t => t.classList.toggle('active', t === tab));
      document.getElementById('replace-search-form').style.display = replaceActiveTab === 'search' ? '' : 'none';
      if (replaceActiveTab === 'search' && replaceCandidateData.search.length === 0) {
        searchReplacements();
      } else {
        renderReplaceGrid(replaceCandidateData[replaceActiveTab]);
      }
    });
  });

  // Replace search debounce
  let replaceSearchTimer = null;
  ['rs-name', 'rs-cmc', 'rs-set', 'rs-type', 'rs-tag'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      clearTimeout(replaceSearchTimer);
      replaceSearchTimer = setTimeout(searchReplacements, 300);
    });
  });

  // Precon checkbox toggle
  document.getElementById('f-precon').addEventListener('change', function() {
    document.getElementById('precon-fields').style.display = this.checked ? '' : 'none';
  });

  // Picker search
  document.getElementById('picker-search').addEventListener('input', searchPickerCards);

  // View toggle
  document.getElementById('view-table-btn').addEventListener('click', () => {
    currentView = 'table';
    updateViewButtons();
    renderCards();
    fetch('/api/settings', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ default_card_view: 'table' }) });
  });
  document.getElementById('view-grid-btn').addEventListener('click', () => {
    currentView = 'grid';
    updateViewButtons();
    renderCards();
    fetch('/api/settings', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ default_card_view: 'grid' }) });
  });

  function updateViewButtons() {
    document.getElementById('view-table-btn').classList.toggle('active', currentView === 'table');
    document.getElementById('view-grid-btn').classList.toggle('active', currentView === 'grid');
    document.getElementById('grid-size-wrap').style.display = currentView === 'grid' ? '' : 'none';
    document.getElementById('card-table').style.display = currentView === 'table' ? '' : 'none';
    document.getElementById('card-grid').style.display = currentView === 'grid' ? '' : 'none';
  }

  // Grid column controls
  function applyGridCols() {
    document.getElementById('col-count').textContent = gridCols;
    document.getElementById('col-minus').disabled = gridCols <= COL_MIN;
    document.getElementById('col-plus').disabled = gridCols >= COL_MAX;
    document.getElementById('card-grid').style.setProperty('--grid-cols', gridCols);
    localStorage.setItem('deckGridCols', gridCols);
  }
  document.getElementById('col-minus').addEventListener('click', () => {
    if (gridCols > COL_MIN) { gridCols--; applyGridCols(); if (currentView === 'grid') renderCards(); }
  });
  document.getElementById('col-plus').addEventListener('click', () => {
    if (gridCols < COL_MAX) { gridCols++; applyGridCols(); if (currentView === 'grid') renderCards(); }
  });
  applyGridCols();

  // Grid card click — navigate to card detail (or open replace modal)
  document.getElementById('card-grid').addEventListener('click', e => {
    const replBtn = e.target.closest('.replace-btn');
    if (replBtn) {
      e.stopPropagation();
      if (deck.hypothetical) {
        openReplaceModal(null, replBtn.dataset.name, replBtn.dataset.oracleId);
      } else {
        openReplaceModal(parseInt(replBtn.dataset.cid), replBtn.dataset.name);
      }
      return;
    }
    const card = e.target.closest('.sheet-card');
    if (card) window.location.href = `/card/${card.dataset.sc}/${card.dataset.cn}`;
  });

  // Close modals on backdrop click (except plan-variants — must choose a plan)
  document.querySelectorAll('.modal-backdrop').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target === el && el.id !== 'plan-variants-modal') el.classList.remove('active');
    });
  });

  // --- Render deck detail header ---
  function renderDeckDetail() {
    document.getElementById('deck-name').textContent = deck.name;
    document.title = `${deck.name} — DeckDumpster`;
    const meta = [];
    if (deck.format) meta.push(`<span class="label">Format</span><span>${esc(deck.format)}</span>`);
    if (deck.is_precon) meta.push(`<span class="label">Type</span><span>Preconstructed</span>`);
  if (deck.hypothetical) meta.push(`<span class="label">Mode</span><span class="hypothetical-badge">Hypothetical</span>`);
    if (deck.origin_set_code) meta.push(`<span class="label">Set</span><span>${esc(deck.origin_set_code.toUpperCase())}</span>`);
    if (deck.origin_theme) meta.push(`<span class="label">Theme</span><span>${esc(deck.origin_theme)}</span>`);
    if (deck.origin_variation) meta.push(`<span class="label">Variation</span><span>${deck.origin_variation}</span>`);
    if (deck.sleeve_color) meta.push(`<span class="label">Sleeves</span><span>${esc(deck.sleeve_color)}</span>`);
    if (deck.deck_box) meta.push(`<span class="label">Deck Box</span><span>${esc(deck.deck_box)}</span>`);
    if (deck.storage_location) meta.push(`<span class="label">Location</span><span>${esc(deck.storage_location)}</span>`);
    if (deck.description) meta.push(`<span class="label">Notes</span><span>${esc(deck.description)}</span>`);
    meta.push(`<span class="label">Cards</span><span>${deck.card_count}</span>`);
    if (deck.total_value) meta.push(`<span class="label">Value</span><span>$${Number(deck.total_value).toFixed(2)}</span>`);
    document.getElementById('deck-meta').innerHTML = meta.join('');
    loadCompleteness();
  }

  // --- Card type from type_line ---
  const TYPE_ORDER = ['Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Planeswalker', 'Battle', 'Land'];

  function primaryType(typeLine) {
    if (!typeLine) return 'Other';
    for (const t of TYPE_ORDER) {
      if (typeLine.includes(t)) return t;
    }
    return 'Other';
  }

  function buildTypeFilters() {
    const typeCounts = {};
    const nonCmdCards = allDeckCards.filter(c => c.deck_zone !== 'commander');
    for (const c of nonCmdCards) {
      const t = primaryType(c.type_line);
      typeCounts[t] = (typeCounts[t] || 0) + 1;
    }
    // Sort by TYPE_ORDER, then Other at end
    const types = Object.keys(typeCounts).sort((a, b) => {
      const ai = TYPE_ORDER.indexOf(a), bi = TYPE_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });

    const container = document.getElementById('type-filters');
    const allCount = nonCmdCards.length;
    let html = `<div class="tab${activeTypeFilter === null ? ' active' : ''}" data-type="all">All (${allCount})</div>`;
    for (const t of types) {
      html += `<div class="tab${activeTypeFilter === t ? ' active' : ''}" data-type="${esc(t)}">${esc(t)} (${typeCounts[t]})</div>`;
    }
    container.innerHTML = html;

    container.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const type = tab.dataset.type;
        activeTypeFilter = type === 'all' ? null : type;
        container.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        deckCards = getMainboardCards();
        renderCards();
      });
    });
  }

  function getMainboardCards() {
    const nonCmd = allDeckCards.filter(c => c.deck_zone !== 'commander');
    if (!activeTypeFilter) return nonCmd;
    return nonCmd.filter(c => primaryType(c.type_line) === activeTypeFilter);
  }

  // --- Load and render cards ---
  let allDeckCards = [];  // All cards across all zones

  async function loadDeckCards() {
    const res = await fetch(`/api/decks/${deck.id}/cards`);
    const allCards = await res.json();
    allDeckCards = allCards;

    // Render commander card in sidebar
    const cmdCards = allCards.filter(c => c.deck_zone === 'commander');
    const cmdEl = document.getElementById('commander-display');
    if (cmdCards.length > 0) {
      cmdEl.innerHTML = cmdCards.map(c => {
        const sc = c.set_code.toLowerCase();
        const cn = c.collector_number;
        const rarityColor = getRarityColor(c.rarity);
        const foilClass = (c.finish === 'foil' || c.finish === 'etched') ? ' foil' : '';
        return `<a href="/card/${esc(sc)}/${esc(cn)}" class="commander-card">
          <div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:#111">
            <img src="${c.image_uri || ''}" alt="${esc(c.name)}">
          </div>
        </a>`;
      }).join('');
      cmdEl.style.display = '';
    } else {
      cmdEl.innerHTML = '';
      cmdEl.style.display = 'none';
    }

    buildTypeFilters();
    deckCards = getMainboardCards();
    renderCards();
  }

  function getFilteredCards() {
    if (!activeRoleFilter) return deckCards;
    if (activeRoleFilter === 'lands') {
      return deckCards.filter(c => (c.type_line || '').includes('Land'));
    }
    return deckCards.filter(c => {
      const tags = c.tags ? c.tags.split(',') : [];
      return tags.includes(activeRoleFilter);
    });
  }

  function getCardRoles(card) {
    const tags = card.tags ? card.tags.split(',') : [];
    const roles = [];
    // Regular tag targets
    for (const t of tags) {
      if (planTargetTags.has(t)) {
        const val = currentPlanTargets && currentPlanTargets[t];
        const label = val.label;
        roles.push(label);
      }
    }
    // Custom query targets — check card's custom_roles if present
    if (card.custom_roles) {
      for (const label of card.custom_roles) roles.push(label);
    }
    return roles;
  }

  function renderCards() {
    const cards = getFilteredCards();

    // Filter banner
    const banner = document.getElementById('active-filter-banner');
    if (activeRoleFilter) {
      const label = activeRoleFilter.replace(/-/g, ' ');
      banner.innerHTML = `Filtered: <strong>${esc(label)}</strong> <button class="secondary" id="btn-clear-filter" style="font-size:0.75rem;padding:2px 8px;margin-left:8px">Clear</button>`;
      banner.style.display = '';
      document.getElementById('btn-clear-filter').addEventListener('click', () => {
        activeRoleFilter = null;
        renderCards();
        highlightPlanTag(null);
      });
    } else {
      banner.style.display = 'none';
    }

    if (currentView === 'grid') {
      renderGrid(cards);
    } else {
      renderTable(cards);
    }
  }

  function renderTable(cards) {
    const tbody = document.getElementById('card-tbody');
    if (cards.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-secondary); padding:24px;">No cards in this zone</td></tr>';
      return;
    }
    const isHypo = !!deck.hypothetical;
    tbody.innerHTML = cards.map(c => {
      const sc = c.set_code.toLowerCase();
      const cn = c.collector_number;
      const role = getCardRoles(c).join(', ');
      const cbData = isHypo ? `data-oracle-id="${esc(c.oracle_id)}"` : `data-id="${c.id}"`;
      const cbKey = isHypo ? c.oracle_id : c.id;
      const ownershipBadge = isHypo
        ? (c.owned_copies > 0
          ? `<span class="own-badge owned" title="${c.free_copies} free / ${c.owned_copies} owned">&#10003;</span>`
          : '<span class="own-badge missing" title="Not owned">&#10007;</span>')
        : '';
      const qtyPrefix = (isHypo && c.quantity > 1) ? `${c.quantity}x ` : '';
      return `<tr>
        <td><input type="checkbox" ${cbData} ${selectedCardIds.has(cbKey) ? 'checked' : ''}></td>
        <td><a href="/card/${esc(sc)}/${esc(cn)}">${qtyPrefix}${esc(c.name)}</a> ${ownershipBadge}</td>
        <td class="role-cell">${esc(role)}</td>
        <td>${esc(c.set_code.toUpperCase())} #${esc(cn)}</td>
        <td class="mana">${renderMana(c.mana_cost || '')}</td>
        <td>${esc(c.type_line || '')}</td>
        <td>${isHypo ? '' : esc(c.finish || '')}</td>
        <td>${isHypo ? '' : esc(c.condition || '')}</td>
      </tr>`;
    }).join('');

    // Wire up checkbox change handlers
    tbody.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', function() {
        if (isHypo) {
          const oid = this.dataset.oracleId;
          if (this.checked) selectedCardIds.add(oid);
          else selectedCardIds.delete(oid);
        } else {
          const id = parseInt(this.dataset.id);
          if (this.checked) selectedCardIds.add(id);
          else selectedCardIds.delete(id);
        }
      });
    });
  }

  function renderGrid(cards) {
    const grid = document.getElementById('card-grid');
    if (cards.length === 0) {
      grid.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">No cards in this zone</div>';
      return;
    }

    const isHypo = !!deck.hypothetical;
    grid.innerHTML = cards.map(c => {
      const sc = c.set_code.toLowerCase();
      const cn = c.collector_number;
      const rarityColor = getRarityColor(c.rarity);
      const foilClass = (c.finish === 'foil' || c.finish === 'etched') ? ' foil' : '';
      const roles = getCardRoles(c);
      const primaryRole = roles.length ? roles[0] : '';
      const replaceData = isHypo
        ? `data-oracle-id="${esc(c.oracle_id)}" data-name="${esc(c.name)}"`
        : `data-cid="${c.id}" data-name="${esc(c.name)}"`;
      const ownershipOverlay = isHypo
        ? (c.owned_copies > 0
          ? '<span class="own-overlay owned">&#10003;</span>'
          : '<span class="own-overlay missing">&#10007;</span>')
        : '';
      return `<div class="sheet-card" data-sc="${esc(sc)}" data-cn="${esc(cn)}">
        <div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:#111">
          <img src="${c.image_uri || ''}" alt="${esc(c.name)}" loading="lazy">
          <button class="replace-btn" title="Replace" ${replaceData}>⇄</button>
          ${primaryRole ? `<span class="role-overlay">${esc(primaryRole)}</span>` : ''}
          ${ownershipOverlay}
        </div>
      </div>`;
    }).join('');
  }

  // --- Edit modal ---
  function showEditModal() {
    editingDeckId = deck.id;
    document.getElementById('modal-title').textContent = 'Edit Deck';
    document.getElementById('f-name').value = deck.name || '';
    document.getElementById('f-format').value = deck.format || '';
    document.getElementById('f-description').value = deck.description || '';
    document.getElementById('f-precon').checked = !!deck.is_precon;
    document.getElementById('f-hypothetical').checked = !!deck.hypothetical;
    document.getElementById('f-origin-set').value = deck.origin_set_code || '';
    document.getElementById('f-origin-theme').value = deck.origin_theme || '';
    document.getElementById('f-origin-variation').value = deck.origin_variation || '';
    document.getElementById('precon-fields').style.display = deck.is_precon ? '' : 'none';
    document.getElementById('f-sleeve').value = deck.sleeve_color || '';
    document.getElementById('f-deckbox').value = deck.deck_box || '';
    document.getElementById('f-location').value = deck.storage_location || '';
    document.getElementById('deck-modal').classList.add('active');
  }

  async function saveDeck() {
    const data = {
      name: document.getElementById('f-name').value.trim(),
      format: document.getElementById('f-format').value || null,
      description: document.getElementById('f-description').value.trim() || null,
      is_precon: document.getElementById('f-precon').checked,
      hypothetical: document.getElementById('f-hypothetical').checked,
      sleeve_color: document.getElementById('f-sleeve').value.trim() || null,
      deck_box: document.getElementById('f-deckbox').value.trim() || null,
      storage_location: document.getElementById('f-location').value.trim() || null,
      origin_set_code: document.getElementById('f-origin-set').value || null,
      origin_theme: document.getElementById('f-origin-theme').value.trim() || null,
      origin_variation: document.getElementById('f-origin-variation').value ? parseInt(document.getElementById('f-origin-variation').value) : null,
    };
    if (!data.name) { alert('Name is required'); return; }

    const res = await fetch(`/api/decks/${deck.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    deck = await res.json();
    closeModal('deck-modal');
    renderDeckDetail();
    await loadDeckCards();
  }

  // --- Delete deck ---
  async function deleteDeck() {
    if (!confirm(`Delete "${deck.name}"? Cards will be unassigned but not deleted.`)) return;
    await fetch(`/api/decks/${deck.id}`, { method: 'DELETE' });
    window.location.href = '/decks';
  }

  // --- Remove selected cards ---
  async function removeSelectedCards() {
    if (selectedCardIds.size === 0) { alert('No cards selected'); return; }
    const ids = Array.from(selectedCardIds);
    const body = deck.hypothetical
      ? { oracle_ids: ids }
      : { collection_ids: ids };
    await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    selectedCardIds.clear();

    const res = await fetch(`/api/decks/${deck.id}`);
    deck = await res.json();
    renderDeckDetail();
    await loadDeckCards();
  }

  // --- Add cards picker ---
  function showAddCardsModal() {
    pickerSelected.clear();
    document.getElementById('picker-search').value = '';
    document.getElementById('picker-cards').innerHTML =
      '<div style="padding:12px;color:var(--text-secondary);">Type to search your collection...</div>';
    document.getElementById('add-cards-modal').classList.add('active');
  }

  async function searchPickerCards() {
    const q = document.getElementById('picker-search').value.trim();
    if (q.length < 2) {
      document.getElementById('picker-cards').innerHTML =
        '<div style="padding:12px;color:var(--text-secondary);">Type at least 2 characters...</div>';
      return;
    }
    const res = await fetch(`/api/collection?q=${encodeURIComponent(q)}&status=owned`);
    const data = await res.json();
    const cards = Array.isArray(data) ? data : data.cards || [];

    const container = document.getElementById('picker-cards');
    if (cards.length === 0) {
      container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);">No matching cards found</div>';
      return;
    }
    container.innerHTML = cards.map(c => {
      const key = c.printing_id + '|' + c.finish;
      return `<div class="picker-card ${pickerSelected.has(key) ? 'selected' : ''}" data-key="${esc(key)}">
        <span>${esc(c.name)}</span>
        <span style="color:var(--text-secondary);font-size:0.85rem">${esc(c.set_code.toUpperCase())} #${esc(c.collector_number)} - ${esc(c.finish)}</span>
        <span style="color:var(--text-secondary);font-size:0.85rem">x${c.qty}</span>
      </div>`;
    }).join('');

    // Wire up picker card click handlers
    container.querySelectorAll('.picker-card').forEach(el => {
      el.addEventListener('click', function() {
        const key = this.dataset.key;
        if (pickerSelected.has(key)) {
          pickerSelected.delete(key);
          this.classList.remove('selected');
        } else {
          pickerSelected.add(key);
          this.classList.add('selected');
        }
      });
    });
  }

  async function addSelectedPickerCards() {
    if (pickerSelected.size === 0) { alert('No cards selected'); return; }
    const zone = document.getElementById('add-zone').value;

    if (deck.hypothetical) {
      // For hypothetical decks, resolve oracle_ids from printings
      const oracleIds = [];
      for (const key of pickerSelected) {
        const [printingId] = key.split('|');
        const res = await fetch(`/api/collection/copies?printing_id=${printingId}`);
        const copies = await res.json();
        if (copies.length > 0 && copies[0].oracle_id) {
          oracleIds.push(copies[0].oracle_id);
        }
      }
      if (oracleIds.length === 0) { alert('No cards found'); return; }
      const res = await fetch(`/api/decks/${deck.id}/cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ oracle_ids: oracleIds, zone }),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
    } else {
      const allIds = [];
      for (const key of pickerSelected) {
        const [printingId, finish] = key.split('|');
        const res = await fetch(`/api/collection/copies?printing_id=${printingId}&finish=${finish}`);
        const copies = await res.json();
        for (const copy of copies) {
          if (!copy.deck_id && !copy.binder_id) {
            allIds.push(copy.id);
          }
        }
      }
      if (allIds.length === 0) {
        alert('No unassigned copies found for the selected cards');
        return;
      }
      const res = await fetch(`/api/decks/${deck.id}/cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collection_ids: allIds, zone }),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
    }

    closeModal('add-cards-modal');

    const deckRes = await fetch(`/api/decks/${deck.id}`);
    deck = await deckRes.json();
    renderDeckDetail();
    await loadDeckCards();
  }

  // --- Expected list import ---
  function showExpectedModal() {
    document.getElementById('f-expected-list').value = '';
    document.getElementById('expected-errors').textContent = '';
    document.getElementById('expected-modal').classList.add('active');
  }

  async function importExpectedList() {
    const text = document.getElementById('f-expected-list').value.trim();
    if (!text) { alert('Paste a decklist first'); return; }

    const res = await fetch(`/api/decks/${deck.id}/expected`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decklist: text }),
    });
    const result = await res.json();
    if (result.error) {
      const errEl = document.getElementById('expected-errors');
      errEl.textContent = result.error;
      if (result.details) errEl.textContent += '\n' + result.details.join('\n');
      return;
    }
    closeModal('expected-modal');
    loadCompleteness();
  }

  // --- Completeness ---
  async function loadCompleteness() {
    const section = document.getElementById('completeness-section');

    const expRes = await fetch(`/api/decks/${deck.id}/expected`);
    const expected = await expRes.json();
    if (!expected.length && !deck.is_precon) {
      section.style.display = 'none';
      return;
    }
    if (!expected.length) {
      section.style.display = '';
      document.getElementById('completeness-summary').textContent = '(no expected list set)';
      document.getElementById('completeness-body').innerHTML =
        '<p style="color:var(--text-secondary);padding:8px">Use "Import Expected List" to define the expected cards for this deck.</p>';
      return;
    }

    const res = await fetch(`/api/decks/${deck.id}/completeness`);
    const data = await res.json();
    section.style.display = '';

    const total = data.present.length + data.missing.length;
    document.getElementById('completeness-summary').textContent =
      `(${data.present.length}/${total} present, ${data.missing.length} missing, ${data.extra.length} extra)`;

    let html = '';

    if (data.present.length) {
      html += '<div class="completeness-group"><h4 class="present">Present (' + data.present.length + ')</h4>';
      for (const c of data.present) {
        html += `<div class="completeness-card"><span class="qty">${c.actual_qty}/${c.expected_qty}</span><span>${esc(c.name)}</span></div>`;
      }
      html += '</div>';
    }

    if (data.missing.length) {
      html += '<div class="completeness-group"><h4 class="missing">Missing (' + data.missing.length + ')</h4>';
      for (const c of data.missing) {
        html += `<div class="completeness-card"><span class="qty">${c.actual_qty}/${c.expected_qty}</span><span>${esc(c.name)}</span>`;
        for (const loc of c.locations) {
          const label = loc.deck_name ? `Deck: ${loc.deck_name}` : loc.binder_name ? `Binder: ${loc.binder_name}` : 'Unassigned';
          const cls = (!loc.deck_name && !loc.binder_name) ? 'location-tag unassigned' : 'location-tag';
          html += ` <span class="${cls}" data-cid="${loc.collection_id}">${esc(label)}</span>`;
        }
        html += '</div>';
      }
      html += '</div>';

      const unassignedIds = [];
      for (const c of data.missing) {
        for (const loc of c.locations) {
          if (!loc.deck_name && !loc.binder_name) unassignedIds.push(loc.collection_id);
        }
      }
      if (unassignedIds.length) {
        html += `<button id="btn-reassemble-all" style="margin-bottom:8px">Reassemble ${unassignedIds.length} Unassigned Card${unassignedIds.length > 1 ? 's' : ''}</button>`;
      }
    }

    if (data.extra.length) {
      html += '<div class="completeness-group"><h4 class="extra">Extra (' + data.extra.length + ')</h4>';
      for (const c of data.extra) {
        html += `<div class="completeness-card"><span class="qty">x${c.actual_qty}</span><span>${esc(c.name)}</span></div>`;
      }
      html += '</div>';
    }

    document.getElementById('completeness-body').innerHTML = html;

    // Wire up location tag click handlers for reassemble
    document.querySelectorAll('.location-tag[data-cid]').forEach(tag => {
      tag.addEventListener('click', () => reassembleCard(parseInt(tag.dataset.cid)));
    });

    // Wire up reassemble all button
    const reassembleBtn = document.getElementById('btn-reassemble-all');
    if (reassembleBtn) {
      reassembleBtn.addEventListener('click', reassembleAll);
    }
  }

  function toggleCompleteness() {
    const body = document.getElementById('completeness-body');
    const toggle = document.getElementById('completeness-toggle');
    body.classList.toggle('collapsed');
    toggle.innerHTML = body.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
  }

  async function reassembleCard(collectionId) {
    const res = await fetch(`/api/decks/${deck.id}/reassemble`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: [collectionId] }),
    });
    const result = await res.json();
    if (result.error) { alert(result.error); return; }

    const deckRes = await fetch(`/api/decks/${deck.id}`);
    deck = await deckRes.json();
    renderDeckDetail();
    await loadDeckCards();
  }

  async function reassembleAll() {
    const res = await fetch(`/api/decks/${deck.id}/completeness`);
    const data = await res.json();
    const ids = [];
    for (const c of data.missing) {
      for (const loc of c.locations) {
        if (!loc.deck_name && !loc.binder_name) ids.push(loc.collection_id);
      }
    }
    if (!ids.length) { alert('No unassigned cards to reassemble'); return; }

    const moveRes = await fetch(`/api/decks/${deck.id}/reassemble`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: ids }),
    });
    const result = await moveRes.json();
    if (result.error) { alert(result.error); return; }

    const deckRes = await fetch(`/api/decks/${deck.id}`);
    deck = await deckRes.json();
    renderDeckDetail();
    await loadDeckCards();
  }

  // --- Dynamic button visibility ---
  function updateDynamicButtons() {
    const totalCards = allDeckCards.length;
    const landCount = allDeckCards.filter(c =>
      (c.type_line || '').includes('Land') && c.deck_zone !== 'commander'
    ).length;
    const hasPlan = !!(currentPlanTargets && Object.keys(currentPlanTargets).length);

    // Weights: visible whenever a plan exists
    document.getElementById('btn-weights').style.display = hasPlan ? '' : 'none';

    // Autofill: hide if >90 cards or no plan
    const autofillBtn = document.getElementById('btn-autofill');
    autofillBtn.style.display = (hasPlan && totalCards <= 90) ? '' : 'none';

    // Fill Lands: hide if >20 lands or no plan
    const fillLandsBtn = document.getElementById('btn-fill-lands');
    fillLandsBtn.style.display = (hasPlan && landCount <= 20) ? '' : 'none';
  }

  // --- Plan ---
  let planProgress = null;  // {tag: {current, target}} from audit
  let planTargetTags = new Set();  // tags from current plan targets
  let currentPlanTargets = null;  // {tag: count} — raw plan targets for editing

  async function loadPlan() {
    // Show Generate Plan button for Commander decks
    if (deck.format === 'commander') {
      document.getElementById('btn-generate-plan').style.display = '';
    }

    const res = await fetch(`/api/decks/${deck.id}/plan`);
    const plan = await res.json();
    if (plan && plan.targets) {
      currentPlanTargets = plan.targets;
      planTargetTags = new Set(Object.keys(plan.targets));
      // Fetch audit for real progress counts
      const auditRes = await fetch(`/api/decks/${deck.id}/audit`);
      if (auditRes.ok) {
        const audit = await auditRes.json();
        planProgress = audit.plan_progress;
      }
      showPlanProgress(plan.targets);
      document.getElementById('btn-generate-plan').style.display = 'none';
      updateDynamicButtons();
    }
  }

  function showPlanProgress(targets) {
    const section = document.getElementById('plan-section');
    const body = document.getElementById('plan-body');
    section.style.display = '';
    document.getElementById('btn-edit-plan').style.display = '';

    // Sort: "lands" first, then alphabetical
    const sorted = Object.entries(targets).sort(([a], [b]) => {
      if (a === 'lands') return -1;
      if (b === 'lands') return 1;
      return a.localeCompare(b);
    });

    let html = '<div class="plan-progress">';
    for (const [tag, targetVal] of sorted) {
      const target = targetVal.count;
      const label = targetVal.label;
      const current = (planProgress && planProgress[tag]) ? planProgress[tag].current : 0;
      const pct = target > 0 ? Math.min((current / target) * 100, 100) : 0;
      const cls = current >= target ? 'met' : 'under';
      const activeClass = activeRoleFilter === tag ? ' active' : '';
      html += `<div class="plan-progress-row">`;
      html += `<div class="plan-progress-top"><span class="cat clickable${activeClass}" data-tag="${esc(tag)}">${esc(label)}</span><span class="counts">${current}/${target}</span></div>`;
      html += `<div class="bar"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>`;
      html += `</div>`;
    }
    html += '</div>';
    body.innerHTML = html;

    // Wire up plan tag click to filter cards
    body.querySelectorAll('.cat.clickable').forEach(el => {
      el.addEventListener('click', () => {
        const tag = el.dataset.tag;
        if (activeRoleFilter === tag) {
          activeRoleFilter = null;
          highlightPlanTag(null);
        } else {
          activeRoleFilter = tag;
          highlightPlanTag(tag);
        }
        renderCards();
      });
    });
  }

  function highlightPlanTag(tag) {
    document.querySelectorAll('.plan-progress .cat.clickable').forEach(el => {
      el.classList.toggle('active', el.dataset.tag === tag);
    });
  }

  async function generatePlan() {
    const btn = document.getElementById('btn-generate-plan');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const section = document.getElementById('plan-section');
    const body = document.getElementById('plan-body');
    section.style.display = '';
    body.innerHTML = '<div class="plan-streaming"><span class="spinner"></span> Asking Claude for deck plans...</div>';

    // Use fetch to stream the SSE response (handles non-SSE error responses too)
    let res;
    try {
      res = await fetch(`/api/decks/${deck.id}/plan/generate`);
    } catch (_) {
      body.innerHTML = '<div class="plan-error">Connection to server failed. Is the server running?</div>';
      btn.disabled = false;
      btn.textContent = 'Generate Plan';
      return;
    }

    // Non-SSE error response (e.g. missing API key)
    if (res.headers.get('content-type')?.includes('application/json')) {
      const err = await res.json();
      body.innerHTML = `<div class="plan-error">${esc(err.message || err.error || 'Unknown error')}</div>`;
      btn.disabled = false;
      btn.textContent = 'Generate Plan';
      return;
    }

    // Parse SSE stream manually
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let gotPlans = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages
      while (buffer.includes('\n\n')) {
        const idx = buffer.indexOf('\n\n');
        const message = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let eventType = 'message';
        let eventData = '';
        for (const line of message.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) eventData = line.slice(6);
        }

        if (!eventData) continue;
        const data = JSON.parse(eventData);

        if (eventType === 'status') {
          body.innerHTML = `<div class="plan-streaming"><span class="spinner"></span> ${esc(data.message)}</div>`;
        } else if (eventType === 'chunk' && !gotPlans) {
          body.innerHTML = '<div class="plan-streaming"><span class="spinner"></span> Claude is thinking...</div>';
        } else if (eventType === 'plans') {
          gotPlans = true;
          showPlanVariants(data.variants || []);
        } else if (eventType === 'error') {
          body.innerHTML = `<div class="plan-error">${esc(data.message)}</div>`;
        } else if (eventType === 'done') {
          // error event already displayed the message — only show generic if no error was shown
          if (data.error && !gotPlans && !body.querySelector('.plan-error')) {
            body.innerHTML = '<div class="plan-error">Plan generation failed. Try again.</div>';
          }
        }
      }
    }

    btn.disabled = false;
    btn.textContent = 'Generate Plan';
  }

  let selectedVariantIdx = null;
  let pendingVariants = [];

  function showPlanVariants(variants) {
    // Hide the streaming indicator in sidebar
    document.getElementById('plan-section').style.display = 'none';

    if (!variants.length) {
      document.getElementById('plan-body').innerHTML = '<div class="plan-error">No plan variants returned. Try again.</div>';
      document.getElementById('plan-section').style.display = '';
      return;
    }
    selectedVariantIdx = null;

    const modal = document.getElementById('plan-variants-modal');
    const body = document.getElementById('plan-variants-body');
    const saveBtn = document.getElementById('btn-save-plan');

    pendingVariants = variants;
    selectedVariantIdx = null;

    let html = '<div class="plan-variants-grid">';
    variants.forEach((v, i) => {
      html += `<div class="plan-variant" data-idx="${i}">`;
      html += `<h4>${esc(v.name)}</h4>`;
      html += `<div class="strategy">${esc(v.strategy)}</div>`;
      html += '<div class="slots">';
      const sortedTargets = Object.entries(v.targets || {}).sort(([a, ac], [b, bc]) => {
        if (a === 'lands') return -1;
        if (b === 'lands') return 1;
        return bc.count - ac.count;
      });
      for (const [tag, val] of sortedTargets) {
        const count = val.count;
        const label = val.label;
        const title = val.query ? ` title="${esc(val.query)}"` : '';
        html += `<span class="cat"${title}>${esc(label)}</span><span class="count">${count}</span>`;
      }
      html += '</div></div>';
    });
    html += '</div>';
    body.innerHTML = html;
    saveBtn.disabled = true;
    saveBtn.textContent = 'Save Selected Plan';
    modal.classList.add('active');

    // Wire up variant selection
    body.querySelectorAll('.plan-variant').forEach(el => {
      el.addEventListener('click', () => {
        body.querySelectorAll('.plan-variant').forEach(v => v.classList.remove('selected'));
        el.classList.add('selected');
        selectedVariantIdx = parseInt(el.dataset.idx);
        saveBtn.disabled = false;
      });
    });
  }

  async function savePlanVariant() {
    if (selectedVariantIdx === null || !pendingVariants.length) return;
    const chosen = pendingVariants[selectedVariantIdx];
    const saveBtn = document.getElementById('btn-save-plan');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    const res = await fetch(`/api/decks/${deck.id}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets: chosen.targets }),
    });
    if (res.ok) {
      currentPlanTargets = chosen.targets;
      planTargetTags = new Set(Object.keys(chosen.targets));
      const auditRes = await fetch(`/api/decks/${deck.id}/audit`);
      if (auditRes.ok) {
        const audit = await auditRes.json();
        planProgress = audit.plan_progress;
      }
      closeModal('plan-variants-modal');
      showPlanProgress(chosen.targets);
      document.getElementById('btn-generate-plan').style.display = 'none';
      updateDynamicButtons();
    } else {
      const err = await res.json();
      alert(err.error || 'Failed to save plan');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Selected Plan';
    }
  }

  // --- Autofill ---
  let autofillSuggestions = {};  // tag -> {cards: [...]}

  async function runAutofill() {
    document.getElementById('autofill-modal').classList.add('active');
    const body = document.getElementById('autofill-body');
    body.innerHTML = '<span class="spinner"></span> Finding cards for your plan...';
    document.getElementById('btn-autofill-add').disabled = true;

    let res;
    try {
      res = await fetch(`/api/decks/${deck.id}/autofill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset: true }),
      });
    } catch (_) {
      body.innerHTML = '<div style="color:var(--error)">Connection to server failed.</div>';
      return;
    }

    // Non-SSE error response (e.g. missing plan)
    if (res.headers.get('content-type')?.includes('application/json')) {
      const err = await res.json();
      body.innerHTML = `<div style="color:var(--error)">${esc(err.error || 'Unknown error')}</div>`;
      return;
    }

    // Parse SSE stream — render as soon as result arrives, don't wait for connection close
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let data = null;
    let finished = false;

    while (!finished) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      while (buffer.includes('\n\n')) {
        const idx = buffer.indexOf('\n\n');
        const message = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let eventType = 'message';
        let eventData = '';
        for (const line of message.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) eventData = line.slice(6);
        }
        if (!eventData) continue;
        const parsed = JSON.parse(eventData);

        if (eventType === 'status') {
          body.innerHTML = `<span class="spinner"></span> ${esc(parsed.message)}`;
        } else if (eventType === 'result') {
          data = parsed;
        } else if (eventType === 'error') {
          body.innerHTML = `<div style="color:var(--error)">${esc(parsed.message)}</div>`;
          reader.cancel();
          return;
        } else if (eventType === 'done') {
          finished = true;
        }
      }
    }
    reader.cancel();

    if (!data) {
      body.innerHTML = '<div style="color:var(--error)">No response from server.</div>';
      return;
    }

    autofillSuggestions = data.suggestions || {};
    const tags = Object.keys(autofillSuggestions);

    if (tags.length === 0) {
      body.innerHTML = '<div style="padding:12px;color:var(--text-secondary)">All plan targets are already met!</div>';
      return;
    }

    let html = '';
    if (data.unvalidated) {
      html += '<div class="autofill-warning">Suggestions are unvalidated (no API key). Some may not match their roles.</div>';
    }
    for (const tag of tags) {
      const group = autofillSuggestions[tag];
      const label = tag.replace(/-/g, ' ');
      html += `<div class="autofill-group">`;
      html += `<div class="autofill-tag-header">`;
      html += `<strong>${esc(label)}</strong>`;
      html += `<span style="color:var(--text-secondary);font-size:0.85rem">${group.current}/${group.target}</span>`;
      html += `</div>`;
      for (const card of group.cards) {
        html += `<label class="autofill-card">`;
        html += `<input type="checkbox" checked data-cid="${card.collection_id}" data-oracle-id="${card.oracle_id}" data-tag="${esc(tag)}">`;
        html += `<span class="autofill-card-name">${esc(card.name)}</span>`;
        html += `<span class="mana">${renderMana(card.mana_cost || '')}</span>`;
        html += `<span class="autofill-card-type">${esc(card.type_line || '')}</span>`;
        html += `<span class="autofill-card-set">${esc(card.set_code.toUpperCase())}</span>`;
        html += `</label>`;
      }
      html += `</div>`;
    }
    body.innerHTML = html;
    document.getElementById('btn-autofill-add').disabled = false;

    // Update button label with count
    updateAutofillCount();
    body.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', updateAutofillCount);
    });
  }

  function updateAutofillCount() {
    const checked = document.querySelectorAll('#autofill-body input[type="checkbox"]:checked');
    const btn = document.getElementById('btn-autofill-add');
    btn.textContent = `Add Selected (${checked.length})`;
    btn.disabled = checked.length === 0;
  }

  async function addAutofillCards() {
    const checked = document.querySelectorAll('#autofill-body input[type="checkbox"]:checked');
    let body;
    if (deck.hypothetical) {
      const oids = [];
      for (const cb of checked) { oids.push(cb.dataset.oracleId); }
      if (oids.length === 0) return;
      body = { oracle_ids: oids, zone: 'mainboard' };
    } else {
      const ids = [];
      for (const cb of checked) { ids.push(parseInt(cb.dataset.cid)); }
      if (ids.length === 0) return;
      body = { collection_ids: ids, zone: 'mainboard' };
    }

    const btn = document.getElementById('btn-autofill-add');
    btn.disabled = true;
    btn.textContent = 'Adding...';

    const res = await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const result = await res.json();
    if (result.error) { alert(result.error); btn.disabled = false; return; }

    closeModal('autofill-modal');

    // Refresh deck data
    const deckRes = await fetch(`/api/decks/${deck.id}`);
    deck = await deckRes.json();
    renderDeckDetail();
    await loadDeckCards();
    await loadPlan();  // Refresh plan progress
  }

  // --- Mana Curve ---

  const SUPERTYPE_COLORS = {
    Creature: '#4a9e4a',
    Instant: '#3b82c4',
    Sorcery: '#c44040',
    Artifact: '#8a8a8a',
    Enchantment: '#b06cc8',
    Planeswalker: '#d4a940',
    Battle: '#d47840',
    Land: '#8b6b47',
  };

  function getSupertype(typeLine) {
    if (!typeLine) return 'Other';
    for (const t of Object.keys(SUPERTYPE_COLORS)) {
      if (typeLine.includes(t)) return t;
    }
    return 'Other';
  }

  function openCurveModal() {
    document.getElementById('curve-modal').classList.add('active');

    // Exclude commanders and lands from the curve
    const cards = allDeckCards.filter(c =>
      c.deck_zone !== 'commander' && !(c.type_line || '').includes('Land')
    );

    // Build histogram: bucket -> { supertype -> count }
    const buckets = {};
    const supertypesUsed = new Set();
    for (const c of cards) {
      const cmc = Math.min(parseInt(c.cmc || 0) || 0, 7);
      const label = cmc >= 7 ? '7+' : String(cmc);
      const st = getSupertype(c.type_line);
      supertypesUsed.add(st);
      if (!buckets[label]) buckets[label] = {};
      buckets[label][st] = (buckets[label][st] || 0) + 1;
    }

    const labels = ['0', '1', '2', '3', '4', '5', '6', '7+'];
    // Stack order: most common supertypes first
    const stOrder = Object.keys(SUPERTYPE_COLORS).filter(s => supertypesUsed.has(s));
    if (supertypesUsed.has('Other')) stOrder.push('Other');

    // Find max total for scaling
    let maxTotal = 0;
    for (const l of labels) {
      let total = 0;
      for (const st of stOrder) total += (buckets[l] || {})[st] || 0;
      if (total > maxTotal) maxTotal = total;
    }
    if (maxTotal === 0) maxTotal = 1;

    const barMaxH = 160;
    const barW = 40;
    const gap = 8;
    const chartW = labels.length * (barW + gap);

    let svg = `<svg width="${chartW}" height="${barMaxH + 30}" style="display:block;margin:0 auto">`;
    for (let i = 0; i < labels.length; i++) {
      const l = labels[i];
      const x = i * (barW + gap);
      const data = buckets[l] || {};
      let y = barMaxH;

      // Stack segments bottom-up
      for (const st of stOrder) {
        const count = data[st] || 0;
        if (count === 0) continue;
        const h = (count / maxTotal) * barMaxH;
        y -= h;
        const color = SUPERTYPE_COLORS[st] || '#666';
        svg += `<rect x="${x}" y="${y}" width="${barW}" height="${h}" fill="${color}" rx="2"/>`;
      }

      // Total count label above bar
      let total = 0;
      for (const st of stOrder) total += data[st] || 0;
      if (total > 0) {
        svg += `<text x="${x + barW / 2}" y="${y - 4}" text-anchor="middle" fill="var(--text-secondary)" font-size="12" font-weight="600">${total}</text>`;
      }

      // X-axis label
      svg += `<text x="${x + barW / 2}" y="${barMaxH + 18}" text-anchor="middle" fill="var(--text-secondary)" font-size="13">${l}</text>`;
    }
    svg += '</svg>';

    document.getElementById('curve-chart').innerHTML = svg;

    // Legend
    let legend = '';
    for (const st of stOrder) {
      const color = SUPERTYPE_COLORS[st] || '#666';
      legend += `<span class="curve-legend-item"><span class="curve-legend-swatch" style="background:${color}"></span>${esc(st)}</span>`;
    }
    document.getElementById('curve-legend').innerHTML = legend;
  }

  // --- Weights ---

  const WEIGHT_LABELS = {
    edhrec: { label: 'EDHREC', desc: () => {
      const cmds = allDeckCards.filter(c => c.deck_zone === 'commander');
      const name = cmds.length > 0 ? cmds[0].name : 'your commander';
      return `Raise to choose more cards that are popular on EDHREC with ${name}`;
    }},
    salt: { label: 'Salt', desc: () => 'Raise to choose fewer annoying cards (according to EDHREC\'s "salt" score)' },
    price: { label: 'Price', desc: () => 'Raise to choose more expensive cards' },
    plan_overlap: { label: 'Plan overlap', desc: () => 'Raise to choose more cards that overlap with the Deck Plan' },
    novelty: { label: 'Novelty', desc: () => 'Raise to choose more cards that have low popularity on EDHREC' },
    bling: { label: 'Bling', desc: () => 'Raise to choose more cards from your collection that are full-art, borderless, showcase, etc.' },
    rarity: { label: 'Rarity', desc: () => 'Raise to choose more rare and mythic cards over commons and uncommons' },
    random: { label: 'Random', desc: () => 'Raise to choose cards more randomly' },
  };
  const WEIGHT_ORDER = ['edhrec', 'salt', 'price', 'plan_overlap', 'novelty', 'bling', 'rarity', 'random'];
  const DEFAULT_WEIGHTS = { edhrec: 3, salt: 2, price: 1, plan_overlap: 3, novelty: 3, bling: 4, rarity: 3, random: 0 };
  let currentWeights = null;

  async function openWeightsModal() {
    document.getElementById('weights-modal').classList.add('active');
    const body = document.getElementById('weights-body');
    body.innerHTML = '<span class="spinner"></span> Loading...';

    const res = await fetch(`/api/decks/${deck.id}/weights`);
    if (!res.ok) {
      body.innerHTML = '<div style="color:var(--error)">Failed to load weights.</div>';
      return;
    }
    currentWeights = await res.json();
    renderWeightsBody();
  }

  function renderWeightsBody() {
    const body = document.getElementById('weights-body');
    let html = '';
    for (const key of WEIGHT_ORDER) {
      const info = WEIGHT_LABELS[key];
      const val = currentWeights[key] ?? DEFAULT_WEIGHTS[key];
      html += `<div class="weight-row">
        <div class="weight-row-top">
          <span class="weight-label">${esc(info.label)}</span>
          <div class="weight-controls">
            <button class="weight-btn" data-key="${key}" data-dir="-1" ${val <= 0 ? 'disabled' : ''}>&minus;</button>
            <span class="weight-value" id="wv-${key}">${val}</span>
            <button class="weight-btn" data-key="${key}" data-dir="1" ${val >= 10 ? 'disabled' : ''}>+</button>
          </div>
        </div>
        <div class="weight-desc">${esc(info.desc())}</div>
      </div>`;
    }
    body.innerHTML = html;
    body.querySelectorAll('.weight-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.key;
        const dir = parseInt(btn.dataset.dir);
        const newVal = Math.max(0, Math.min(10, (currentWeights[key] ?? DEFAULT_WEIGHTS[key]) + dir));
        currentWeights[key] = newVal;
        renderWeightsBody();
      });
    });
  }

  async function saveWeights() {
    const btn = document.getElementById('btn-weights-save');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const res = await fetch(`/api/decks/${deck.id}/weights`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentWeights),
    });
    if (res.ok) {
      closeModal('weights-modal');
    } else {
      const err = await res.json();
      alert(err.error || 'Failed to save weights');
    }
    btn.disabled = false;
    btn.textContent = 'Save';
  }

  function resetWeights() {
    currentWeights = { ...DEFAULT_WEIGHTS };
    renderWeightsBody();
  }

  // --- Fill Lands ---

  const MANA_COLORS = { W: '#f9faf4', U: '#0e68ab', B: '#150b00', R: '#d3202a', G: '#00733e' };
  const BASIC_LAND_NAMES = { W: 'Plains', U: 'Island', B: 'Swamp', R: 'Mountain', G: 'Forest' };

  // Fill-lands state
  let fillLandsNonbasic = [];
  let fillLandsBasic = [];
  let fillLandsPipFractions = {};

  async function runFillLands() {
    document.getElementById('fill-lands-modal').classList.add('active');
    const body = document.getElementById('fill-lands-body');
    body.innerHTML = '<span class="spinner"></span> Finding lands...';
    document.getElementById('btn-fill-lands-add').disabled = true;

    let res;
    try {
      res = await fetch(`/api/decks/${deck.id}/fill-lands`, { method: 'POST' });
    } catch (_) {
      body.innerHTML = '<div style="color:var(--error)">Connection to server failed.</div>';
      return;
    }

    const data = await res.json();
    if (data.error) {
      body.innerHTML = `<div style="color:var(--error)">${esc(data.error)}</div>`;
      return;
    }

    fillLandsNonbasic = data.suggestions?.nonbasic || [];
    fillLandsBasic = data.suggestions?.basic || [];
    fillLandsPipFractions = data.pip_fractions || {};

    if (fillLandsNonbasic.length === 0 && fillLandsBasic.length === 0) {
      body.innerHTML = '<div style="padding:12px;color:var(--text-secondary)">No lands needed — deck has enough lands already.</div>';
      return;
    }

    renderFillLandsBody(data);
  }

  function renderFillLandsBody(data) {
    const body = document.getElementById('fill-lands-body');
    const totalCount = fillLandsNonbasic.length + fillLandsBasic.reduce((a, b) => a + b.count, 0);

    let html = `<div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px">` +
      `Lands: ${data.existing_lands}/${data.land_target} — suggesting ${totalCount} lands</div>`;

    if (fillLandsNonbasic.length > 0) {
      html += '<div class="fill-lands-section-label">Nonbasic Lands</div>';
      html += '<div class="card-grid fill-lands-grid">';
      for (const land of fillLandsNonbasic) {
        const rarityColor = getRarityColor(land.rarity);
        const foilClass = (land.finish === 'foil' || land.finish === 'etched') ? ' foil' : '';
        const dots = (land.produced_mana || []).map(c =>
          `<span class="land-mana-dot" style="background:${MANA_COLORS[c] || '#888'}"></span>`
        ).join('');
        html += `<div class="sheet-card fill-land-card" data-cid="${land.collection_id}">
          <div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:#111">
            <img src="${land.image_uri || ''}" alt="${esc(land.name)}" loading="lazy">
            <button class="fill-land-remove" title="Replace with basic">&times;</button>
          </div>
          <div class="fill-land-colors">${dots}</div>
        </div>`;
      }
      html += '</div>';
    }

    if (fillLandsBasic.length > 0) {
      html += '<div class="fill-lands-section-label">Basic Lands</div>';
      html += '<div class="fill-lands-basics">';
      for (const group of fillLandsBasic) {
        html += `<span class="fill-lands-basic-pill">${esc(group.name)} &times;${group.count}</span>`;
      }
      html += '</div>';
    }

    body.innerHTML = html;
    document.getElementById('btn-fill-lands-add').disabled = false;
    document.getElementById('btn-fill-lands-add').textContent = `Add All (${totalCount})`;

    // Wire X buttons on nonbasics
    body.querySelectorAll('.fill-land-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.fill-land-card');
        const cid = parseInt(card.dataset.cid);
        removeNonbasicLand(cid, data);
      });
    });
  }

  function removeNonbasicLand(collectionId, data) {
    // Find and remove the nonbasic
    const idx = fillLandsNonbasic.findIndex(l => l.collection_id === collectionId);
    if (idx === -1) return;
    fillLandsNonbasic.splice(idx, 1);

    // Add one basic land — pick the color with the highest pip fraction
    // that has the fewest basics relative to its fraction
    const currentBasicCounts = {};
    const totalBasics = fillLandsBasic.reduce((a, b) => a + b.count, 0);
    for (const g of fillLandsBasic) {
      for (const [color, name] of Object.entries(BASIC_LAND_NAMES)) {
        if (g.name === name) currentBasicCounts[color] = (currentBasicCounts[color] || 0) + g.count;
      }
    }

    // Pick color most underrepresented vs pip fraction
    let bestColor = null;
    let bestDeficit = -Infinity;
    for (const [color, frac] of Object.entries(fillLandsPipFractions)) {
      const current = currentBasicCounts[color] || 0;
      const expected = frac * (totalBasics + 1);
      const deficit = expected - current;
      if (deficit > bestDeficit) {
        bestDeficit = deficit;
        bestColor = color;
      }
    }

    if (bestColor) {
      const name = BASIC_LAND_NAMES[bestColor];
      const existing = fillLandsBasic.find(g => g.name === name);
      if (existing) {
        existing.count++;
      } else {
        fillLandsBasic.push({ name, count: 1, collection_ids: [] });
      }
    }

    renderFillLandsBody(data);
  }

  async function addFillLandsCards() {
    let body;
    if (deck.hypothetical) {
      const oids = fillLandsNonbasic.map(l => l.oracle_id);
      for (const g of fillLandsBasic) {
        if (g.count > 0 && g.oracle_id) {
          for (let i = 0; i < g.count; i++) oids.push(g.oracle_id);
        }
      }
      if (oids.length === 0) return;
      body = { oracle_ids: oids, zone: 'mainboard' };
    } else {
      const ids = fillLandsNonbasic.map(l => l.collection_id);
      for (const g of fillLandsBasic) {
        if (g.count > 0 && g.collection_ids) {
          ids.push(...g.collection_ids.slice(0, g.count));
        }
      }
      if (ids.length === 0) return;
      body = { collection_ids: ids, zone: 'mainboard' };
    }

    const btn = document.getElementById('btn-fill-lands-add');

    const res = await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const result = await res.json();
    if (result.error) { alert(result.error); btn.disabled = false; return; }

    closeModal('fill-lands-modal');

    const deckRes = await fetch(`/api/decks/${deck.id}`);
    deck = await deckRes.json();
    renderDeckDetail();
    await loadDeckCards();
    await loadPlan();
  }

  async function clearPlan() {
    if (!confirm('Clear the deck plan?')) return;
    await fetch(`/api/decks/${deck.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: null }),
    });
    document.getElementById('plan-section').style.display = 'none';
    document.getElementById('plan-body').innerHTML = '';
  }

  // --- Plan Editing ---
  function enterPlanEditMode() {
    if (!currentPlanTargets) return;
    const body = document.getElementById('plan-body');

    // Sort same as display: lands first, then alphabetical
    const sorted = Object.entries(currentPlanTargets).sort(([a], [b]) => {
      if (a === 'lands') return -1;
      if (b === 'lands') return 1;
      return a.localeCompare(b);
    });

    let html = '<div class="plan-edit">';
    for (const [tag, target] of sorted) {
      const isQuery = target.type === 'query';
      html += `<div class="plan-edit-row" data-original-tag="${esc(tag)}">`;
      html += `<input type="text" class="plan-edit-tag" value="${esc(isQuery ? target.label : tag)}" placeholder="tag name"${isQuery ? ' readonly title="Custom query — rename not supported"' : ''}>`;
      html += `<input type="number" class="plan-edit-count" value="${target.count}" min="0" max="99">`;
      html += `<button class="plan-edit-delete" title="Remove">&times;</button>`;
      html += `</div>`;
    }
    html += `<div class="plan-edit-row plan-edit-add">`;
    html += `<input type="text" class="plan-edit-tag" placeholder="new tag name">`;
    html += `<input type="number" class="plan-edit-count" value="3" min="0" max="99">`;
    html += `<button class="secondary plan-edit-add-btn" title="Add">+</button>`;
    html += `</div>`;
    html += `<div class="plan-edit-actions">`;
    html += `<button id="btn-save-plan-edit">Save</button>`;
    html += `<button class="secondary" id="btn-cancel-plan-edit">Cancel</button>`;
    html += `</div>`;
    html += '</div>';
    body.innerHTML = html;

    // Hide header buttons during edit
    document.getElementById('btn-edit-plan').style.display = 'none';

    // Wire delete buttons
    body.querySelectorAll('.plan-edit-delete').forEach(btn => {
      btn.addEventListener('click', () => btn.closest('.plan-edit-row').remove());
    });

    // Wire add button
    body.querySelector('.plan-edit-add-btn').addEventListener('click', () => {
      const addRow = body.querySelector('.plan-edit-add');
      const tagInput = addRow.querySelector('.plan-edit-tag');
      const countInput = addRow.querySelector('.plan-edit-count');
      const tag = tagInput.value.trim();
      if (!tag) return;

      // Insert new row before the add row
      const newRow = document.createElement('div');
      newRow.className = 'plan-edit-row';
      newRow.dataset.originalTag = tag;
      newRow.innerHTML = `<input type="text" class="plan-edit-tag" value="${esc(tag)}" placeholder="tag name">` +
        `<input type="number" class="plan-edit-count" value="${countInput.value}" min="0" max="99">` +
        `<button class="plan-edit-delete" title="Remove">&times;</button>`;
      newRow.querySelector('.plan-edit-delete').addEventListener('click', () => newRow.remove());
      addRow.parentNode.insertBefore(newRow, addRow);

      // Reset add row
      tagInput.value = '';
      countInput.value = '3';
      tagInput.focus();
    });

    // Save
    body.querySelector('#btn-save-plan-edit').addEventListener('click', savePlanEdit);
    // Cancel
    body.querySelector('#btn-cancel-plan-edit').addEventListener('click', () => {
      showPlanProgress(currentPlanTargets);
    });
  }

  async function savePlanEdit() {
    const body = document.getElementById('plan-body');
    const rows = body.querySelectorAll('.plan-edit-row:not(.plan-edit-add)');
    const targets = {};
    for (const row of rows) {
      const count = parseInt(row.querySelector('.plan-edit-count').value) || 0;
      if (count <= 0) continue;
      const originalTag = row.dataset.originalTag;
      const originalTarget = currentPlanTargets && currentPlanTargets[originalTag];
      if (originalTarget && originalTarget.type === 'query') {
        // Preserve custom query target, only update count
        targets[originalTag] = { ...originalTarget, count };
      } else {
        const tag = row.querySelector('.plan-edit-tag').value.trim();
        if (tag) {
          const type = tag === 'lands' ? 'lands' : 'tag';
          targets[tag] = { count, label: tag === 'lands' ? 'lands' : tag.replace(/-/g, ' '), type };
        }
      }
    }

    if (Object.keys(targets).length === 0) {
      alert('Plan must have at least one tag target.');
      return;
    }

    const res = await fetch(`/api/decks/${deck.id}/plan`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || 'Failed to save plan');
      return;
    }

    // Refresh
    currentPlanTargets = targets;
    planTargetTags = new Set(Object.keys(targets));
    // Re-fetch audit for updated progress
    const auditRes = await fetch(`/api/decks/${deck.id}/audit`);
    if (auditRes.ok) {
      const audit = await auditRes.json();
      planProgress = audit.plan_progress;
    }
    showPlanProgress(targets);
    renderCards();  // Update role labels
  }

  // --- Replacement modal ---
  let replaceCollectionId = null;
  let replaceOracleId = null;
  let replaceSelectedCandidate = null;

  async function openReplaceModal(collectionId, cardName, oracleId) {
    replaceCollectionId = collectionId;
    replaceOracleId = oracleId || null;
    replaceSelectedCandidate = null;
    document.getElementById('replace-card-name').textContent = cardName;
    document.getElementById('replace-card-roles').innerHTML = '';
    document.getElementById('replace-confirm').disabled = true;
    document.getElementById('replace-selection-label').textContent = 'No card selected';
    replaceCandidateData = { role: [], type: [], search: [] };
    // Reset to Role tab
    replaceActiveTab = 'role';
    document.querySelectorAll('.replace-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === 'role'));
    document.getElementById('replace-search-form').style.display = 'none';
    renderReplaceGrid([]);
    document.getElementById('replace-grid').innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">Loading...</div>';
    document.getElementById('replace-modal').classList.add('active');

    const queryParam = deck.hypothetical
      ? `oracle_id=${encodeURIComponent(oracleId)}`
      : `collection_id=${collectionId}`;
    const res = await fetch(`/api/decks/${encodeURIComponent(deckId)}/replacements?${queryParam}`);
    if (!res.ok) {
      document.getElementById('replace-grid').innerHTML = '<div style="padding:24px;color:#e74c3c;text-align:center;grid-column:1/-1">Failed to load</div>';
      return;
    }
    const data = await res.json();
    const cardRoles = (data.card.tags || []);
    if (cardRoles.length) {
      document.getElementById('replace-card-roles').innerHTML = cardRoles.map(r => `<span class="replace-role-pill">${esc(r)}</span>`).join('');
    }
    replaceCandidateData.role = data.role_suggestions || [];
    replaceCandidateData.type = data.type_suggestions || [];
    renderReplaceGrid(replaceCandidateData[replaceActiveTab]);

    // Pre-fill search inputs from card data
    document.getElementById('rs-name').value = '';
    document.getElementById('rs-cmc').value = data.card.cmc != null ? Math.floor(data.card.cmc) : '';
    document.getElementById('rs-set').value = '';
    const tl = data.card.type_line || '';
    const dashIdx = tl.indexOf('\u2014');
    document.getElementById('rs-type').value = (dashIdx >= 0 ? tl.substring(0, dashIdx).trim() : tl).split(' ').find(w =>
      ['Creature','Artifact','Enchantment','Instant','Sorcery','Planeswalker'].includes(w)
    ) || '';
  }

  function renderReplaceGrid(candidates) {
    const grid = document.getElementById('replace-grid');
    if (!candidates || candidates.length === 0) {
      grid.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">No candidates found</div>';
      return;
    }
    grid.innerHTML = candidates.map(c => {
      const tags = (c.tags || '').split(',').filter(t => t && planTargetTags.has(t));
      const rolesText = tags.map(t => {
        const val = currentPlanTargets && currentPlanTargets[t];
        return val ? val.label : t.replace(/-/g, ' ');
      }).join(', ');
      const rarityColor = getRarityColor(c.rarity);
      const foilClass = (c.finish === 'foil' || c.finish === 'etched') ? ' foil' : '';
      return `<div class="sheet-card replace-candidate" data-cid="${c.collection_id}" data-name="${esc(c.name)}">
        <div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:#111">
          <img src="${c.image_uri || ''}" alt="${esc(c.name)}" loading="lazy">
          ${rolesText ? `<span class="role-overlay" style="opacity:1">${esc(rolesText)}</span>` : ''}
        </div>
      </div>`;
    }).join('');

    grid.querySelectorAll('.replace-candidate').forEach(el => {
      el.addEventListener('click', () => selectReplaceCandidate(el));
    });
  }

  function selectReplaceCandidate(el) {
    document.querySelectorAll('.replace-candidate.selected').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    replaceSelectedCandidate = {
      collection_id: parseInt(el.dataset.cid),
      name: el.dataset.name,
    };
    document.getElementById('replace-selection-label').textContent = replaceSelectedCandidate.name;
    document.getElementById('replace-confirm').disabled = false;
  }

  async function searchReplacements() {
    const name = document.getElementById('rs-name').value.trim();
    const cmc = document.getElementById('rs-cmc').value.trim();
    const set = document.getElementById('rs-set').value.trim();
    const type = document.getElementById('rs-type').value.trim();
    const tag = document.getElementById('rs-tag').value.trim();

    const params = new URLSearchParams({ status: 'owned' });
    if (name) params.set('q', name);
    if (cmc) params.set('cmc', cmc);
    if (set) params.set('filter_set', set);
    if (type) params.set('type', type);
    if (tag) params.set('filter_tag', tag);

    // Get commander CI for filtering
    const commanders = deckCards.filter(c => c.deck_zone === 'commander');
    if (commanders.length > 0) {
      const ci = new Set();
      commanders.forEach(c => {
        try { JSON.parse(c.color_identity || '[]').forEach(col => ci.add(col)); } catch(e) {}
      });
      if (ci.size > 0) params.set('ci_colors', [...ci].join(''));
    }
    params.set('exclude_deck_id', deckId);

    const grid = document.getElementById('replace-grid');
    grid.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">Searching...</div>';

    const res = await fetch(`/api/collection?${params}`);
    if (!res.ok) {
      grid.innerHTML = '<div style="padding:24px;color:#e74c3c;text-align:center;grid-column:1/-1">Search failed</div>';
      return;
    }
    const cards = await res.json();
    replaceCandidateData.search = cards.filter(c => c.collection_id).map(c => ({
      collection_id: c.collection_id,
      name: c.name,
      mana_cost: c.mana_cost,
      image_uri: c.image_uri,
      rarity: c.rarity,
      finish: c.finish,
      tags: (c.card_tags || []).join(','),
    }));
    renderReplaceGrid(replaceCandidateData.search);
  }

  async function confirmReplacement() {
    if (!replaceSelectedCandidate) return;

    let body;
    if (deck.hypothetical) {
      if (!replaceOracleId) return;
      const card = deckCards.find(c => c.oracle_id === replaceOracleId);
      const zone = card ? (card.deck_zone || 'mainboard') : 'mainboard';
      body = {
        remove_oracle_id: replaceOracleId,
        add_oracle_id: replaceSelectedCandidate.oracle_id,
        zone: zone,
      };
    } else {
      if (!replaceCollectionId) return;
      const card = deckCards.find(c => c.id === replaceCollectionId);
      const zone = card ? (card.deck_zone || 'mainboard') : 'mainboard';
      body = {
        remove_collection_id: replaceCollectionId,
        add_collection_id: replaceSelectedCandidate.collection_id,
        zone: zone,
      };
    }

    const res = await fetch(`/api/decks/${encodeURIComponent(deckId)}/replace`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || 'Replacement failed');
      return;
    }
    closeModal('replace-modal');
    loadDeckCards();
  }

  // --- Utils ---
  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }

  // --- Initial render ---
  renderDeckDetail();
  loadPlan();
  fetch('/api/settings').then(r => r.json()).then(s => {
    currentView = s.default_card_view || 'grid';
    updateViewButtons();
    loadDeckCards();
  });
})();
