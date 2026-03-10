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
  let currentZone = 'mainboard';
  let deckCards = [];
  let selectedCardIds = new Set();
  let pickerSelected = new Set();
  let editingDeckId = null;
  let activeRoleFilter = null;
  let currentView = 'table';
  const COL_MIN = 1, COL_MAX = 12;
  let gridCols = parseInt(localStorage.getItem('deckGridCols'))
    || (window.innerWidth < 600 ? 2 : 6);

  // Build the page
  const layout = document.getElementById('deck-detail-layout');
  layout.innerHTML = `
    <div class="deck-detail-header">
      <div class="info">
        <h2 id="deck-name"></h2>
        <div class="deck-meta-grid" id="deck-meta"></div>
      </div>
      <div class="actions">
        <button class="secondary" id="btn-edit">Edit</button>
        <button id="btn-generate-plan" style="display:none">Generate Plan</button>
        <button id="btn-autofill" style="display:none">Autofill</button>
        <button id="btn-add-cards">Add Cards</button>
        <button class="secondary" id="btn-remove-selected">Remove Selected</button>
        <button class="secondary" id="btn-import-expected">Import Expected List</button>
        <button class="danger" id="btn-delete">Delete Deck</button>
      </div>
    </div>

    <div class="plan-section" id="plan-section" style="display:none">
      <div class="plan-header">
        <h3>Deck Plan</h3>
        <button class="secondary" id="btn-clear-plan" style="display:none;font-size:0.8rem;padding:4px 10px">Clear Plan</button>
      </div>
      <div class="plan-body" id="plan-body"></div>
    </div>

    <div class="deck-view-bar">
      <div class="zone-tabs" id="zone-tabs">
        <div class="tab active" data-zone="mainboard">Mainboard <span id="count-mainboard"></span></div>
        <div class="tab" data-zone="sideboard">Sideboard <span id="count-sideboard"></span></div>
        <div class="tab" data-zone="commander">Commander <span id="count-commander"></span></div>
      </div>
      <div class="deck-view-controls">
        <div class="view-toggle-group">
          <button class="secondary active" id="view-table-btn" title="Table view">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <rect x="1" y="1" width="14" height="3" rx="1"/>
              <rect x="1" y="6" width="14" height="3" rx="1"/>
              <rect x="1" y="11" width="14" height="3" rx="1"/>
            </svg>
          </button>
          <button class="secondary" id="view-grid-btn" title="Grid view">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <rect x="1" y="1" width="6" height="6" rx="1"/>
              <rect x="9" y="1" width="6" height="6" rx="1"/>
              <rect x="1" y="9" width="6" height="6" rx="1"/>
              <rect x="9" y="9" width="6" height="6" rx="1"/>
            </svg>
          </button>
        </div>
        <div class="col-controls" id="grid-size-wrap" style="display:none">
          <button class="col-btn" id="col-minus">&minus;</button>
          <div class="col-count" id="col-count"></div>
          <button class="col-btn" id="col-plus">+</button>
        </div>
      </div>
    </div>

    <div id="active-filter-banner" class="active-filter-banner" style="display:none"></div>

    <div id="card-display">
    <table class="card-table" id="card-table">
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
    <div class="card-grid" id="card-grid" style="display:none"></div>
    </div>

    <div class="completeness-section" id="completeness-section" style="display:none">
      <div class="completeness-header" id="completeness-header">
        <h3>Expected Cards <span id="completeness-summary"></span></h3>
        <span id="completeness-toggle">&#9660;</span>
      </div>
      <div class="completeness-body" id="completeness-body"></div>
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
  `;

  // --- Wire up event handlers ---

  // Zone tabs
  document.querySelectorAll('#zone-tabs .tab').forEach(tab => {
    tab.addEventListener('click', () => switchZone(tab.dataset.zone));
  });

  // Select all checkbox
  document.getElementById('select-all').addEventListener('change', function() {
    deckCards.forEach(c => {
      if (this.checked) selectedCardIds.add(c.id);
      else selectedCardIds.delete(c.id);
    });
    renderCards();
  });

  // Header buttons
  document.getElementById('btn-edit').addEventListener('click', showEditModal);
  document.getElementById('btn-generate-plan').addEventListener('click', generatePlan);
  document.getElementById('btn-autofill').addEventListener('click', runAutofill);
  document.getElementById('btn-add-cards').addEventListener('click', showAddCardsModal);
  document.getElementById('btn-remove-selected').addEventListener('click', removeSelectedCards);
  document.getElementById('btn-import-expected').addEventListener('click', showExpectedModal);
  document.getElementById('btn-delete').addEventListener('click', deleteDeck);
  document.getElementById('btn-clear-plan').addEventListener('click', clearPlan);

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
  });
  document.getElementById('view-grid-btn').addEventListener('click', () => {
    currentView = 'grid';
    updateViewButtons();
    renderCards();
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
    localStorage.setItem('deckGridCols', gridCols);
  }
  document.getElementById('col-minus').addEventListener('click', () => {
    if (gridCols > COL_MIN) { gridCols--; applyGridCols(); if (currentView === 'grid') renderCards(); }
  });
  document.getElementById('col-plus').addEventListener('click', () => {
    if (gridCols < COL_MAX) { gridCols++; applyGridCols(); if (currentView === 'grid') renderCards(); }
  });
  applyGridCols();

  // Grid card click — navigate to card detail
  document.getElementById('card-grid').addEventListener('click', e => {
    const card = e.target.closest('.sheet-card');
    if (card) window.location.href = `/card/${card.dataset.sc}/${card.dataset.cn}`;
  });

  // Close modals on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target === el) el.classList.remove('active');
    });
  });

  // --- Render deck detail header ---
  function renderDeckDetail() {
    document.getElementById('deck-name').textContent = deck.name;
    document.title = `${deck.name} — DeckDumpster`;
    const meta = [];
    if (deck.format) meta.push(`<span class="label">Format</span><span>${esc(deck.format)}</span>`);
    if (deck.is_precon) meta.push(`<span class="label">Type</span><span>Preconstructed</span>`);
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

  // --- Zone switching ---
  function switchZone(zone) {
    currentZone = zone;
    selectedCardIds.clear();
    document.getElementById('select-all').checked = false;
    document.querySelectorAll('#zone-tabs .tab').forEach(t => {
      t.classList.toggle('active', t.dataset.zone === zone);
    });
    loadDeckCards();
  }

  // --- Load and render cards ---
  async function loadDeckCards() {
    const res = await fetch(`/api/decks/${deck.id}/cards`);
    const allCards = await res.json();

    const counts = { mainboard: 0, sideboard: 0, commander: 0 };
    allCards.forEach(c => { if (counts[c.deck_zone] !== undefined) counts[c.deck_zone]++; });
    document.getElementById('count-mainboard').textContent = `(${counts.mainboard})`;
    document.getElementById('count-sideboard').textContent = `(${counts.sideboard})`;
    document.getElementById('count-commander').textContent = `(${counts.commander})`;

    deckCards = allCards.filter(c => c.deck_zone === currentZone);
    renderCards();
  }

  function getFilteredCards() {
    if (!activeRoleFilter) return deckCards;
    return deckCards.filter(c => {
      const tags = c.tags ? c.tags.split(',') : [];
      return tags.includes(activeRoleFilter);
    });
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
    tbody.innerHTML = cards.map(c => {
      const sc = c.set_code.toLowerCase();
      const cn = c.collector_number;
      const tags = c.tags ? c.tags.split(',') : [];
      const role = tags.filter(t => planTargetTags.has(t)).map(t => t.replace(/-/g, ' ')).join(', ');
      return `<tr>
        <td><input type="checkbox" data-id="${c.id}" ${selectedCardIds.has(c.id) ? 'checked' : ''}></td>
        <td><a href="/card/${esc(sc)}/${esc(cn)}">${esc(c.name)}</a></td>
        <td class="role-cell">${esc(role)}</td>
        <td>${esc(c.set_code.toUpperCase())} #${esc(cn)}</td>
        <td class="mana">${renderMana(c.mana_cost || '')}</td>
        <td>${esc(c.type_line || '')}</td>
        <td>${esc(c.finish)}</td>
        <td>${esc(c.condition)}</td>
      </tr>`;
    }).join('');

    // Wire up checkbox change handlers
    tbody.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', function() {
        const id = parseInt(this.dataset.id);
        if (this.checked) selectedCardIds.add(id);
        else selectedCardIds.delete(id);
      });
    });
  }

  function renderGrid(cards) {
    const grid = document.getElementById('card-grid');
    if (cards.length === 0) {
      grid.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center">No cards in this zone</div>';
      return;
    }
    const gap = 10;
    const containerWidth = grid.clientWidth || document.getElementById('card-display').clientWidth || 800;
    const cardWidth = Math.floor((containerWidth - (gridCols - 1) * gap) / gridCols);

    grid.innerHTML = cards.map(c => {
      const sc = c.set_code.toLowerCase();
      const cn = c.collector_number;
      const rarityColor = getRarityColor(c.rarity);
      const foilClass = (c.finish === 'foil' || c.finish === 'etched') ? ' foil' : '';
      return `<div class="sheet-card" data-sc="${esc(sc)}" data-cn="${esc(cn)}" style="width:${cardWidth}px">
        <div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:#111">
          <img src="${c.image_uri || ''}" alt="${esc(c.name)}" loading="lazy">
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
    await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: ids }),
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

  // --- Plan ---
  let planProgress = null;  // {tag: {current, target}} from audit
  let planTargetTags = new Set();  // tags from current plan targets

  async function loadPlan() {
    // Show Generate Plan button for Commander decks
    if (deck.format === 'commander') {
      document.getElementById('btn-generate-plan').style.display = '';
    }

    const res = await fetch(`/api/decks/${deck.id}/plan`);
    const plan = await res.json();
    if (plan && plan.targets) {
      planTargetTags = new Set(Object.keys(plan.targets));
      // Fetch audit for real progress counts
      const auditRes = await fetch(`/api/decks/${deck.id}/audit`);
      if (auditRes.ok) {
        const audit = await auditRes.json();
        planProgress = audit.plan_progress;
      }
      showPlanProgress(plan.targets);
      document.getElementById('btn-autofill').style.display = '';
    }
  }

  function showPlanProgress(targets) {
    const section = document.getElementById('plan-section');
    const body = document.getElementById('plan-body');
    section.style.display = '';
    document.getElementById('btn-clear-plan').style.display = '';

    // Sort: "lands" first, then alphabetical
    const sorted = Object.entries(targets).sort(([a], [b]) => {
      if (a === 'lands') return -1;
      if (b === 'lands') return 1;
      return a.localeCompare(b);
    });

    let html = '<div class="plan-progress">';
    for (const [tag, target] of sorted) {
      const label = tag.replace(/-/g, ' ');
      const current = (planProgress && planProgress[tag]) ? planProgress[tag].current : 0;
      const pct = target > 0 ? Math.min((current / target) * 100, 100) : 0;
      const cls = current >= target ? 'met' : 'under';
      const activeClass = activeRoleFilter === tag ? ' active' : '';
      html += `<span class="cat clickable${activeClass}" data-tag="${esc(tag)}">${esc(label)}</span>`;
      html += `<span class="bar-cell"><div class="bar"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div></span>`;
      html += `<span class="counts">${current}/${target}</span>`;
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
          if (data.error && !gotPlans) {
            body.innerHTML = '<div class="plan-error">Plan generation failed. Try again.</div>';
          }
        }
      }
    }

    btn.disabled = false;
    btn.textContent = 'Generate Plan';
  }

  let selectedVariantIdx = null;

  function showPlanVariants(variants) {
    const body = document.getElementById('plan-body');
    if (!variants.length) {
      body.innerHTML = '<div class="plan-error">No plan variants returned. Try again.</div>';
      return;
    }
    selectedVariantIdx = null;

    let html = '<div class="plan-variants">';
    variants.forEach((v, i) => {
      html += `<div class="plan-variant" data-idx="${i}">`;
      html += `<h4>${esc(v.name)}</h4>`;
      html += `<div class="strategy">${esc(v.strategy)}</div>`;
      html += '<div class="slots">';
      // Sort: lands first, then by count descending
      const sortedTargets = Object.entries(v.targets || {}).sort(([a, ac], [b, bc]) => {
        if (a === 'lands') return -1;
        if (b === 'lands') return 1;
        return bc - ac;
      });
      for (const [tag, count] of sortedTargets) {
        const label = tag.replace(/-/g, ' ');
        html += `<span class="cat">${esc(label)}</span><span class="count">${count}</span>`;
      }
      html += '</div></div>';
    });
    html += '</div>';
    html += '<div class="plan-actions"><button id="btn-save-plan" disabled>Save Selected Plan</button></div>';
    body.innerHTML = html;

    // Wire up variant selection
    body.querySelectorAll('.plan-variant').forEach(el => {
      el.addEventListener('click', () => {
        body.querySelectorAll('.plan-variant').forEach(v => v.classList.remove('selected'));
        el.classList.add('selected');
        selectedVariantIdx = parseInt(el.dataset.idx);
        document.getElementById('btn-save-plan').disabled = false;
      });
    });

    // Wire up save button
    document.getElementById('btn-save-plan').addEventListener('click', async () => {
      if (selectedVariantIdx === null) return;
      const chosen = variants[selectedVariantIdx];
      const res = await fetch(`/api/decks/${deck.id}/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets: chosen.targets }),
      });
      if (res.ok) {
        // Fetch real progress from audit before rendering
        const auditRes = await fetch(`/api/decks/${deck.id}/audit`);
        if (auditRes.ok) {
          const audit = await auditRes.json();
          planProgress = audit.plan_progress;
        }
        showPlanProgress(chosen.targets);
        document.getElementById('btn-autofill').style.display = '';
        document.getElementById('btn-clear-plan').style.display = '';
      } else {
        const err = await res.json();
        alert(err.error || 'Failed to save plan');
      }
    });
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
      res = await fetch(`/api/decks/${deck.id}/autofill`, { method: 'POST' });
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
        html += `<input type="checkbox" checked data-cid="${card.collection_id}" data-tag="${esc(tag)}">`;
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
    const ids = [];
    for (const cb of checked) {
      ids.push(parseInt(cb.dataset.cid));
    }
    if (ids.length === 0) return;

    const btn = document.getElementById('btn-autofill-add');
    btn.disabled = true;
    btn.textContent = 'Adding...';

    const res = await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: ids, zone: 'mainboard' }),
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

  async function clearPlan() {
    if (!confirm('Clear the deck plan?')) return;
    await fetch(`/api/decks/${deck.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: null }),
    });
    document.getElementById('plan-section').style.display = 'none';
    document.getElementById('btn-clear-plan').style.display = 'none';
    document.getElementById('plan-body').innerHTML = '';
  }

  // --- Utils ---
  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }

  // --- Initial render ---
  renderDeckDetail();
  loadPlan();
  switchZone('mainboard');
})();
