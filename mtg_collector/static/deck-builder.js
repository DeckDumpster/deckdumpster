/* deck-builder.js — Commander deck builder page */
(async function() {
  const root = document.getElementById('deck-builder-root');
  const pathParts = window.location.pathname.split('/').filter(Boolean);
  // /deck-builder → create mode, /deck-builder/123 → builder mode
  const deckId = pathParts.length > 1 ? pathParts[1] : null;

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
          <label>Deck Type</label>
          <div class="radio-group">
            <label><input type="radio" name="deck-type" value="physical" checked> Physical</label>
            <label><input type="radio" name="deck-type" value="hypothetical"> Hypothetical</label>
          </div>
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
      const hypo = document.querySelector('input[name="deck-type"]:checked').value === 'hypothetical';
      const res = await fetch('/api/deck-builder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          commander_oracle_id: selectedCommander.oracle_id,
          commander_printing_id: selectedCommander.printing_id,
          hypothetical: hypo,
        }),
      });
      const deck = await res.json();
      if (deck.error) {
        createBtn.textContent = 'Create Deck';
        createBtn.disabled = false;
        alert(deck.error);
        return;
      }
      history.pushState(null, '', '/deck-builder/' + deck.id);
      document.title = deck.name + ' — Deck Builder';
      await loadBuilder(deck.id);
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
    renderBuilder(data);
  }

  function renderBuilder(data) {
    const { deck, commander, groups } = data;
    const previewImg = commander && commander.image_uri
      ? commander.image_uri.replace('/large/', '/normal/')
      : '';
    const previewName = commander ? commander.name : '';

    let totalCards = 0;
    for (const g of Object.values(groups)) totalCards += g.length;

    root.innerHTML = `
      <div class="builder-layout">
        <div class="card-preview">
          ${previewImg ? `<img id="preview-img" src="${esc(previewImg)}" alt="${esc(previewName)}">` : ''}
          <div class="preview-name" id="preview-name">${esc(previewName)}</div>
        </div>
        <div class="deck-list">
          <div class="deck-header">
            <h2>${esc(deck.name)}</h2>
            <span class="card-count">${totalCards}/100</span>
            ${deck.hypothetical ? '<span class="hypothetical-badge">Hypothetical</span>' : ''}
            <button class="add-btn" id="add-card-btn">+ Add Card</button>
            <a class="detail-link" href="/decks/${deck.id}">Detail</a>
            <button class="delete-btn" id="delete-deck-btn">Delete</button>
          </div>
          <div id="type-groups">${renderGroups(groups, commander)}</div>
        </div>
      </div>`;

    // Hover preview
    const previewImgEl = document.getElementById('preview-img');
    const previewNameEl = document.getElementById('preview-name');
    const defaultImg = previewImg;
    const defaultName = previewName;

    document.getElementById('type-groups').addEventListener('mouseenter', (e) => {
      const row = e.target.closest('.card-row');
      if (!row || !previewImgEl) return;
      const img = row.dataset.imageUri;
      const name = row.dataset.cardName;
      if (img) previewImgEl.src = img.replace('/large/', '/normal/');
      if (name) previewNameEl.textContent = name;
    }, true);

    document.getElementById('type-groups').addEventListener('mouseleave', () => {
      if (!previewImgEl) return;
      if (defaultImg) previewImgEl.src = defaultImg;
      previewNameEl.textContent = defaultName;
    });

    // Remove card
    document.getElementById('type-groups').addEventListener('click', async (e) => {
      const btn = e.target.closest('.remove-btn');
      if (!btn) return;
      const cid = parseInt(btn.dataset.collectionId, 10);
      await fetch('/api/deck-builder/' + deck.id + '/cards', {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ collection_id: cid }),
      });
      await loadBuilder(deck.id);
    });

    // Add card modal
    document.getElementById('add-card-btn').addEventListener('click', () => {
      showAddModal(deck.id);
    });

    // Delete deck
    document.getElementById('delete-deck-btn').addEventListener('click', async () => {
      if (!confirm(`Delete "${deck.name}"? Cards will be unassigned but not deleted.`)) return;
      await fetch('/api/decks/' + deck.id, { method: 'DELETE' });
      window.location.href = '/decks';
    });
  }

  function renderGroups(groups, commander) {
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
      html += `<div class="type-group">
        <div class="type-group-header">${esc(type)} <span class="group-count">(${cards.length})</span></div>`;
      for (const c of cards) {
        html += `<div class="card-row" data-image-uri="${esc(c.image_uri || '')}" data-card-name="${esc(c.name)}">
          <span class="card-name"><a href="/card/${esc(c.set_code)}/${esc(c.collector_number)}">${esc(c.name)}</a></span>
          <span class="mana-icons">${renderMana(c.mana_cost)}</span>
          <button class="remove-btn" data-collection-id="${c.id}" title="Remove">&times;</button>
        </div>`;
      }
      html += '</div>';
    }
    return html;
  }

  // ── Add Card Modal ──

  function showAddModal(deckId) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <h3>Add Card</h3>
          <button class="modal-close">&times;</button>
        </div>
        <div class="modal-body">
          <input type="text" id="search-input" placeholder="Search cards..." autocomplete="off">
          <div id="search-results"></div>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const searchInput = overlay.querySelector('#search-input');
    const resultsDiv = overlay.querySelector('#search-results');
    let timer = null;

    searchInput.focus();

    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      const q = searchInput.value.trim();
      if (q.length < 2) { resultsDiv.innerHTML = ''; return; }
      timer = setTimeout(() => searchCards(q), 250);
    });

    async function searchCards(q) {
      const res = await fetch('/api/deck-builder/' + deckId + '/search?q=' + encodeURIComponent(q));
      const cards = await res.json();
      if (!cards.length) {
        resultsDiv.innerHTML = '<div style="color:var(--text-secondary);padding:8px">No results</div>';
        return;
      }
      resultsDiv.innerHTML = cards.map(c => `
        <div class="search-result">
          <span class="result-name">${esc(c.name)}</span>
          <span class="mana-icons">${renderMana(c.mana_cost)}</span>
          <button class="result-add" data-collection-id="${c.id}">Add</button>
        </div>`).join('');
    }

    resultsDiv.addEventListener('click', async (e) => {
      const btn = e.target.closest('.result-add');
      if (!btn) return;
      btn.disabled = true;
      btn.textContent = '...';
      const cid = parseInt(btn.dataset.collectionId, 10);
      const res = await fetch('/api/deck-builder/' + deckId + '/cards', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ collection_id: cid }),
      });
      const result = await res.json();
      if (result.error) {
        btn.textContent = 'Error';
        return;
      }
      // Remove the added card from results
      btn.closest('.search-result').remove();
      // Refresh deck list in background
      await loadBuilder(deckId);
      // Re-show modal on top
    });

    // Close modal
    overlay.querySelector('.modal-close').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
  }
})();
