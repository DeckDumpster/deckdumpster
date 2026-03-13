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
  let editingDeckId = null;
  let activeRoleFilter = null;
  let activeTypeFilter = null;
  let currentView = 'list';
  let groupBy = 'type';

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
              <button class="secondary active" id="view-list-btn" title="List view">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="1" width="6" height="6" rx="1"/>
                  <rect x="9" y="1" width="6" height="6" rx="1"/>
                  <rect x="1" y="9" width="6" height="6" rx="1"/>
                  <rect x="9" y="9" width="6" height="6" rx="1"/>
                </svg>
              </button>
              <button class="secondary" id="view-table-btn" title="Table view">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="1" width="14" height="3" rx="1"/>
                  <rect x="1" y="6" width="14" height="3" rx="1"/>
                  <rect x="1" y="11" width="14" height="3" rx="1"/>
                </svg>
              </button>
            </div>
            <select id="group-by-select" class="group-by-select">
              <option value="type">Group by Type</option>
              <option value="role">Group by Role</option>
            </select>
          </div>
        </div>

        <div id="active-filter-banner" class="active-filter-banner" style="display:none"></div>

        <div id="card-display">
        <div id="card-list"></div>
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
          <div class="sidebar-actions-row" id="plan-actions-row">
            <button class="secondary" id="btn-add-card">Add Card</button>
          </div>
          <button id="btn-autofill" style="display:none">Autofill Nonland</button>
          <button id="btn-fill-lands" style="display:none">Autofill Lands</button>
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


    <div class="modal-backdrop" id="search-modal">
      <div class="modal replace-modal">
        <div class="replace-header">
          <h3 id="search-modal-title">Search</h3>
          <button class="btn btn-ghost" id="search-cancel">✕</button>
        </div>
        <div class="search-filters">
          <div class="search-filter-row">
            <input placeholder="Card name..." id="sf-name" class="search-input-wide">
            <input placeholder="Mana value" id="sf-cmc" type="number" min="0" max="20" class="search-input-sm">
            <input placeholder="Tag (e.g. removal)" id="sf-tag" class="search-input-med">
          </div>
          <div class="search-filter-row">
            <div class="search-pills" id="sf-colors">
              <label class="search-pill"><input type="checkbox" value="W"><span class="ms ms-w ms-cost"></span></label>
              <label class="search-pill"><input type="checkbox" value="U"><span class="ms ms-u ms-cost"></span></label>
              <label class="search-pill"><input type="checkbox" value="B"><span class="ms ms-b ms-cost"></span></label>
              <label class="search-pill"><input type="checkbox" value="R"><span class="ms ms-r ms-cost"></span></label>
              <label class="search-pill"><input type="checkbox" value="G"><span class="ms ms-g ms-cost"></span></label>
            </div>
            <div class="search-pills" id="sf-types">
              <label class="search-pill"><input type="checkbox" value="Creature">Creature</label>
              <label class="search-pill"><input type="checkbox" value="Instant">Instant</label>
              <label class="search-pill"><input type="checkbox" value="Sorcery">Sorcery</label>
              <label class="search-pill"><input type="checkbox" value="Enchantment">Enchant</label>
              <label class="search-pill"><input type="checkbox" value="Artifact">Artifact</label>
              <label class="search-pill"><input type="checkbox" value="Land">Land</label>
            </div>
            <select id="sf-role" style="display:none">
              <option value="">— Role —</option>
            </select>
          </div>
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
      if (this.checked) selectedCardIds.add(cardKey(c));
      else selectedCardIds.delete(cardKey(c));
    });
    renderCards();
  });

  // Header/sidebar buttons
  document.getElementById('btn-edit').addEventListener('click', showEditModal);
  document.getElementById('btn-curve').addEventListener('click', openCurveModal);
  document.getElementById('btn-generate-plan').addEventListener('click', generatePlan);
  document.getElementById('btn-autofill').addEventListener('click', runAutofill);

  document.getElementById('btn-delete').addEventListener('click', deleteDeck);
  document.getElementById('btn-edit-plan').addEventListener('click', enterPlanEditMode);
  document.getElementById('btn-add-card').addEventListener('click', openAddCardModal);

  // Completeness header toggle
  document.getElementById('completeness-header').addEventListener('click', toggleCompleteness);

  // Modal save/cancel buttons
  document.getElementById('btn-save-deck').addEventListener('click', saveDeck);
  document.getElementById('btn-cancel-edit').addEventListener('click', () => closeModal('deck-modal'));
  document.getElementById('btn-import-expected-confirm').addEventListener('click', importExpectedList);
  document.getElementById('btn-cancel-expected').addEventListener('click', () => closeModal('expected-modal'));
  document.getElementById('btn-fill-lands').addEventListener('click', runFillLands);
  document.getElementById('btn-curve-close').addEventListener('click', () => closeModal('curve-modal'));
  document.getElementById('btn-save-plan').addEventListener('click', savePlanVariant);
  document.getElementById('search-cancel').addEventListener('click', () => closeModal('search-modal'));
  document.getElementById('replace-confirm').addEventListener('click', confirmReplacement);

  // Search modal filter debounce
  let searchTimer = null;
  ['sf-name', 'sf-cmc', 'sf-tag'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(searchCards, 300);
    });
  });
  document.querySelectorAll('#sf-colors input, #sf-types input').forEach(cb => {
    cb.addEventListener('change', searchCards);
  });
  document.getElementById('sf-role').addEventListener('change', () => {
    document.getElementById('sf-tag').value = document.getElementById('sf-role').value;
    searchCards();
  });

  // Precon checkbox toggle
  document.getElementById('f-precon').addEventListener('change', function() {
    document.getElementById('precon-fields').style.display = this.checked ? '' : 'none';
  });

  // View toggle
  document.getElementById('view-list-btn').addEventListener('click', () => {
    currentView = 'list';
    updateViewButtons();
    renderCards();
    fetch('/api/settings', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ default_card_view: 'list' }) });
  });
  document.getElementById('view-table-btn').addEventListener('click', () => {
    currentView = 'table';
    updateViewButtons();
    renderCards();
    fetch('/api/settings', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ default_card_view: 'table' }) });
  });

  // Group-by selector
  document.getElementById('group-by-select').addEventListener('change', function() {
    groupBy = this.value;
    renderCards();
  });

  function updateViewButtons() {
    document.getElementById('view-list-btn').classList.toggle('active', currentView === 'list');
    document.getElementById('view-table-btn').classList.toggle('active', currentView === 'table');
    document.getElementById('group-by-select').style.display = currentView === 'list' ? '' : 'none';
    document.getElementById('card-list').style.display = currentView === 'list' ? '' : 'none';
    document.getElementById('card-table').style.display = currentView === 'table' ? '' : 'none';
  }

  // List card hover — show card image in sidebar commander-display area
  let hoverPreviewActive = false;
  let commanderHtml = '';  // stash original commander display

  document.getElementById('card-list').addEventListener('mouseover', e => {
    const row = e.target.closest('.list-card-row');
    if (row && row.dataset.image) {
      const el = document.getElementById('commander-display');
      if (!hoverPreviewActive) commanderHtml = el.innerHTML;
      hoverPreviewActive = true;
      const rarityColor = row.dataset.rarityColor || '#111';
      el.innerHTML = `<div class="hover-preview-card">
        <div class="sheet-card-img-wrap" style="--rarity-color:${rarityColor};--set-color:#111">
          <img src="${esc(row.dataset.image)}" alt="Card preview">
        </div>
      </div>`;
      el.style.display = '';
    }
  });

  document.getElementById('card-list').addEventListener('mouseleave', () => {
    if (hoverPreviewActive) {
      hoverPreviewActive = false;
      const el = document.getElementById('commander-display');
      el.innerHTML = commanderHtml;
      el.style.display = commanderHtml ? '' : 'none';
    }
  });

  // List card click — actions (replace, remove) handled via delegation
  document.getElementById('card-list').addEventListener('click', e => {
    const replBtn = e.target.closest('.list-replace-btn');
    if (replBtn) {
      e.preventDefault();
      if (deck.hypothetical) {
        openReplaceModal(null, replBtn.dataset.name, replBtn.dataset.oracleId);
      } else {
        openReplaceModal(parseInt(replBtn.dataset.cid), replBtn.dataset.name, replBtn.dataset.oracleId);
      }
      return;
    }
    const removeBtn = e.target.closest('.list-remove-btn');
    if (removeBtn) {
      e.preventDefault();
      removeCard(removeBtn.dataset);
      return;
    }
  });

  // Close modals on backdrop click (except plan-variants — must choose a plan)
  document.querySelectorAll('.modal-backdrop').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target === el && el.id !== 'plan-variants-modal') el.classList.remove('active');
    });
  });

  // --- Refresh all deck state after any mutation ---
  async function refreshDeck() {
    const res = await fetch(`/api/decks/${deck.id}`);
    deck = await res.json();
    renderDeckDetail();
    await loadDeckCards();
    await loadPlan();
    loadCompleteness();
  }

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

  function cardQty(c) { return c.quantity || 1; }
  function cardKey(c) { return deck.hypothetical ? c.oracle_id : c.id; }
  function selectedIdsBody() {
    const ids = Array.from(selectedCardIds);
    return deck.hypothetical ? { oracle_ids: ids } : { collection_ids: ids };
  }

  function buildTypeFilters() {
    const typeCounts = {};
    const nonCmdCards = allDeckCards.filter(c => c.deck_zone !== 'commander');
    for (const c of nonCmdCards) {
      const t = primaryType(c.type_line);
      typeCounts[t] = (typeCounts[t] || 0) + cardQty(c);
    }
    // Sort by TYPE_ORDER, then Other at end
    const types = Object.keys(typeCounts).sort((a, b) => {
      const ai = TYPE_ORDER.indexOf(a), bi = TYPE_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });

    const container = document.getElementById('type-filters');
    const allCount = nonCmdCards.reduce((sum, c) => sum + cardQty(c), 0);
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
    commanderHtml = cmdEl.innerHTML;

    buildTypeFilters();
    deckCards = getMainboardCards();
    renderCards();
  }

  function getFilteredCards() {
    if (!activeRoleFilter) return deckCards;
    if (activeRoleFilter === 'lands') {
      return deckCards.filter(c => (c.type_line || '').includes('Land'));
    }
    const subTags = INFRA_SUB_TAGS[activeRoleFilter];
    if (subTags) {
      return deckCards.filter(c => {
        const tags = c.tags ? c.tags.split(',') : [];
        return tags.some(t => subTags.has(t));
      });
    }
    return deckCards.filter(c => {
      const tags = c.tags ? c.tags.split(',') : [];
      return tags.includes(activeRoleFilter);
    });
  }

  function getCardRoles(card) {
    const tags = card.tags ? card.tags.split(',') : [];
    const tagSet = new Set(tags);
    const roles = [];
    // Check each plan target
    for (const [key, val] of Object.entries(currentPlanTargets || {})) {
      if (key === 'lands') continue;
      if (val.type === 'query') continue;
      const subTags = INFRA_SUB_TAGS[key];
      if (subTags) {
        // Infrastructure category: match if card has any sub-tag
        if (tags.some(t => subTags.has(t))) roles.push(val.label);
      } else if (tagSet.has(key)) {
        roles.push(val.label);
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

    if (currentView === 'list') {
      renderList(cards);
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
      const key = cardKey(c);
      const ownershipBadge = isHypo
        ? (c.owned_copies > 0
          ? `<span class="own-badge owned" title="${c.free_copies} free / ${c.owned_copies} owned">&#10003;</span>`
          : '<span class="own-badge missing" title="Not owned">&#10007;</span>')
        : '';
      const qtyControls = isHypo
        ? `<span class="qty-controls" data-oracle-id="${esc(c.oracle_id)}" data-zone="${esc(c.deck_zone || 'mainboard')}"><button class="qty-btn qty-minus">−</button><span class="qty-val">${c.quantity}</span><button class="qty-btn qty-plus">+</button></span> `
        : '';
      return `<tr>
        <td><input type="checkbox" data-key="${esc(String(key))}" ${selectedCardIds.has(key) ? 'checked' : ''}></td>
        <td>${qtyControls}<a href="/card/${esc(sc)}/${esc(cn)}">${esc(c.name)}</a> ${ownershipBadge}</td>
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
        const key = isHypo ? this.dataset.key : parseInt(this.dataset.key);
        if (this.checked) selectedCardIds.add(key);
        else selectedCardIds.delete(key);
      });
    });

    // Wire up quantity +/- buttons for hypothetical decks
    if (isHypo) {
      tbody.querySelectorAll('.qty-controls').forEach(ctrl => {
        const oid = ctrl.dataset.oracleId;
        const zone = ctrl.dataset.zone;
        ctrl.querySelector('.qty-minus').addEventListener('click', () => updateQuantity(oid, zone, -1, ctrl));
        ctrl.querySelector('.qty-plus').addEventListener('click', () => updateQuantity(oid, zone, 1, ctrl));
      });
    }
  }

  async function updateQuantity(oracleId, zone, delta, ctrl) {
    const valSpan = ctrl.querySelector('.qty-val') || ctrl.querySelector('.qty-grid-val');
    const current = parseInt(valSpan.textContent);
    const newQty = current + delta;
    if (newQty < 0) return;

    const res = await fetch(`/api/decks/${deck.id}/cards/quantity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oracle_id: oracleId, quantity: newQty, zone }),
    });
    const result = await res.json();
    if (result.error) { alert(result.error); return; }
    await refreshDeck();
  }

  function groupByType(cards) {
    const groups = {};
    for (const c of cards) {
      const t = primaryType(c.type_line);
      if (!groups[t]) groups[t] = [];
      groups[t].push(c);
    }
    const sorted = TYPE_ORDER.filter(t => groups[t]);
    if (groups['Other']) sorted.push('Other');
    return sorted.map(t => ({ name: t, cards: groups[t] }));
  }

  function groupByRole(cards) {
    const groups = {};
    const unassigned = [];
    for (const c of cards) {
      const roles = getCardRoles(c);
      if (roles.length === 0) {
        unassigned.push(c);
      } else {
        for (const role of roles) {
          if (!groups[role]) groups[role] = [];
          groups[role].push(c);
        }
      }
    }
    const sorted = Object.keys(groups).sort((a, b) => a.localeCompare(b));
    const result = sorted.map(r => ({ name: r, cards: groups[r] }));
    if (unassigned.length) result.push({ name: 'Unassigned', cards: unassigned });
    return result;
  }

  function renderList(cards) {
    const list = document.getElementById('card-list');
    if (cards.length === 0) {
      list.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center">No cards in this zone</div>';
      return;
    }

    const groups = groupBy === 'role' ? groupByRole(cards) : groupByType(cards);
    const isHypo = !!deck.hypothetical;

    let html = '';
    for (const group of groups) {
      const groupCount = group.cards.reduce((sum, c) => sum + cardQty(c), 0);
      html += `<div class="list-group">`;
      html += `<div class="list-group-header">${esc(group.name)} (${groupCount})</div>`;
      for (const c of group.cards) {
        const sc = c.set_code.toLowerCase();
        const cn = c.collector_number;
        const rarityColor = getRarityColor(c.rarity);
        const qty = cardQty(c);
        const qtyPrefix = qty > 1 ? `<span class="list-card-qty">${qty}x</span>` : '';

        // Subtitle: show roles when grouped by type, show type when grouped by role
        let subtitle = '';
        if (groupBy === 'type') {
          const roles = getCardRoles(c);
          if (roles.length) subtitle = roles.join(', ');
        } else {
          subtitle = primaryType(c.type_line);
        }

        const replaceData = isHypo
          ? `data-oracle-id="${esc(c.oracle_id)}" data-name="${esc(c.name)}"`
          : `data-cid="${c.id}" data-name="${esc(c.name)}" data-oracle-id="${esc(c.oracle_id || '')}"`;
        const removeData = isHypo
          ? `data-oracle-id="${esc(c.oracle_id)}" data-zone="${esc(c.deck_zone || 'mainboard')}"`
          : `data-cid="${c.id}"`;

        const isBasic = isHypo && /\bBasic\b/.test(c.type_line || '');
        let qtyControls = '';
        if (isBasic && isHypo) {
          qtyControls = `<span class="qty-controls list-qty-controls" data-oracle-id="${esc(c.oracle_id)}" data-zone="${esc(c.deck_zone || 'mainboard')}"><button class="qty-btn qty-minus">−</button><span class="qty-val">${qty}</span><button class="qty-btn qty-plus">+</button></span>`;
        }

        html += `<div class="list-card-row" data-image="${esc(c.image_uri || '')}" data-rarity-color="${rarityColor}" data-sc="${esc(sc)}" data-cn="${esc(cn)}">
          ${qtyPrefix}
          <div class="list-card-info">
            <a href="/card/${esc(sc)}/${esc(cn)}" class="list-card-name">${esc(c.name)}</a>
            ${subtitle ? `<span class="list-card-subtitle">${esc(subtitle)}</span>` : ''}
          </div>
          <span class="list-card-mana mana">${renderMana(c.mana_cost || '')}</span>
          ${qtyControls}
          <span class="list-card-actions">
            <button class="list-replace-btn" title="Replace" ${replaceData}>⇄</button>
            <button class="list-remove-btn" title="Remove" ${removeData}>✕</button>
          </span>
        </div>`;
      }
      html += `</div>`;
    }
    list.innerHTML = html;

    // Wire up quantity +/- buttons for basic lands
    if (isHypo) {
      list.querySelectorAll('.list-qty-controls').forEach(ctrl => {
        const oid = ctrl.dataset.oracleId;
        const zone = ctrl.dataset.zone;
        ctrl.querySelector('.qty-minus').addEventListener('click', () => updateQuantity(oid, zone, -1, ctrl));
        ctrl.querySelector('.qty-plus').addEventListener('click', () => updateQuantity(oid, zone, 1, ctrl));
      });
    }
  }

  async function removeCard(dataset) {
    const isHypo = !!deck.hypothetical;
    let body;
    if (isHypo) {
      body = { oracle_ids: [dataset.oracleId] };
    } else {
      body = { collection_ids: [parseInt(dataset.cid)] };
    }
    await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    await refreshDeck();
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
    await refreshDeck();
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
    const body = selectedIdsBody();
    await fetch(`/api/decks/${deck.id}/cards`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    selectedCardIds.clear();
    await refreshDeck();
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

    // Hypothetical decks use deck_expected_cards for their card list,
    // not for precon completeness tracking — hide this section entirely.
    if (deck.hypothetical) {
      section.style.display = 'none';
      return;
    }

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
    await refreshDeck();
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
    await refreshDeck();
  }

  // --- Dynamic button visibility ---
  function updateDynamicButtons() {
    const totalCards = allDeckCards.reduce((sum, c) => sum + cardQty(c), 0);
    const landCount = allDeckCards.filter(c =>
      (c.type_line || '').includes('Land') && c.deck_zone !== 'commander'
    ).reduce((sum, c) => sum + cardQty(c), 0);
    const hasPlan = !!(currentPlanTargets && Object.keys(currentPlanTargets).length);

    // Plan actions row (Add Card): always visible
    document.getElementById('plan-actions-row').style.display = '';

    // Autofill: hide if >90 cards or no plan
    const autofillBtn = document.getElementById('btn-autofill');
    autofillBtn.style.display = (hasPlan && totalCards <= 90) ? '' : 'none';

    // Autofill Lands: hide if >20 lands or no plan
    const fillLandsBtn = document.getElementById('btn-fill-lands');
    fillLandsBtn.style.display = (hasPlan && landCount <= 20) ? '' : 'none';
  }

  // --- Plan ---
  let planProgress = null;  // {tag: {current, target}} from audit
  let planTargetTags = new Set();  // tags from current plan targets
  let currentPlanTargets = null;  // {tag: count} — raw plan targets for editing

  // Infrastructure broad categories → sub-tags (mirrors INFRASTRUCTURE in constants.py)
  const INFRA_SUB_TAGS = {
    "Ramp": new Set(["ramp", "mana-dork", "mana-rock", "adds-multiple-mana", "extra-land", "repeatable-treasures"]),
    "Card Advantage": new Set(["draw", "card-advantage", "tutor", "repeatable-draw", "burst-draw", "impulse", "repeatable-impulsive-draw", "wheel", "curiosity-like", "life-for-cards", "bottle-draw"]),
    "Targeted Disruption": new Set(["removal", "creature-removal", "artifact-removal", "enchantment-removal", "planeswalker-removal", "removal-exile", "removal-toughness", "disenchant", "counter", "edict", "bounce", "graveyard-hate", "land-removal", "hand-disruption", "burn-creature", "lockdown", "humble", "control-changing-effects"]),
    "Mass Disruption": new Set(["boardwipe", "sweeper-one-sided", "multi-removal", "mass-land-denial", "tax"]),
  };

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

  async function runAutofill() {
    const btn = document.getElementById('btn-autofill');
    btn.disabled = true;
    btn.textContent = 'Filling...';

    try {
      const res = await fetch(`/api/decks/${deck.id}/autofill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset: true }),
      });

      // Non-SSE error response (e.g. missing plan)
      if (res.headers.get('content-type')?.includes('application/json')) return;

      // Parse SSE stream
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
            btn.textContent = parsed.message.length > 30
              ? parsed.message.slice(0, 30) + '…'
              : parsed.message;
          } else if (eventType === 'result') {
            data = parsed;
          } else if (eventType === 'error') {
            reader.cancel();
            return;
          } else if (eventType === 'done') {
            finished = true;
          }
        }
      }
      reader.cancel();

      if (!data) return;

      const suggestions = data.suggestions || {};
      const tags = Object.keys(suggestions);
      if (tags.length === 0) return;

      // Collect all suggested cards and add them directly
      let addBody;
      if (deck.hypothetical) {
        const oids = [];
        for (const tag of tags) {
          for (const card of suggestions[tag].cards) oids.push(card.oracle_id);
        }
        if (oids.length === 0) return;
        addBody = { oracle_ids: oids, zone: 'mainboard' };
      } else {
        const ids = [];
        for (const tag of tags) {
          for (const card of suggestions[tag].cards) ids.push(card.collection_id);
        }
        if (ids.length === 0) return;
        addBody = { collection_ids: ids, zone: 'mainboard' };
      }

      const addRes = await fetch(`/api/decks/${deck.id}/cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(addBody),
      });
      const result = await addRes.json();
      if (result.error) return;

      await refreshDeck();
    } finally {
      btn.disabled = false;
      btn.textContent = 'Autofill Nonland';
    }
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


  // --- Autofill Lands ---


  async function runFillLands() {
    const btn = document.getElementById('btn-fill-lands');
    btn.disabled = true;
    btn.textContent = 'Filling...';

    try {
      const res = await fetch(`/api/decks/${deck.id}/fill-lands`, { method: 'POST' });
      const data = await res.json();
      if (data.error) return;

      const nonbasic = data.suggestions?.nonbasic || [];
      const basic = data.suggestions?.basic || [];
      if (nonbasic.length === 0 && basic.length === 0) return;

      // Add all suggested lands directly
      let addBody;
      if (deck.hypothetical) {
        const oids = nonbasic.map(l => l.oracle_id);
        for (const g of basic) {
          if (g.count > 0 && g.oracle_id) {
            for (let i = 0; i < g.count; i++) oids.push(g.oracle_id);
          }
        }
        if (oids.length === 0) return;
        addBody = { oracle_ids: oids, zone: 'mainboard' };
      } else {
        const ids = nonbasic.map(l => l.collection_id);
        for (const g of basic) {
          if (g.count > 0 && g.collection_ids) {
            ids.push(...g.collection_ids.slice(0, g.count));
          }
        }
        if (ids.length === 0) return;
        addBody = { collection_ids: ids, zone: 'mainboard' };
      }

      const addRes = await fetch(`/api/decks/${deck.id}/cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(addBody),
      });
      const result = await addRes.json();
      if (result.error) return;

      await refreshDeck();
    } finally {
      btn.disabled = false;
      btn.textContent = 'Autofill Lands';
    }
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

  // --- Search modal (unified add/replace) ---
  let replaceCollectionId = null;
  let replaceOracleId = null;
  let replaceSelectedCandidate = null;
  let replaceMode = 'replace'; // 'replace' or 'add'

  function resetSearchModal() {
    replaceSelectedCandidate = null;
    document.getElementById('replace-confirm').disabled = true;
    document.getElementById('replace-confirm').textContent = replaceMode === 'add' ? 'Add' : 'Confirm';
    document.getElementById('replace-selection-label').textContent = 'No card selected';
    // Clear all filters
    document.getElementById('sf-name').value = '';
    document.getElementById('sf-cmc').value = '';
    document.getElementById('sf-tag').value = '';
    document.querySelectorAll('#sf-colors input, #sf-types input').forEach(cb => { cb.checked = false; });
    document.getElementById('sf-role').value = '';
    renderReplaceGrid([]);
  }

  async function openReplaceModal(collectionId, cardName, oracleId) {
    replaceMode = 'replace';
    replaceCollectionId = collectionId;
    replaceOracleId = oracleId || null;
    resetSearchModal();

    // Set title with role pills
    let titleHtml = `Replace: ${esc(cardName)}`;
    document.getElementById('search-modal-title').innerHTML = titleHtml;

    // Populate role selector
    populateRoleSelector();

    document.getElementById('replace-grid').innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">Loading...</div>';
    document.getElementById('search-modal').classList.add('active');

    // Fetch replacement data for role info
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

    // Add role pills to title
    if (cardRoles.length) {
      titleHtml += ' ' + cardRoles.map(r => `<span class="replace-role-pill">${esc(r)}</span>`).join('');
      document.getElementById('search-modal-title').innerHTML = titleHtml;
    }

    // Auto-select primary role in tag filter
    if (cardRoles.length > 0) {
      const primaryRole = cardRoles[0];
      document.getElementById('sf-tag').value = primaryRole;
      // Also select in role dropdown if it exists
      const roleSelect = document.getElementById('sf-role');
      if (roleSelect.querySelector(`option[value="${primaryRole}"]`)) {
        roleSelect.value = primaryRole;
      }
    }

    searchCards();
  }

  function openAddCardModal() {
    replaceMode = 'add';
    replaceCollectionId = null;
    replaceOracleId = null;
    resetSearchModal();

    document.getElementById('search-modal-title').textContent = 'Search';
    populateRoleSelector();
    document.getElementById('search-modal').classList.add('active');
    searchCards();
  }

  function populateRoleSelector() {
    const roleSelect = document.getElementById('sf-role');
    if (currentPlanTargets && Object.keys(currentPlanTargets).length > 0) {
      const sorted = Object.entries(currentPlanTargets).sort(([a], [b]) => {
        if (a === 'lands') return -1;
        if (b === 'lands') return 1;
        return a.localeCompare(b);
      });
      roleSelect.innerHTML = '<option value="">— Role —</option>' +
        sorted.map(([tag, val]) => {
          const current = (planProgress && planProgress[tag]) ? planProgress[tag].current : 0;
          return `<option value="${esc(tag)}">${esc(val.label)} (${current}/${val.count})</option>`;
        }).join('');
      roleSelect.style.display = '';
    } else {
      roleSelect.style.display = 'none';
    }
  }

  function renderReplaceGrid(candidates) {
    const grid = document.getElementById('replace-grid');
    if (!candidates || candidates.length === 0) {
      grid.innerHTML = '<div style="padding:24px;color:var(--text-secondary);text-align:center;grid-column:1/-1">No candidates found</div>';
      return;
    }
    grid.innerHTML = candidates.map(c => {
      const rolesText = getCardRoles(c).join(', ');
      const rarityColor = getRarityColor(c.rarity);
      const foilClass = (c.finish === 'foil' || c.finish === 'etched') ? ' foil' : '';
      return `<div class="sheet-card replace-candidate" data-cid="${c.collection_id}" data-oracle-id="${esc(c.oracle_id || '')}" data-name="${esc(c.name)}">
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
      oracle_id: el.dataset.oracleId || null,
      name: el.dataset.name,
    };
    document.getElementById('replace-selection-label').textContent = replaceSelectedCandidate.name;
    document.getElementById('replace-confirm').disabled = false;
  }

  async function searchCards() {
    const name = document.getElementById('sf-name').value.trim();
    const cmc = document.getElementById('sf-cmc').value.trim();
    const tag = document.getElementById('sf-tag').value.trim();

    // Collect color checkboxes
    const colors = [...document.querySelectorAll('#sf-colors input:checked')].map(cb => cb.value);
    // Collect type checkboxes
    const types = [...document.querySelectorAll('#sf-types input:checked')].map(cb => cb.value);

    const params = new URLSearchParams();
    params.set('status', 'owned');
    if (name) params.set('q', name);
    if (cmc) params.set('filter_cmc_min', cmc);
    if (cmc) params.set('filter_cmc_max', cmc);
    if (tag) params.set('filter_tag', tag);
    for (const c of colors) params.append('filter_color', c);
    for (const t of types) params.append('filter_type[]', t);

    // Get commander CI for filtering
    const commanders = allDeckCards.filter(c => c.deck_zone === 'commander');
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
    const candidates = cards.filter(c => c.collection_id || c.oracle_id).map(c => ({
      collection_id: c.collection_id,
      oracle_id: c.oracle_id,
      name: c.name,
      mana_cost: c.mana_cost,
      image_uri: c.image_uri,
      rarity: c.rarity,
      finish: c.finish,
      tags: (c.card_tags || []).join(','),
    }));
    renderReplaceGrid(candidates);
  }

  async function confirmReplacement() {
    if (!replaceSelectedCandidate) return;

    if (replaceMode === 'add') {
      const body = deck.hypothetical
        ? { oracle_ids: [replaceSelectedCandidate.oracle_id], zone: 'mainboard' }
        : { collection_ids: [replaceSelectedCandidate.collection_id], zone: 'mainboard' };
      const res = await fetch(`/api/decks/${deck.id}/cards`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const result = await res.json();
      if (result.error) { alert(result.error); return; }
      closeModal('search-modal');
      await refreshDeck();
      return;
    }

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
    closeModal('search-modal');
    await refreshDeck();
  }

  // --- Utils ---
  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }

  // --- Initial render ---
  renderDeckDetail();
  loadPlan();
  loadCompleteness();
  fetch('/api/settings').then(r => r.json()).then(s => {
    const saved = s.default_card_view || 'list';
    currentView = saved === 'grid' ? 'list' : saved;
    updateViewButtons();
    loadDeckCards();
  });
})();
