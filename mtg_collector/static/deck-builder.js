/* deck-builder.js — Unified deck builder + detail page */
(async function() {
  const root = document.getElementById('deck-builder-root');
  const pathParts = window.location.pathname.split('/').filter(Boolean);

  // Accept /deck-builder, /deck-builder/123, /decks/123
  let deckId = null;
  if (pathParts[0] === 'deck-builder' && pathParts.length > 1) deckId = pathParts[1];
  else if (pathParts[0] === 'decks' && pathParts.length > 1) deckId = pathParts[1];

  // State — declared before loadBuilder call to avoid temporal dead zone
  let currentZone = 'mainboard';
  let currentView = localStorage.getItem('deckDetailView') || 'list';
  const COL_MIN = 2, COL_MAX = 10;
  let gridCols = parseInt(localStorage.getItem('deckDetailGridCols'))
    || (window.innerWidth < 600 ? 3 : 4);
  let deckCards = [];
  let selectedCardIds = new Set();
  let pickerSelected = new Set();
  let cardModal = null;

  if (deckId) {
    await loadBuilder(deckId);
  } else {
    showCreateForm();
  }

  // ── Create mode ──

  function showCreateForm() {
    root.innerHTML = `
      <div class="builder-create">
        <h2>New Commander Deck</h2>
        <div class="form-group">
          <label>Commander</label>
          <input type="text" id="cmd-input" placeholder="Search your collection..." autocomplete="off">
          <div class="autocomplete-list" id="cmd-autocomplete" style="display:none"></div>
        </div>
        <div class="form-group">
          <label>Deck State</label>
          <select id="deck-state">
            <option value="idea">Idea</option>
            <option value="ready">Ready</option>
            <option value="constructed">Constructed</option>
          </select>
        </div>
        <button id="create-btn" disabled>Create Deck</button>
      </div>`;

    const input = document.getElementById('cmd-input');
    const acList = document.getElementById('cmd-autocomplete');
    const createBtn = document.getElementById('create-btn');
    let selectedCommander = null;
    let debounceTimer = null;

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      selectedCommander = null;
      createBtn.disabled = true;
      const q = input.value.trim();
      if (q.length < 2) { acList.style.display = 'none'; return; }
      debounceTimer = setTimeout(() => fetchCommanders(q), 250);
    });

    async function fetchCommanders(q) {
      const res = await fetch('/api/deck-builder/commanders?q=' + encodeURIComponent(q));
      const data = await res.json();
      if (!data.length) { acList.style.display = 'none'; return; }
      acList.innerHTML = data.map(c => `
        <div class="autocomplete-item" data-oracle='${esc(JSON.stringify(c))}'>
          <span>${esc(c.name)}</span>
          <span class="mana-icons">${renderMana(c.mana_cost)}</span>
        </div>`).join('');
      acList.style.display = 'block';
      acList.querySelectorAll('.autocomplete-item').forEach(el => {
        el.addEventListener('click', () => {
          selectedCommander = JSON.parse(el.dataset.oracle);
          input.value = selectedCommander.name;
          acList.style.display = 'none';
          createBtn.disabled = false;
        });
      });
    }

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.form-group')) acList.style.display = 'none';
    });

    createBtn.addEventListener('click', async () => {
      if (!selectedCommander) return;
      createBtn.disabled = true;
      createBtn.textContent = 'Creating...';
      const deckState = document.getElementById('deck-state').value;
      const res = await fetch('/api/deck-builder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          commander_oracle_id: selectedCommander.oracle_id,
          commander_printing_id: selectedCommander.printing_id,
          state: deckState,
        }),
      });
      const deck = await res.json();
      if (deck.error) {
        createBtn.textContent = 'Create Deck';
        createBtn.disabled = false;
        alert(deck.error);
        return;
      }
      const newDeckId = deck.id || deck.deck_id;
      history.pushState(null, '', '/decks/' + newDeckId);
      document.title = deck.name + ' — Deck Builder';
      await loadBuilder(newDeckId);
    });
  }

  // ── Builder mode ──

  // Note: using window property instead of closure let — headless Chromium
  // hangs when assigning large parsed JSON to closure variables in async IIFEs

  async function loadBuilder(id) {
    root.innerHTML = '<div class="loading-state"><span class="spinner"></span> Loading deck...</div>';
    const res = await fetch('/api/deck-builder/' + id);
    const data = await res.json();
    if (data.error) {
      root.innerHTML = '<div class="loading-state">' + esc(data.error) + '</div>';
      return;
    }
    window._builderData = data;
    document.title = data.deck.name + ' — Deck Builder';

    // Also fetch flat card data for grid view + zone counts
    const cardsRes = await fetch('/api/decks/' + id + '/cards');
    window._deckCards = await cardsRes.json();

    // Default view: grid for small decks, list for large
    let totalCards = 0;
    for (const g of Object.values(data.groups)) for (const c of g) totalCards += (c.quantity || 1);
    if (!localStorage.getItem('deckDetailView')) {
      currentView = totalCards < 25 ? 'grid' : 'list';
    }

    renderBuilder(data);
  }

  function renderBuilder(data) {
    const { deck, commander, groups } = data;
    const previewImg = commander && commander.image_uri
      ? commander.image_uri.replace('/large/', '/normal/')
      : '';
    const previewName = commander ? commander.name : (deck.origin_theme || deck.name);
    const isCommander = deck.format === 'commander';
    const deckSize = isCommander ? 100 : 20;

    let totalCards = 0;
    for (const g of Object.values(groups)) for (const c of g) totalCards += (c.quantity || 1);

    const previewContent = previewImg
      ? `<img id="preview-img" src="${esc(previewImg)}" alt="${esc(previewName)}">`
      : `<div class="preview-placeholder" id="preview-placeholder">${esc(previewName)}</div>`;

    // Compute zone counts from flat card data
    const allCards = window._deckCards || [];
    const zoneCounts = { mainboard: 0, sideboard: 0, commander: 0 };
    allCards.forEach(c => { if (zoneCounts[c.deck_zone] !== undefined) zoneCounts[c.deck_zone] += (c.quantity || 1); });

    root.innerHTML = `
      <div class="builder-layout">
        <div class="card-preview">
          ${previewContent}
          <div class="preview-name" id="preview-name">${esc(previewName)}</div>
        </div>
        <div class="deck-list">
          <div class="deck-header">
            <h2>${esc(deck.name)}</h2>
            <span class="card-count">${totalCards}/${deckSize}</span>
            <span class="state-badge state-${deck.state || 'idea'}">${({'idea':'Idea','ready':'Ready','constructed':'Constructed'})[deck.state] || deck.state || 'Idea'}</span>
            <div class="header-actions">
              <button class="edit-btn" id="edit-deck-btn">Edit</button>
              <button class="add-btn" id="add-card-btn">+ Add Card</button>
              <button class="edit-btn" id="btn-import-expected">Import Expected</button>
              ${deck.state !== 'constructed' ? '<button class="add-btn" id="btn-materialize">Materialize</button>' : ''}
              <button class="delete-btn" id="delete-deck-btn">Delete</button>
            </div>
          </div>

          <div class="zone-bar">
            <div class="zone-tabs" id="zone-tabs">
              <div class="tab ${currentZone === 'mainboard' ? 'active' : ''}" data-zone="mainboard">Mainboard <span id="count-mainboard">(${zoneCounts.mainboard})</span></div>
              <div class="tab ${currentZone === 'sideboard' ? 'active' : ''}" data-zone="sideboard">Sideboard <span id="count-sideboard">(${zoneCounts.sideboard})</span></div>
              <div class="tab ${currentZone === 'commander' ? 'active' : ''}" data-zone="commander">Commander <span id="count-commander">(${zoneCounts.commander})</span></div>
            </div>
            <div class="view-controls">
              <div class="view-toggle">
                <button class="view-btn ${currentView === 'list' ? 'active' : ''}" id="view-list-btn" title="List view">
                  <svg width="16" height="16" viewBox="0 0 16 16"><rect x="1" y="2" width="14" height="2" rx="0.5" fill="currentColor"/><rect x="1" y="7" width="14" height="2" rx="0.5" fill="currentColor"/><rect x="1" y="12" width="14" height="2" rx="0.5" fill="currentColor"/></svg>
                </button>
                <button class="view-btn ${currentView === 'grid' ? 'active' : ''}" id="view-grid-btn" title="Grid view">
                  <svg width="16" height="16" viewBox="0 0 16 16"><rect x="1" y="1" width="6" height="6" rx="1" fill="currentColor"/><rect x="9" y="1" width="6" height="6" rx="1" fill="currentColor"/><rect x="1" y="9" width="6" height="6" rx="1" fill="currentColor"/><rect x="9" y="9" width="6" height="6" rx="1" fill="currentColor"/></svg>
                </button>
              </div>
              <div class="col-controls" id="grid-size-wrap" style="${currentView === 'grid' ? '' : 'display:none'}">
                <button class="col-btn" id="col-minus">&minus;</button>
                <div class="col-count" id="col-count">${gridCols}</div>
                <button class="col-btn" id="col-plus">+</button>
              </div>
            </div>
          </div>

          <div id="type-groups" style="${currentView === 'list' ? '' : 'display:none'}">${renderGroups(groups, commander, deck)}</div>
          <div class="deck-grid" id="deck-grid" style="${currentView === 'grid' ? '' : 'display:none'}"></div>

          <div class="completeness-section" id="completeness-section" style="display:none">
            <div class="completeness-header" id="completeness-header">
              <h3 id="completeness-title">Expected Cards <span id="completeness-summary"></span></h3>
              <span id="completeness-toggle">&#9660;</span>
            </div>
            <div class="completeness-body" id="completeness-body"></div>
          </div>
        </div>
      </div>

      <!-- Edit Deck Modal -->
      <div class="modal-backdrop" id="deck-modal">
        <div class="edit-modal">
          <h3 id="modal-title">Edit Deck</h3>
          <div class="form-group">
            <label>Commander</label>
            <select id="f-commander"></select>
          </div>
          <div class="form-group">
            <label>Name *</label>
            <input type="text" id="f-name" placeholder="My Commander Deck">
          </div>
          <div class="form-group">
            <label>Format</label>
            <select id="f-format">
              <option value="">-- None --</option>
              <option value="commander">Commander / EDH</option>
              <option value="jumpstart">Jumpstart</option>
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
            <label>State</label>
            <select id="f-deck-state">
              <option value="idea">Idea</option>
              <option value="ready">Ready</option>
              <option value="constructed">Constructed</option>
            </select>
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

      <!-- Add Cards Modal (detail-style picker) -->
      <div class="modal-backdrop" id="add-cards-modal">
        <div class="edit-modal">
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
        <div class="edit-modal">
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

      <!-- Swap Printing Modal -->
      <div class="modal-backdrop" id="swap-modal">
        <div class="edit-modal" style="width:600px">
          <h3>Swap Printing</h3>
          <div id="swap-printings" class="swap-printings"></div>
          <div class="form-actions">
            <button class="secondary" id="btn-cancel-swap">Cancel</button>
          </div>
        </div>
      </div>`;

    // Init card modal
    if (!cardModal) cardModal = createCardModal();

    // Wire up zone tabs
    document.querySelectorAll('#zone-tabs .tab').forEach(tab => {
      tab.addEventListener('click', () => switchZone(tab.dataset.zone));
    });

    // Wire up view toggle
    document.getElementById('view-list-btn').addEventListener('click', () => {
      currentView = 'list';
      localStorage.setItem('deckDetailView', 'list');
      updateView();
    });
    document.getElementById('view-grid-btn').addEventListener('click', () => {
      currentView = 'grid';
      localStorage.setItem('deckDetailView', 'grid');
      updateView();
    });
    document.getElementById('col-minus').addEventListener('click', () => {
      if (gridCols > COL_MIN) { gridCols--; applyGridCols(); renderGrid(); }
    });
    document.getElementById('col-plus').addEventListener('click', () => {
      if (gridCols < COL_MAX) { gridCols++; applyGridCols(); renderGrid(); }
    });

    // Hover preview — look up elements fresh each time since they get swapped
    const previewContainer = document.querySelector('.card-preview');
    const defaultImg = previewImg;
    const defaultName = previewName;

    function setPreview(imgUrl, name) {
      const imgEl = previewContainer.querySelector('#preview-img');
      const phEl = previewContainer.querySelector('#preview-placeholder');
      const nameEl = previewContainer.querySelector('#preview-name');
      if (imgUrl) {
        const src = imgUrl.replace('/large/', '/normal/');
        if (imgEl) {
          imgEl.src = src;
        } else if (phEl) {
          const img = document.createElement('img');
          img.id = 'preview-img';
          img.src = src;
          phEl.replaceWith(img);
        }
      }
      if (name && nameEl) nameEl.textContent = name;
    }

    function resetPreview() {
      const imgEl = previewContainer.querySelector('#preview-img');
      const nameEl = previewContainer.querySelector('#preview-name');
      if (defaultImg && imgEl) {
        imgEl.src = defaultImg;
      } else if (!defaultImg && imgEl) {
        const ph = document.createElement('div');
        ph.className = 'preview-placeholder';
        ph.id = 'preview-placeholder';
        ph.textContent = defaultName;
        imgEl.replaceWith(ph);
      }
      if (nameEl) nameEl.textContent = defaultName;
    }

    // List view: hover preview + remove + card link click
    const typeGroupsEl = document.getElementById('type-groups');
    typeGroupsEl.addEventListener('mouseenter', (e) => {
      const row = e.target.closest('.card-row');
      if (!row) return;
      setPreview(row.dataset.imageUri, row.dataset.cardName);
    }, true);
    typeGroupsEl.addEventListener('mouseleave', resetPreview);

    // Swap printing (list view)
    typeGroupsEl.addEventListener('click', async (e) => {
      const swapBtn = e.target.closest('.swap-btn');
      if (!swapBtn) return;
      showSwapModal(deck.id, swapBtn.dataset.printingId, swapBtn.dataset.oracleId);
    });

    // Adjust card quantity (+/-)
    typeGroupsEl.addEventListener('click', async (e) => {
      const btn = e.target.closest('.qty-btn');
      if (!btn) return;
      const delta = parseInt(btn.dataset.delta, 10);
      const pid = btn.dataset.printingId;
      const zone = btn.dataset.zone || 'mainboard';
      const res = await fetch('/api/decks/' + deck.id + '/cards/quantity', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ printing_id: pid, zone, delta }),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
      await loadBuilder(deck.id);
    });

    // Grid view: click for card modal
    document.getElementById('deck-grid').addEventListener('click', (e) => {
      const card = e.target.closest('.grid-card');
      if (!card) return;
      const idx = parseInt(card.dataset.idx);
      const zoneCards = getZoneCards();
      if (zoneCards[idx]) cardModal.show(zoneCards[idx]);
    });

    // Add card button
    const addBtn = document.getElementById('add-card-btn');
    if (addBtn) {
      addBtn.addEventListener('click', () => showAddCardsModal(deck.id));
    }

    // Edit deck
    document.getElementById('edit-deck-btn').addEventListener('click', () => showEditModal(deck));

    // Import expected list
    document.getElementById('btn-import-expected').addEventListener('click', showExpectedModal);

    // Delete deck
    document.getElementById('delete-deck-btn').addEventListener('click', async () => {
      if (!confirm(`Delete "${deck.name}"? Cards will be unassigned but not deleted.`)) return;
      await fetch('/api/decks/' + deck.id, { method: 'DELETE' });
      window.location.href = '/decks';
    });

    // Materialize idea/ready deck to constructed
    const materializeBtn = document.getElementById('btn-materialize');
    if (materializeBtn) {
      materializeBtn.addEventListener('click', async () => {
        if (!confirm('Materialize this deck? This will assign owned cards from your collection and convert it to a physical deck.')) return;
        materializeBtn.disabled = true;
        materializeBtn.textContent = 'Materializing...';
        try {
          const res = await fetch('/api/decks/' + deck.id + '/materialize', { method: 'POST' });
          const result = await res.json();
          if (result.error) {
            alert('Error: ' + result.error);
            materializeBtn.disabled = false;
            materializeBtn.textContent = 'Materialize';
            return;
          }
          let msg = 'Matched ' + result.total_matched + ' card(s).';
          if (result.total_missing > 0) {
            const names = result.missing.map(function(m) { return m.name + ' (' + (m.short || m.expected) + ' short)'; }).join('\n');
            msg += '\n\n' + result.total_missing + ' card(s) missing:\n' + names;
          }
          alert(msg);
          window.location.reload();
        } catch (err) {
          alert('Materialize failed: ' + err.message);
          materializeBtn.disabled = false;
          materializeBtn.textContent = 'Materialize';
        }
      });
    }

    // Modal buttons
    document.getElementById('btn-save-deck').addEventListener('click', () => saveDeck(deck.id));
    document.getElementById('btn-cancel-edit').addEventListener('click', () => closeModal('deck-modal'));
    document.getElementById('btn-add-picker').addEventListener('click', () => addSelectedPickerCards(deck.id));
    document.getElementById('btn-cancel-add').addEventListener('click', () => closeModal('add-cards-modal'));
    document.getElementById('btn-import-expected-confirm').addEventListener('click', () => importExpectedList(deck.id));
    document.getElementById('btn-cancel-expected').addEventListener('click', () => closeModal('expected-modal'));
    document.getElementById('btn-cancel-swap').addEventListener('click', () => closeModal('swap-modal'));

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

    // Completeness
    document.getElementById('completeness-header').addEventListener('click', toggleCompleteness);

    // Apply grid cols and render initial view
    applyGridCols();
    updateDeckCards();
    loadCompleteness(deck);
  }

  function getZoneCards() {
    const allCards = window._deckCards || [];
    return allCards.filter(c => c.deck_zone === currentZone);
  }

  function updateDeckCards() {
    deckCards = getZoneCards();
    if (currentView === 'grid') renderGrid();
  }

  function switchZone(zone) {
    currentZone = zone;
    document.querySelectorAll('#zone-tabs .tab').forEach(t => {
      t.classList.toggle('active', t.dataset.zone === zone);
    });
    updateDeckCards();
  }

  function updateView() {
    document.getElementById('view-list-btn').classList.toggle('active', currentView === 'list');
    document.getElementById('view-grid-btn').classList.toggle('active', currentView === 'grid');
    document.getElementById('grid-size-wrap').style.display = currentView === 'grid' ? '' : 'none';
    document.getElementById('type-groups').style.display = currentView === 'list' ? '' : 'none';
    document.getElementById('deck-grid').style.display = currentView === 'grid' ? '' : 'none';
    if (currentView === 'grid') renderGrid();
  }

  function applyGridCols() {
    const el = document.getElementById('col-count');
    if (el) el.textContent = gridCols;
    const minBtn = document.getElementById('col-minus');
    const maxBtn = document.getElementById('col-plus');
    if (minBtn) minBtn.disabled = gridCols <= COL_MIN;
    if (maxBtn) maxBtn.disabled = gridCols >= COL_MAX;
    localStorage.setItem('deckDetailGridCols', gridCols);
  }

  function renderGrid() {
    const container = document.getElementById('deck-grid');
    const cards = getZoneCards();
    if (cards.length === 0) {
      container.innerHTML = '<div style="text-align:center; color:var(--text-secondary); padding:24px;">No cards in this zone</div>';
      return;
    }
    const gap = 8;
    container.style.display = 'flex';
    container.style.flexWrap = 'wrap';
    container.style.gap = gap + 'px';
    const cardWidthPct = `calc((100% - ${(gridCols - 1) * gap}px) / ${gridCols})`;

    container.innerHTML = cards.map((c, idx) => {
      const img = c.image_uri || '';
      const imgSrc = img.replace('/large/', '/normal/');
      const rarityColor = typeof getRarityColor === 'function' ? getRarityColor(c.rarity) : '#555';
      const qty = c.quantity && c.quantity > 1 ? `<span class="grid-qty">${c.quantity}x</span>` : '';
      return `<div class="grid-card" data-idx="${idx}" style="width:${cardWidthPct}">
        <div class="grid-card-img" style="--rarity-color:${rarityColor}">
          ${imgSrc ? `<img src="${imgSrc}" loading="lazy" alt="${esc(c.name)}">` : ''}
        </div>
        <div class="grid-card-name">${qty}${esc(c.name)}</div>
      </div>`;
    }).join('');
  }

  function renderGroups(groups, commander, deck) {
    const showSwap = deck && deck.state !== 'constructed';
    let html = '';
    // Show commander first if present
    if (commander) {
      html += `<div class="type-group">
        <div class="type-group-header">Commander</div>
        <div class="card-row" data-image-uri="${esc(commander.image_uri || '')}" data-card-name="${esc(commander.name)}">
          <span class="card-name"><a href="/card/${esc(commander.set_code)}/${esc(commander.collector_number)}">${esc(commander.name)}</a></span>
          <span class="mana-icons">${renderMana(commander.mana_cost)}</span>
        </div>
      </div>`;
    }
    for (const [type, cards] of Object.entries(groups)) {
      let typeTotal = 0;
      for (const c of cards) typeTotal += (c.quantity || 1);
      html += `<div class="type-group">
        <div class="type-group-header">${esc(type)} <span class="group-count">(${typeTotal})</span></div>`;
      for (const c of cards) {
        const qty = c.quantity || 1;
        const zone = c.deck_zone || 'mainboard';
        const pid = c.printing_id || '';
        let swapBtn = '';
        if (showSwap && pid && c.oracle_id) {
          swapBtn = `<button class="swap-btn" data-printing-id="${pid}" data-oracle-id="${c.oracle_id}" title="Swap printing">&#x21c4;</button>`;
        }
        const qtyControls = pid ? `<span class="qty-controls">`
          + `<button class="qty-btn" data-delta="-1" data-printing-id="${pid}" data-zone="${zone}" title="Remove one">&minus;</button>`
          + `<span class="qty-count">${qty}</span>`
          + `<button class="qty-btn" data-delta="1" data-printing-id="${pid}" data-zone="${zone}" title="Add one">&plus;</button>`
          + `</span>` : '';
        html += `<div class="card-row" data-image-uri="${esc(c.image_uri || '')}" data-card-name="${esc(c.name)}">
          <span class="card-name"><a href="/card/${esc(c.set_code)}/${esc(c.collector_number)}">${esc(c.name)}</a></span>
          <span class="mana-icons">${renderMana(c.mana_cost)}</span>
          ${swapBtn}${qtyControls}
        </div>`;
      }
      html += '</div>';
    }
    return html;
  }

  // ── Edit Deck Modal ──

  function showEditModal(deck) {
    document.getElementById('modal-title').textContent = 'Edit Deck';

    // Commander dropdown — populated from cards in the deck
    const cmdSelect = document.getElementById('f-commander');
    const allCards = window._deckCards || [];
    // Dedupe by oracle_id, keeping first occurrence
    const seen = new Set();
    const uniqueCards = allCards.filter(c => {
      if (seen.has(c.oracle_id)) return false;
      seen.add(c.oracle_id);
      return true;
    });
    uniqueCards.sort((a, b) => a.name.localeCompare(b.name));
    cmdSelect.innerHTML = '<option value="">-- None --</option>' +
      uniqueCards.map(c =>
        `<option value="${esc(c.oracle_id)}|${esc(c.printing_id)}">${esc(c.name)}</option>`
      ).join('');
    // Pre-select current commander
    if (deck.commander_oracle_id) {
      const match = uniqueCards.find(c => c.oracle_id === deck.commander_oracle_id);
      if (match) cmdSelect.value = match.oracle_id + '|' + match.printing_id;
    }
    document.getElementById('f-name').value = deck.name || '';
    document.getElementById('f-format').value = deck.format || '';
    document.getElementById('f-description').value = deck.description || '';
    document.getElementById('f-deck-state').value = deck.state || 'idea';
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

  async function saveDeck(deckId) {
    const data = {
      name: document.getElementById('f-name').value.trim(),
      format: document.getElementById('f-format').value || null,
      description: document.getElementById('f-description').value.trim() || null,
      state: document.getElementById('f-deck-state').value,
      is_precon: document.getElementById('f-precon').checked,
      sleeve_color: document.getElementById('f-sleeve').value.trim() || null,
      deck_box: document.getElementById('f-deckbox').value.trim() || null,
      storage_location: document.getElementById('f-location').value.trim() || null,
      origin_set_code: document.getElementById('f-origin-set').value || null,
      origin_theme: document.getElementById('f-origin-theme').value.trim() || null,
      origin_variation: document.getElementById('f-origin-variation').value ? parseInt(document.getElementById('f-origin-variation').value) : null,
    };
    const cmdVal = document.getElementById('f-commander').value;
    if (cmdVal) {
      const [oid, pid] = cmdVal.split('|');
      data.commander_oracle_id = oid;
      data.commander_printing_id = pid;
    } else {
      data.commander_oracle_id = null;
      data.commander_printing_id = null;
    }
    if (!data.name) { alert('Name is required'); return; }

    await fetch('/api/decks/' + deckId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    closeModal('deck-modal');
    await loadBuilder(deckId);
  }

  // ── Add Cards Modal (detail-style picker) ──

  function showAddCardsModal(deckId) {
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
    const isVirtual = window._builderData && window._builderData.deck.state !== 'constructed';
    const res = await fetch('/api/collection?q=' + encodeURIComponent(q) + '&status=owned&expand=copies');
    const data = await res.json();
    const allCopies = Array.isArray(data) ? data : data.cards || [];
    // Hypothetical decks: dedup by printing_id (don't care about individual copies)
    // Real decks: only show unassigned copies
    let cards;
    if (isVirtual) {
      const seen = new Set();
      cards = allCopies.filter(c => {
        if (seen.has(c.printing_id)) return false;
        seen.add(c.printing_id);
        return true;
      });
    } else {
      cards = allCopies.filter(c => !c.deck_id && !c.binder_id);
    }

    const container = document.getElementById('picker-cards');
    if (cards.length === 0) {
      container.innerHTML = '<div style="padding:12px;color:var(--text-secondary);">No unassigned copies found</div>';
      return;
    }
    container.innerHTML = cards.map(c => {
      const key = isVirtual ? String(c.printing_id) : String(c.collection_id);
      const cond = c.condition ? ` [${esc(c.condition)}]` : '';
      const price = c.purchase_price ? ` $${parseFloat(c.purchase_price).toFixed(2)}` : '';
      return `<div class="picker-card ${pickerSelected.has(key) ? 'selected' : ''}" data-key="${esc(key)}">
        <span>${esc(c.name)}</span>
        <span style="color:var(--text-secondary);font-size:0.85rem">${esc(c.set_code.toUpperCase())} #${esc(c.collector_number)} · ${esc(c.finish)}${cond}${price}</span>
      </div>`;
    }).join('');

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

  async function addSelectedPickerCards(deckId) {
    if (pickerSelected.size === 0) { alert('No cards selected'); return; }
    const zone = document.getElementById('add-zone').value;
    const isVirtual = window._builderData && window._builderData.deck.state !== 'constructed';

    if (isVirtual) {
      // Hypothetical deck: add to expected cards by printing_id
      const printingIds = Array.from(pickerSelected);
      const res = await fetch('/api/decks/' + deckId + '/expected-cards/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ printing_ids: printingIds, zone }),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
    } else {
      const allIds = Array.from(pickerSelected).map(Number);
      const res = await fetch('/api/decks/' + deckId + '/cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collection_ids: allIds, zone }),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
    }

    closeModal('add-cards-modal');
    await loadBuilder(deckId);
  }

  // ── Expected List Import ──

  async function showSwapModal(deckId, currentPrintingId, oracleId) {
    const modal = document.getElementById('swap-modal');
    const container = document.getElementById('swap-printings');
    container.innerHTML = '<div class="loading-state"><span class="spinner"></span> Loading...</div>';
    modal.classList.add('active');

    const res = await fetch('/api/printings/by-oracle/' + oracleId);
    const printings = await res.json();

    container.innerHTML = printings.map(p => {
      const isCurrent = p.printing_id === currentPrintingId;
      const ownedBadge = p.owned_count > 0
        ? `<span class="owned-badge">Owned: ${p.owned_count}</span>`
        : `<span class="unowned-badge">Not owned</span>`;
      const imgSrc = (p.image_uri || '').replace('/large/', '/small/');
      return `<div class="swap-option${isCurrent ? ' current' : ''}" data-pid="${esc(p.printing_id)}">
        ${imgSrc ? `<img src="${imgSrc}" class="swap-thumb" loading="lazy">` : '<div class="swap-thumb-placeholder"></div>'}
        <div class="swap-info">
          <div class="swap-set">${esc(p.set_name)} (${esc(p.set_code.toUpperCase())}) #${esc(p.collector_number)}</div>
          <div class="swap-meta">${ownedBadge}${isCurrent ? ' <span class="current-badge">Current</span>' : ''}</div>
        </div>
      </div>`;
    }).join('');

    container.onclick = async (e) => {
      const option = e.target.closest('.swap-option');
      if (!option || option.classList.contains('current')) return;
      const newPid = option.dataset.pid;
      await fetch('/api/decks/' + deckId + '/expected-cards/swap', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ old_printing_id: currentPrintingId, new_printing_id: newPid }),
      });
      closeModal('swap-modal');
      await loadBuilder(deckId);
    };
  }

  function showExpectedModal() {
    document.getElementById('f-expected-list').value = '';
    document.getElementById('expected-errors').textContent = '';
    document.getElementById('expected-modal').classList.add('active');
  }

  async function importExpectedList(deckId) {
    const text = document.getElementById('f-expected-list').value.trim();
    if (!text) { alert('Paste a decklist first'); return; }

    const res = await fetch('/api/decks/' + deckId + '/expected', {
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
    const deck = window._builderData.deck;
    loadCompleteness(deck);
  }

  // ── Completeness ──

  async function loadCompleteness(deck) {
    const section = document.getElementById('completeness-section');

    const expRes = await fetch('/api/decks/' + deck.id + '/expected');
    const expected = await expRes.json();
    if (!expected.length && !deck.is_precon) {
      section.style.display = 'none';
      return;
    }
    if (!expected.length) {
      section.style.display = '';
      document.getElementById('completeness-summary').textContent = '(no expected list set)';
      document.getElementById('completeness-body').innerHTML =
        '<p style="color:var(--text-secondary);padding:8px">Use "Edit" > "Import Expected List" to define the expected cards for this deck.</p>';
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

    // Scryfall link for small decks
    if (nonlandCards.length > 0 && nonlandCards.length < 15) {
      const q = nonlandCards.map(c => c.set_code ? `(!"${c.name}" set:${c.set_code})` : `!"${c.name}"`).join(' or ');
      const sfUrl = `https://scryfall.com/search?unique=cards&q=${encodeURIComponent(q)}`;
      html += `<div style="margin-bottom:12px"><a href="${sfUrl}" target="_blank" rel="noopener" class="btn-scryfall-link">View on Scryfall</a></div>`;
    }

    // Idea decks: cards are in the mainboard table, just show Scryfall link
    if (deck.state === 'idea') {
      if (!html) {
        section.style.display = 'none';
        return;
      }
      document.getElementById('completeness-title').innerHTML = '';
      document.getElementById('completeness-body').innerHTML = html;
      return;
    }

    // Ready/Constructed: show completeness
    const res = await fetch('/api/decks/' + deck.id + '/completeness');
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

    // Wire up location tag click handlers
    document.querySelectorAll('.location-tag[data-cid]').forEach(tag => {
      tag.addEventListener('click', () => reassembleCard(deck.id, parseInt(tag.dataset.cid)));
    });

    const reassembleBtn = document.getElementById('btn-reassemble-all');
    if (reassembleBtn) {
      reassembleBtn.addEventListener('click', () => reassembleAll(deck.id));
    }
  }

  function toggleCompleteness() {
    const body = document.getElementById('completeness-body');
    const toggle = document.getElementById('completeness-toggle');
    body.classList.toggle('collapsed');
    toggle.innerHTML = body.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
  }

  async function reassembleCard(deckId, collectionId) {
    const res = await fetch('/api/decks/' + deckId + '/reassemble', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: [collectionId] }),
    });
    const result = await res.json();
    if (result.error) { alert(result.error); return; }
    await loadBuilder(deckId);
  }

  async function reassembleAll(deckId) {
    const res = await fetch('/api/decks/' + deckId + '/completeness');
    const data = await res.json();
    const ids = [];
    for (const c of data.missing) {
      for (const loc of c.locations) {
        if (!loc.deck_name && !loc.binder_name) ids.push(loc.collection_id);
      }
    }
    if (!ids.length) { alert('No unassigned cards to reassemble'); return; }

    const moveRes = await fetch('/api/decks/' + deckId + '/reassemble', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: ids }),
    });
    const result = await moveRes.json();
    if (result.error) { alert(result.error); return; }
    await loadBuilder(deckId);
  }

  // ── Utils ──

  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }
})();
