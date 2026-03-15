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

  // Card modal
  const cardModal = createCardModal();

  // Build the page
  const layout = document.getElementById('deck-detail-layout');
  layout.innerHTML = `
    <div class="deck-detail-header">
      <div class="info">
        <h2 id="deck-name"></h2>
        <div class="deck-meta-grid" id="deck-meta"></div>
      </div>
      <div class="actions">
        <a class="btn-builder-link" id="btn-builder-link" href="#" style="display:none">Builder</a>
        <button class="secondary" id="btn-edit">Edit</button>
        <button id="btn-add-cards">Add Cards</button>
        <button class="secondary" id="btn-remove-selected">Remove Selected</button>
        <button class="secondary" id="btn-import-expected">Import Expected List</button>
        <button class="danger" id="btn-delete">Delete Deck</button>
      </div>
    </div>

    <div class="zone-tabs" id="zone-tabs">
      <div class="tab active" data-zone="mainboard">Mainboard <span id="count-mainboard"></span></div>
      <div class="tab" data-zone="sideboard">Sideboard <span id="count-sideboard"></span></div>
      <div class="tab" data-zone="commander">Commander <span id="count-commander"></span></div>
    </div>

    <table class="card-table" id="card-table">
      <thead>
        <tr>
          <th><input type="checkbox" id="select-all"></th>
          <th>Name</th>
          <th>Type</th>
          <th>Mana</th>
          <th>Set</th>
          <th>#</th>
          <th>Condition</th>
          <th>Price</th>
        </tr>
      </thead>
      <tbody id="card-tbody"></tbody>
    </table>

    <div class="completeness-section" id="completeness-section" style="display:none">
      <div class="completeness-header" id="completeness-header">
        <h3 id="completeness-title">Expected Cards <span id="completeness-summary"></span></h3>
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
  document.getElementById('btn-add-cards').addEventListener('click', showAddCardsModal);
  document.getElementById('btn-remove-selected').addEventListener('click', removeSelectedCards);
  document.getElementById('btn-import-expected').addEventListener('click', showExpectedModal);
  document.getElementById('btn-delete').addEventListener('click', deleteDeck);

  // Completeness header toggle
  document.getElementById('completeness-header').addEventListener('click', toggleCompleteness);

  // Modal save/cancel buttons
  document.getElementById('btn-save-deck').addEventListener('click', saveDeck);
  document.getElementById('btn-cancel-edit').addEventListener('click', () => closeModal('deck-modal'));
  document.getElementById('btn-add-picker').addEventListener('click', addSelectedPickerCards);
  document.getElementById('btn-cancel-add').addEventListener('click', () => closeModal('add-cards-modal'));
  document.getElementById('btn-import-expected-confirm').addEventListener('click', importExpectedList);
  document.getElementById('btn-cancel-expected').addEventListener('click', () => closeModal('expected-modal'));

  // Precon checkbox toggle
  document.getElementById('f-precon').addEventListener('change', function() {
    document.getElementById('precon-fields').style.display = this.checked ? '' : 'none';
  });

  // Picker search
  document.getElementById('picker-search').addEventListener('input', searchPickerCards);

  // Close modals on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target === el) el.classList.remove('active');
    });
  });

  // Card table row click → card modal
  document.getElementById('card-table').addEventListener('click', (e) => {
    if (e.target.closest('input[type="checkbox"]')) return;
    if (e.target.closest('a')) return;
    const tr = e.target.closest('tr[data-idx]');
    if (tr) cardModal.show(deckCards[parseInt(tr.dataset.idx)]);
  });

  // --- Render deck detail header ---
  function renderDeckDetail() {
    document.getElementById('deck-name').textContent = deck.name;
    document.title = `${deck.name} — DeckDumpster`;
    const builderLink = document.getElementById('btn-builder-link');
    builderLink.href = `/deck-builder/${deck.id}`;
    builderLink.style.display = deck.format === 'commander' ? '' : 'none';
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
    const displayCount = deck.hypothetical && deck.card_count === 0 && deck.expected_card_count ? deck.expected_card_count : deck.card_count;
    meta.push(`<span class="label">Cards</span><span>${displayCount}</span>`);
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
    allCards.forEach(c => { if (counts[c.deck_zone] !== undefined) counts[c.deck_zone] += (c.quantity || 1); });
    document.getElementById('count-mainboard').textContent = `(${counts.mainboard})`;
    document.getElementById('count-sideboard').textContent = `(${counts.sideboard})`;
    document.getElementById('count-commander').textContent = `(${counts.commander})`;

    deckCards = allCards.filter(c => c.deck_zone === currentZone);
    renderCards();
  }

  const DECK_COLUMNS = ['name', 'type', 'mana', 'set', 'collector_number', 'condition', 'price'];

  function renderCards() {
    const tbody = document.getElementById('card-tbody');
    if (deckCards.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-secondary); padding:24px;">No cards in this zone</td></tr>';
      return;
    }
    tbody.innerHTML = deckCards.map((c, idx) => {
      const helpers = prepareCardHelpers(c);
      // Prefix name with quantity for expected cards with qty > 1
      if (c.quantity && c.quantity > 1) {
        helpers.nameHtml = `<span class="card-qty">${c.quantity}x</span> ${helpers.nameHtml}`;
      }
      const cells = DECK_COLUMNS.map(col => {
        const cls = col === 'price' ? ' class="price-cell"' : '';
        const content = renderCellContent(col, c, helpers);
        return `<td${cls}>${content}</td>`;
      }).join('');
      const checkboxHtml = c.id != null
        ? `<input type="checkbox" data-id="${c.id}" ${selectedCardIds.has(c.id) ? 'checked' : ''}>`
        : '';
      return `<tr data-idx="${idx}">
        <td>${checkboxHtml}</td>
        ${cells}
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
    const res = await fetch(`/api/collection?q=${encodeURIComponent(q)}&status=owned&expand=copies`);
    const data = await res.json();
    const allCopies = Array.isArray(data) ? data : data.cards || [];
    // Filter to unassigned copies only
    const cards = allCopies.filter(c => !c.deck_id && !c.binder_id);

    const container = document.getElementById('picker-cards');
    if (cards.length === 0) {
      container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);">No unassigned copies found</div>';
      return;
    }
    container.innerHTML = cards.map(c => {
      const key = String(c.collection_id);
      const cond = c.condition ? ` [${esc(c.condition)}]` : '';
      const price = c.purchase_price ? ` $${parseFloat(c.purchase_price).toFixed(2)}` : '';
      return `<div class="picker-card ${pickerSelected.has(key) ? 'selected' : ''}" data-key="${esc(key)}">
        <span>${esc(c.name)}</span>
        <span style="color:var(--text-secondary);font-size:0.85rem">${esc(c.set_code.toUpperCase())} #${esc(c.collector_number)} · ${esc(c.finish)}${cond}${price}</span>
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

    const allIds = Array.from(pickerSelected).map(Number);

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

    // Scryfall link helper for nonland cards
    const nonlandCards = expected.filter(c => {
      const name = c.name.toLowerCase();
      return name !== 'plains' && name !== 'island' && name !== 'swamp'
          && name !== 'mountain' && name !== 'forest';
    });

    section.style.display = '';
    let html = '';

    // Scryfall link for small decks (nonland cards < 15)
    if (nonlandCards.length > 0 && nonlandCards.length < 15) {
      const q = nonlandCards.map(c => `!"${c.name}"`).join(' or ');
      const sfUrl = `https://scryfall.com/search?unique=cards&q=${encodeURIComponent(q)}`;
      html += `<div style="margin-bottom:12px"><a href="${sfUrl}" target="_blank" rel="noopener" class="btn-scryfall-link">View on Scryfall</a></div>`;
    }

    // Hypothetical decks: cards are in the mainboard table, just show Scryfall link
    if (deck.hypothetical) {
      if (!html) {
        section.style.display = 'none';
        return;
      }
      document.getElementById('completeness-title').innerHTML = '';
      document.getElementById('completeness-body').innerHTML = html;
      return;
    }

    // Non-hypothetical decks: show completeness (present/missing/extra)
    const res = await fetch(`/api/decks/${deck.id}/completeness`);
    const data = await res.json();

    const total = data.present.length + data.missing.length;
    document.getElementById('completeness-summary').textContent =
      `(${data.present.length}/${total} present, ${data.missing.length} missing, ${data.extra.length} extra)`;

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

  // --- Utils ---
  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }

  // --- Initial render ---
  renderDeckDetail();
  switchZone('mainboard');
})();
