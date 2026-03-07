/* card-detail.js — Standalone card detail page logic. */

(async function() {
  // Extract set_code and collector_number from URL: /card/:set/:cn
  const pathParts = window.location.pathname.split('/').filter(Boolean);
  // pathParts = ['card', 'set_code', 'collector_number']
  if (pathParts.length < 3 || pathParts[0] !== 'card') {
    document.getElementById('loading-state').innerHTML = '<div class="empty-state">Invalid card URL. Expected /card/:set/:cn</div>';
    return;
  }
  const setCode = pathParts[1].toLowerCase();
  const collectorNumber = pathParts.slice(2).join('/'); // CN can contain slashes

  // Parallel data fetching
  const [cardRes, settingsRes, decksRes, bindersRes] = await Promise.all([
    fetch(`/api/card/by-set-cn?set=${encodeURIComponent(setCode)}&cn=${encodeURIComponent(collectorNumber)}`),
    fetch('/api/settings').catch(() => ({ ok: false })),
    fetch('/api/decks').catch(() => ({ ok: false })),
    fetch('/api/binders').catch(() => ({ ok: false })),
  ]);

  if (!cardRes.ok) {
    const err = await cardRes.json().catch(() => ({}));
    document.getElementById('loading-state').innerHTML =
      `<div class="empty-state">${esc(err.error || 'Card not found')}</div>`;
    return;
  }

  const card = await cardRes.json();
  const _settings = settingsRes.ok ? await settingsRes.json() : {};
  let allDecks = decksRes.ok ? await decksRes.json() : [];
  let allBinders = bindersRes.ok ? await bindersRes.json() : [];

  document.title = `${card.name} — DeckDumpster`;

  // Build the page
  const layout = document.getElementById('card-detail-layout');
  const isDfc = DFC_LAYOUTS.includes(card.layout);
  const frontSrc = card.image_uri || '';
  const backSrc = isDfc ? frontSrc.replace('/front/', '/back/') : '/static/card_back.jpeg';

  layout.innerHTML = `
    <div class="card-image-section">
      <div class="card-flip-container" id="card-flip">
        <div class="card-flip-front">
          <img src="${frontSrc}" alt="${esc(card.name)}" id="img-front">
        </div>
        <div class="card-flip-back">
          <img src="${backSrc}" alt="${isDfc ? 'Back face' : 'Card back'}" id="img-back">
        </div>
      </div>
      <button class="flip-btn" id="flip-btn" title="Flip card">&#x21BB;</button>
    </div>
    <div class="card-details-panel" id="details-panel"></div>
  `;

  // Flip button
  let showingBack = false;
  document.getElementById('flip-btn').addEventListener('click', () => {
    showingBack = !showingBack;
    document.getElementById('card-flip').classList.toggle('flipped');
    if (isDfc) renderDetails(showingBack ? 1 : 0);
  });

  // DFC face splitting
  const names = card.name.split(' // ');
  const types = (card.type_line || '').split(' // ');
  const manas = (card.mana_cost || '').split(' // ');
  const isArtSeries = card.layout === 'art_series';

  // Set info
  const sc = card.set_code.toLowerCase();
  const rarityClass = `ss-${card.rarity || 'common'}`;
  const setIcon = `<i class="ss ss-${sc} ${rarityClass} ss-grad"></i>`;
  const setName = card.set_name || card.set_code.toUpperCase();
  const rarity = card.rarity ? card.rarity.charAt(0).toUpperCase() + card.rarity.slice(1) : '';

  // Prices
  const tcgPrice = card.tcg_price ? `$${parseFloat(card.tcg_price).toFixed(2)}` : '';
  const ckPrice = card.ck_price ? `$${parseFloat(card.ck_price).toFixed(2)}` : '';
  const sfUrl = `https://scryfall.com/card/${sc}/${card.collector_number}`;
  const ckUrl = getCkUrl(card);

  // Treatment tags
  const fe = parseJsonField(card.frame_effects);
  let tagsHtml = '';
  if (card.border_color === 'borderless') tagsHtml += '<span class="treat-tag">Borderless</span>';
  if (fe.includes('showcase')) tagsHtml += '<span class="treat-tag">Showcase</span>';
  if (fe.includes('extendedart')) tagsHtml += '<span class="treat-tag">Extended Art</span>';
  if (card.full_art) tagsHtml += '<span class="treat-tag">Full Art</span>';
  if (fe.includes('inverted')) tagsHtml += '<span class="treat-tag">Inverted</span>';
  if (card.promo) tagsHtml += '<span class="promo-tag">Promo</span>';

  // Wishlist state
  let wishlistEntry = null;
  try {
    const wlRes = await fetch(`/api/wishlist?name=${encodeURIComponent(card.name.split(' // ')[0])}`);
    if (wlRes.ok) {
      const wlData = await wlRes.json();
      const items = wlData.items || wlData;
      if (Array.isArray(items)) {
        wishlistEntry = items.find(w =>
          (w.printing_id && w.printing_id === card.printing_id) ||
          (w.oracle_id && w.oracle_id === card.oracle_id)
        ) || null;
      }
    }
  } catch {}

  function renderDetails(faceIdx) {
    let faceName, faceType, faceMana;
    if (isDfc && names.length > 1) {
      faceName = names[faceIdx] || names[0];
      faceType = isArtSeries ? 'Art Series' : (types[faceIdx] || types[0] || '');
      faceMana = manas[faceIdx] || manas[0] || '';
    } else {
      faceName = isArtSeries ? names[0] : card.name;
      faceType = isArtSeries ? 'Art Series' : (card.type_line || '');
      faceMana = card.mana_cost || '';
    }
    const manaHtml = faceMana ? renderMana(faceMana) : '';
    const cmcText = card.cmc != null ? card.cmc : '';

    const panel = document.getElementById('details-panel');
    panel.innerHTML = `
      <h2>${esc(faceName)}</h2>
      ${card.oracle_name ? `<div style="font-size:0.85rem;color:#888;margin-top:2px">${esc(card.oracle_name)}</div>` : ''}
      ${manaHtml ? `<div class="detail-mana">${manaHtml}</div>` : ''}
      <div class="detail-section">
        <span class="detail-section-title">Type</span>
        <span class="value">${esc(faceType)}</span>
        ${cmcText !== '' ? `<div class="detail-row"><span class="label">Mana Value</span><span class="value">${cmcText}</span></div>` : ''}
      </div>
      <div class="detail-section">
        <span class="detail-section-title">Printing</span>
        <div class="detail-row"><span class="label">Set</span><span class="value">${setIcon} ${esc(setName)} (${card.set_code.toUpperCase()})</span></div>
        <div class="detail-row"><span class="label">Number</span><span class="value">${esc(card.collector_number || '')}</span></div>
        <div class="detail-row"><span class="label">Rarity</span><span class="value">${esc(rarity)}</span></div>
        ${card.artist ? `<div class="detail-row"><span class="label">Artist</span><span class="value">${esc(card.artist)}</span></div>` : ''}
      </div>
      ${tagsHtml ? `<div class="detail-section"><span class="detail-section-title">Treatments</span><div class="detail-tags">${tagsHtml}</div></div>` : ''}
      <div class="detail-section">
        <div class="detail-links">
          <a class="badge link" href="${sfUrl}" target="_blank" rel="noopener">SF${tcgPrice ? ' ' + tcgPrice : ''}</a>
          <a class="badge link" href="${ckUrl}" target="_blank" rel="noopener">CK${ckPrice ? ' ' + ckPrice : ''}</a>
          <button class="want-btn${wishlistEntry ? ' wanted' : ''}" id="want-btn">${wishlistEntry ? 'Wanted' : 'Want'}</button>
          <button class="add-collection-btn" id="add-btn">Add</button>
        </div>
      </div>
      <div id="add-form-container"></div>
      <div id="copies-container"><div style="color:#888;font-size:0.85rem;padding:8px 0;">Loading copies...</div></div>
      <div class="price-chart-section" id="price-chart-section">
        <div class="detail-section">
          <span class="detail-section-title">Price History</span>
          <div class="price-range-pills" id="price-range-pills">
            <button class="price-range-pill active" data-range="30">1M</button>
            <button class="price-range-pill" data-range="90">3M</button>
            <button class="price-range-pill" data-range="180">6M</button>
            <button class="price-range-pill" data-range="365">1Y</button>
            <button class="price-range-pill" data-range="0">ALL</button>
          </div>
          <div class="price-chart-canvas-wrap"><canvas id="price-chart-canvas"></canvas></div>
        </div>
      </div>
    `;

    // Wire up want button
    document.getElementById('want-btn').addEventListener('click', handleWant);
    // Wire up add button
    document.getElementById('add-btn').addEventListener('click', handleAdd);
    // Load copies
    loadCopies();
  }

  renderDetails(0);
  renderPriceChart();

  // --- Want handler ---
  async function handleWant() {
    const btn = document.getElementById('want-btn');
    if (wishlistEntry) {
      await fetch(`/api/wishlist/${wishlistEntry.id}`, { method: 'DELETE' });
      wishlistEntry = null;
      btn.classList.remove('wanted');
      btn.textContent = 'Want';
    } else {
      const body = { name: card.name.split(' // ')[0] };
      if (card.set_code) body.set_code = card.set_code;
      if (card.collector_number) body.collector_number = card.collector_number;
      const res = await fetch('/api/wishlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const result = await res.json();
      if (result.id) {
        wishlistEntry = { id: result.id, oracle_id: card.oracle_id, printing_id: result.printing_id };
        btn.classList.add('wanted');
        btn.textContent = 'Wanted';
      }
    }
  }

  // --- Add to collection handler ---
  function handleAdd() {
    const container = document.getElementById('add-form-container');
    if (!container) return;
    if (container.querySelector('.add-collection-form')) {
      container.innerHTML = '';
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    container.innerHTML = `<div class="add-collection-form">
      <input type="date" id="add-date" value="${today}">
      <input type="number" step="0.01" min="0" id="add-price" placeholder="Price">
      <input type="text" id="add-source" placeholder="Source">
      <button id="add-confirm-btn">Confirm</button>
    </div>`;
    container.querySelector('#add-confirm-btn').addEventListener('click', async () => {
      const confirmBtn = container.querySelector('#add-confirm-btn');
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Adding...';
      const body = {
        printing_id: card.printing_id,
        finish: card.finishes ? parseJsonField(card.finishes)[0] || 'nonfoil' : 'nonfoil',
        acquired_at: container.querySelector('#add-date').value || today,
      };
      const priceVal = container.querySelector('#add-price').value;
      if (priceVal) body.purchase_price = parseFloat(priceVal);
      const sourceVal = container.querySelector('#add-source').value.trim();
      if (sourceVal) body.source = sourceVal;
      const res = await fetch('/api/collection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        container.innerHTML = '';
        loadCopies();
      } else {
        const err = await res.json();
        alert(err.error || 'Add failed');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm';
      }
    });
  }

  // --- Load and render copies ---
  async function loadCopies() {
    const container = document.getElementById('copies-container');
    if (!container) return;
    try {
      const res = await fetch(`/api/collection/copies?printing_id=${encodeURIComponent(card.printing_id)}`);
      const copies = await res.json();
      if (!copies.length) {
        container.innerHTML = '';
        return;
      }
      container.innerHTML =
        `<div class="detail-section"><span class="detail-section-title">Copies (${copies.length})</span></div>` +
        copies.map(copy => renderCopySection(copy)).join('');

      wireUpCopyHandlers(container);
    } catch (e) {
      container.innerHTML = `<div style="color:#e87e7e;font-size:0.85rem;">Failed to load copies</div>`;
    }
  }

  // --- Reload container data (decks/binders) ---
  async function loadContainerData() {
    const [dr, br] = await Promise.all([
      fetch('/api/decks').catch(() => ({ ok: false })),
      fetch('/api/binders').catch(() => ({ ok: false })),
    ]);
    if (dr.ok) allDecks = await dr.json();
    if (br.ok) allBinders = await br.json();
  }

  // --- Render a single copy section ---
  function renderCopySection(copy) {
    const date = copy.acquired_at ? new Date(copy.acquired_at).toLocaleDateString() : '';
    const isActive = copy.status === 'owned' || copy.status === 'listed';
    const isDeleteable = copy.status === 'owned' || copy.status === 'ordered';

    let statusBadge = '';
    if (!isActive) {
      const lastLog = copy.status_history && copy.status_history.length
        ? copy.status_history[copy.status_history.length - 1] : null;
      const note = lastLog && lastLog.note ? ` — ${lastLog.note}` : '';
      const logDate = lastLog ? new Date(lastLog.changed_at).toLocaleDateString() : '';
      statusBadge = `<span class="disposition-badge ${copy.status}">${copy.status}</span>`;
      if (logDate || note) statusBadge += `<span style="font-size:0.75rem;color:#888;margin-left:6px;">${logDate}${note}</span>`;
    }

    let orderHtml = '';
    if (copy.order_id) {
      orderHtml = `<div class="detail-row"><span class="label">Order</span><span class="value">${esc(copy.seller_name || '')} #${esc(copy.order_number || '')}${copy.order_date ? ' (' + copy.order_date + ')' : ''}</span></div>`;
    }

    let lineageHtml = '';
    if (copy.image_md5 && copy.image_id) {
      lineageHtml = `<div class="detail-row"><span class="label">Lineage</span><span class="value" style="display:flex;gap:8px;align-items:center;">
        <button class="reprocess-btn" data-image-id="${copy.image_id}" data-image-md5="${esc(copy.image_md5)}" style="padding:2px 8px;font-size:0.8rem;background:#0f3460;color:#e0e0e0;border:1px solid #16213e;border-radius:4px;cursor:pointer;">Reprocess</button>
        <button class="refinish-btn" data-image-id="${copy.image_id}" data-image-md5="${esc(copy.image_md5)}" style="padding:2px 8px;font-size:0.8rem;background:#0f3460;color:#e0e0e0;border:1px solid #16213e;border-radius:4px;cursor:pointer;">Refinish</button>
      </span></div>`;
    }

    let priceHtml = '';
    if (copy.purchase_price) {
      priceHtml = `<div class="detail-row"><span class="label">Price</span><span class="value">$${parseFloat(copy.purchase_price).toFixed(2)}</span></div>`;
    }
    if (copy.sale_price) {
      priceHtml += `<div class="detail-row"><span class="label">Sale Price</span><span class="value">$${parseFloat(copy.sale_price).toFixed(2)}</span></div>`;
    }

    // Deck/binder assignment row
    let assignHtml = '';
    if (isActive) {
      if (copy.deck_id) {
        const binderOpts = allBinders.map(b => `<option value="${b.id}">${esc(b.name)}</option>`).join('');
        assignHtml = `<div class="detail-row"><span class="label">Deck</span><span class="value">
          ${esc(copy.deck_name || 'Deck #' + copy.deck_id)}
          <a href="#" class="copy-remove-deck" data-copy-id="${copy.id}" data-deck-id="${copy.deck_id}" style="color:#e94560;margin-left:8px;font-size:0.8rem;">Remove</a>
          <select class="copy-move-to-binder" data-copy-id="${copy.id}" style="margin-left:8px;padding:2px 6px;font-size:0.8rem;background:#1a1a2e;color:#e0e0e0;border:1px solid #0f3460;border-radius:4px;">
            <option value="">Move to Binder ▾</option>${binderOpts}<option value="__new__">New Binder...</option></select>
        </span></div>`;
      } else if (copy.binder_id) {
        const deckOpts = allDecks.map(d => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
        assignHtml = `<div class="detail-row"><span class="label">Binder</span><span class="value">
          ${esc(copy.binder_name || 'Binder #' + copy.binder_id)}
          <a href="#" class="copy-remove-binder" data-copy-id="${copy.id}" data-binder-id="${copy.binder_id}" style="color:#e94560;margin-left:8px;font-size:0.8rem;">Remove</a>
          <select class="copy-move-to-deck" data-copy-id="${copy.id}" style="margin-left:8px;padding:2px 6px;font-size:0.8rem;background:#1a1a2e;color:#e0e0e0;border:1px solid #0f3460;border-radius:4px;">
            <option value="">Move to Deck ▾</option>${deckOpts}<option value="__new__">New Deck...</option></select>
        </span></div>`;
      } else {
        const deckOpts = allDecks.map(d => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
        const binderOpts = allBinders.map(b => `<option value="${b.id}">${esc(b.name)}</option>`).join('');
        assignHtml = `<div class="detail-row"><span class="label">Location</span><span class="value">Unassigned
          <select class="copy-add-to-deck" data-copy-id="${copy.id}" style="margin-left:8px;padding:2px 6px;font-size:0.8rem;background:#1a1a2e;color:#e0e0e0;border:1px solid #0f3460;border-radius:4px;">
            <option value="">Add to Deck ▾</option>${deckOpts}<option value="__new__">New Deck...</option></select>
          <select class="copy-add-to-binder" data-copy-id="${copy.id}" style="margin-left:8px;padding:2px 6px;font-size:0.8rem;background:#1a1a2e;color:#e0e0e0;border:1px solid #0f3460;border-radius:4px;">
            <option value="">Add to Binder ▾</option>${binderOpts}<option value="__new__">New Binder...</option></select>
        </span></div>`;
      }
    }

    const condLabel = copy.condition || 'Near Mint';
    const finLabel = copy.finish ? copy.finish.charAt(0).toUpperCase() + copy.finish.slice(1) : '';

    // Receive button for ordered copies
    const receiveHtml = copy.status === 'ordered'
      ? `<button class="receive-btn" data-collection-id="${copy.id}" style="padding:2px 8px;font-size:0.8rem;background:#1a5c3a;border:1px solid #2a8c5a;color:#7ee8b0;border-radius:4px;cursor:pointer;font-weight:600;">Receive</button>`
      : '';

    let controlsHtml = '';
    if (isActive) {
      controlsHtml = `<div class="dispose-controls">
        <select class="dispose-select">
          <option value="">Dispose...</option>
          <option value="sold">Sold</option>
          <option value="traded">Traded</option>
          <option value="gifted">Gifted</option>
          <option value="lost">Lost</option>
          ${copy.status === 'owned' ? '<option value="listed">Listed</option>' : ''}
          ${copy.status === 'listed' ? '<option value="owned">Unlist</option>' : ''}
        </select>
        <input type="number" step="0.01" placeholder="Price" class="dispose-price">
        <input type="text" placeholder="Note" class="dispose-note">
        <button class="dispose-btn" data-id="${copy.id}">Dispose</button>
        ${isDeleteable ? `<button class="delete-copy-btn" data-id="${copy.id}">Delete</button>` : ''}
      </div>`;
    } else if (isDeleteable) {
      controlsHtml = `<div class="dispose-controls">
        <button class="delete-copy-btn" data-id="${copy.id}">Delete</button>
      </div>`;
    }

    return `<div class="copy-section" data-copy-id="${copy.id}">
      <div class="copy-header">
        <span>${esc(finLabel)} ${esc(condLabel)} — ${esc(copy.source || '')} ${date ? '(' + date + ')' : ''} ${receiveHtml}</span>
        <span class="copy-id">#${copy.id}</span>
      </div>
      ${statusBadge ? `<div style="margin-bottom:6px;">${statusBadge}</div>` : ''}
      ${orderHtml}${priceHtml}${lineageHtml}${assignHtml}
      ${controlsHtml}
      <button class="history-toggle" data-copy-id="${copy.id}">History &#x25BE;</button>
      <div class="history-container" id="history-${copy.id}"></div>
    </div>`;
  }

  // --- Wire up all copy action handlers ---
  function wireUpCopyHandlers(container) {
    const refreshAfterAction = () => { loadCopies(); loadContainerData(); };

    // Receive
    container.querySelectorAll('.receive-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.textContent = '...';
        const cid = btn.dataset.collectionId;
        const res = await fetch(`/api/collection/${cid}/receive`, { method: 'POST' });
        const result = await res.json();
        if (result.received) {
          loadCopies();
        } else {
          btn.textContent = 'Failed';
        }
      });
    });

    // Dispose
    container.querySelectorAll('.dispose-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.id);
        const row = btn.closest('.copy-section');
        const sel = row.querySelector('.dispose-select');
        const priceInput = row.querySelector('.dispose-price');
        const noteInput = row.querySelector('.dispose-note');
        const newStatus = sel.value;
        if (!newStatus) return;
        btn.disabled = true;
        btn.textContent = 'Saving...';
        const body = { new_status: newStatus };
        if (priceInput && priceInput.value) body.sale_price = parseFloat(priceInput.value);
        if (noteInput && noteInput.value) body.note = noteInput.value;
        const r = await fetch(`/api/collection/${id}/dispose`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (r.ok) {
          loadCopies();
        } else {
          const err = await r.json();
          alert(err.error || 'Dispose failed');
          btn.disabled = false;
          btn.textContent = 'Dispose';
        }
      });
    });

    // Delete
    container.querySelectorAll('.delete-copy-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.id);
        if (!confirm(`Delete copy #${id}? This cannot be undone.`)) return;
        btn.disabled = true;
        btn.textContent = 'Deleting...';
        const r = await fetch(`/api/collection/${id}?confirm=true`, { method: 'DELETE' });
        if (r.ok) {
          loadCopies();
        } else {
          const err = await r.json();
          alert(err.error || 'Delete failed');
          btn.disabled = false;
          btn.textContent = 'Delete';
        }
      });
    });

    // Reprocess
    container.querySelectorAll('.reprocess-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const imageId = parseInt(btn.dataset.imageId);
        const md5 = btn.dataset.imageMd5;
        const allFromImage = container.querySelectorAll(`.reprocess-btn[data-image-md5="${md5}"]`).length;
        const msg = allFromImage > 1
          ? `This will delete ALL ${allFromImage} cards from this image and re-identify them. Continue?`
          : 'This will delete this card from your collection and re-identify it. Continue?';
        if (!confirm(msg)) return;
        btn.disabled = true;
        btn.textContent = 'Reprocessing...';
        const r = await fetch('/api/ingest2/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_id: imageId }),
        });
        if (r.ok) {
          loadCopies();
        } else {
          const err = await r.json();
          alert(err.error || 'Reprocess failed');
          btn.disabled = false;
          btn.textContent = 'Reprocess';
        }
      });
    });

    // Refinish
    container.querySelectorAll('.refinish-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const imageId = parseInt(btn.dataset.imageId);
        const md5 = btn.dataset.imageMd5;
        const allFromImage = container.querySelectorAll(`.refinish-btn[data-image-md5="${md5}"]`).length;
        const msg = allFromImage > 1
          ? `This will remove ALL ${allFromImage} cards from this image so you can fix the finish. Continue?`
          : 'This will remove this card from your collection so you can fix the finish. Continue?';
        if (!confirm(msg)) return;
        btn.disabled = true;
        btn.textContent = 'Refinishing...';
        const r = await fetch('/api/ingest2/refinish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_id: imageId }),
        });
        if (r.ok) {
          loadCopies();
        } else {
          const err = await r.json();
          alert(err.error || 'Refinish failed');
          btn.disabled = false;
          btn.textContent = 'Refinish';
        }
      });
    });

    // Deck assignment
    container.querySelectorAll('.copy-add-to-deck').forEach(sel => {
      sel.addEventListener('change', async () => {
        if (!sel.value) return;
        let deckId = sel.value;
        if (deckId === '__new__') {
          const name = prompt('New deck name:');
          if (!name) { sel.value = ''; return; }
          const cr = await fetch('/api/decks', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
          const created = await cr.json();
          if (created.error) { alert(created.error); sel.value = ''; return; }
          deckId = created.id;
          await loadContainerData();
        }
        const r = await fetch(`/api/decks/${deckId}/cards`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(sel.dataset.copyId)], zone: 'mainboard' }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); sel.value = ''; return; }
        refreshAfterAction();
      });
    });

    // Binder assignment
    container.querySelectorAll('.copy-add-to-binder').forEach(sel => {
      sel.addEventListener('change', async () => {
        if (!sel.value) return;
        let binderId = sel.value;
        if (binderId === '__new__') {
          const name = prompt('New binder name:');
          if (!name) { sel.value = ''; return; }
          const cr = await fetch('/api/binders', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
          const created = await cr.json();
          if (created.error) { alert(created.error); sel.value = ''; return; }
          binderId = created.id;
          await loadContainerData();
        }
        const r = await fetch(`/api/binders/${binderId}/cards`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(sel.dataset.copyId)] }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); sel.value = ''; return; }
        refreshAfterAction();
      });
    });

    // Remove from deck
    container.querySelectorAll('.copy-remove-deck').forEach(link => {
      link.addEventListener('click', async (e) => {
        e.preventDefault();
        const r = await fetch(`/api/decks/${link.dataset.deckId}/cards`, {
          method: 'DELETE', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(link.dataset.copyId)] }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); return; }
        refreshAfterAction();
      });
    });

    // Remove from binder
    container.querySelectorAll('.copy-remove-binder').forEach(link => {
      link.addEventListener('click', async (e) => {
        e.preventDefault();
        const r = await fetch(`/api/binders/${link.dataset.binderId}/cards`, {
          method: 'DELETE', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(link.dataset.copyId)] }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); return; }
        refreshAfterAction();
      });
    });

    // Move to deck (from binder)
    container.querySelectorAll('.copy-move-to-deck').forEach(sel => {
      sel.addEventListener('change', async () => {
        if (!sel.value) return;
        let deckId = sel.value;
        if (deckId === '__new__') {
          const name = prompt('New deck name:');
          if (!name) { sel.value = ''; return; }
          const cr = await fetch('/api/decks', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
          const created = await cr.json();
          if (created.error) { alert(created.error); sel.value = ''; return; }
          deckId = created.id;
          await loadContainerData();
        }
        const r = await fetch(`/api/decks/${deckId}/cards/move`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(sel.dataset.copyId)], zone: 'mainboard' }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); sel.value = ''; return; }
        refreshAfterAction();
      });
    });

    // Move to binder (from deck)
    container.querySelectorAll('.copy-move-to-binder').forEach(sel => {
      sel.addEventListener('change', async () => {
        if (!sel.value) return;
        let binderId = sel.value;
        if (binderId === '__new__') {
          const name = prompt('New binder name:');
          if (!name) { sel.value = ''; return; }
          const cr = await fetch('/api/binders', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
          const created = await cr.json();
          if (created.error) { alert(created.error); sel.value = ''; return; }
          binderId = created.id;
          await loadContainerData();
        }
        const r = await fetch(`/api/binders/${binderId}/cards/move`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ collection_ids: [parseInt(sel.dataset.copyId)] }),
        });
        const result = await r.json();
        if (result.error) { alert(result.error); sel.value = ''; return; }
        refreshAfterAction();
      });
    });

    // History toggle
    container.querySelectorAll('.history-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const copyId = btn.dataset.copyId;
        const histContainer = document.getElementById(`history-${copyId}`);
        if (histContainer.innerHTML) {
          histContainer.innerHTML = '';
          btn.innerHTML = 'History &#x25BE;';
          return;
        }
        btn.innerHTML = 'History &#x25B4;';
        loadHistory(copyId, histContainer);
      });
    });
  }

  // --- History timeline ---
  async function loadHistory(copyId, container) {
    container.innerHTML = '<div style="color:#888;font-size:0.8rem;padding:4px 0;">Loading...</div>';
    try {
      const res = await fetch(`/api/collection/${copyId}/history`);
      const data = await res.json();
      const events = data.combined || [];
      if (!events.length) {
        container.innerHTML = '<div style="color:#666;font-size:0.8rem;padding:4px 0;">No history</div>';
        return;
      }
      container.innerHTML = `<div class="history-timeline">${events.map(ev => {
        const date = ev.changed_at ? new Date(ev.changed_at).toLocaleDateString() : '';
        if (ev.type === 'status') {
          const from = ev.from_status || '?';
          const to = ev.to_status || '?';
          const note = ev.note ? ` — ${esc(ev.note)}` : '';
          return `<div class="history-event status">
            <span class="history-date">${date}</span>
            <span class="history-desc">${esc(from)} &rarr; ${esc(to)}${note}</span>
          </div>`;
        } else {
          // movement
          let desc = '';
          if (ev.to_deck_name) {
            desc = `Added to deck: ${esc(ev.to_deck_name)}`;
            if (ev.to_zone) desc += ` (${esc(ev.to_zone)})`;
          } else if (ev.to_binder_name) {
            desc = `Added to binder: ${esc(ev.to_binder_name)}`;
          } else if (ev.from_deck_name && !ev.to_deck_name && !ev.to_binder_name) {
            desc = `Removed from deck: ${esc(ev.from_deck_name)}`;
          } else if (ev.from_binder_name && !ev.to_deck_name && !ev.to_binder_name) {
            desc = `Removed from binder: ${esc(ev.from_binder_name)}`;
          } else if (ev.from_deck_name && ev.to_binder_name) {
            desc = `Moved from deck ${esc(ev.from_deck_name)} to binder ${esc(ev.to_binder_name)}`;
          } else if (ev.from_binder_name && ev.to_deck_name) {
            desc = `Moved from binder ${esc(ev.from_binder_name)} to deck ${esc(ev.to_deck_name)}`;
          } else {
            desc = ev.note || 'Movement';
          }
          const note = ev.note && !desc.includes(ev.note) ? ` — ${esc(ev.note)}` : '';
          return `<div class="history-event movement">
            <span class="history-date">${date}</span>
            <span class="history-desc">${desc}${note}</span>
          </div>`;
        }
      }).join('')}</div>`;
    } catch {
      container.innerHTML = '<div style="color:#e87e7e;font-size:0.8rem;padding:4px 0;">Failed to load history</div>';
    }
  }

  // --- Price chart ---
  const PRICE_SERIES_COLORS = {
    tcgplayer_normal: '#e94560', cardkingdom_buylist_normal: '#7ec8e3',
    tcgplayer_foil: '#a83248', cardkingdom_buylist_foil: '#5a9bb5',
  };
  const PRICE_SERIES_LABELS = {
    tcgplayer_normal: 'TCG Normal', cardkingdom_buylist_normal: 'CK Buy Normal',
    tcgplayer_foil: 'TCG Foil', cardkingdom_buylist_foil: 'CK Buy Foil',
  };

  const crosshairPlugin = {
    id: 'crosshair',
    afterDraw(chart) {
      if (chart.tooltip?._active?.length) {
        const x = chart.tooltip._active[0].element.x;
        const { top, bottom } = chart.chartArea;
        const ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.stroke();
        ctx.restore();
      }
    }
  };

  const purchaseLinesPlugin = {
    id: 'purchaseLines',
    afterDraw(chart) {
      const prices = chart.options.plugins.purchaseLines?.prices;
      if (!prices?.length) return;
      const { left, right } = chart.chartArea;
      const yScale = chart.scales.y;
      const ctx = chart.ctx;
      ctx.save();
      for (const price of prices) {
        const y = yScale.getPixelForValue(price);
        if (y < chart.chartArea.top || y > chart.chartArea.bottom) continue;
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(126,232,176,0.5)';
        ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(126,232,176,0.7)';
        ctx.font = '9px sans-serif';
        ctx.fillText('$' + price.toFixed(2), left + 3, y - 3);
      }
      ctx.restore();
    }
  };

  let _priceChart = null;

  async function renderPriceChart() {
    const section = document.getElementById('price-chart-section');
    if (!section) return;
    section.classList.remove('visible');

    let data;
    try {
      const res = await fetch(`/api/price-history/${encodeURIComponent(card.set_code)}/${encodeURIComponent(card.collector_number)}`);
      data = await res.json();
    } catch { return; }

    const seriesKeys = Object.keys(data).filter(k => data[k].length > 0);
    if (!seriesKeys.length) return;

    section.classList.add('visible');

    // Purchase prices for reference lines
    let purchasePrices = [];
    try {
      const copiesRes = await fetch(`/api/collection/copies?printing_id=${encodeURIComponent(card.printing_id)}`);
      const copies = await copiesRes.json();
      const seen = new Set();
      for (const c of copies) {
        if (c.purchase_price != null) {
          const p = parseFloat(c.purchase_price);
          if (p > 0 && !seen.has(p)) { seen.add(p); purchasePrices.push(p); }
        }
      }
    } catch {}

    let earliest = Infinity;
    for (const k of seriesKeys) {
      const t = new Date(data[k][0].date).getTime();
      if (t < earliest) earliest = t;
    }
    const spanDays = (Date.now() - earliest) / 86400000;

    const pills = section.querySelectorAll('.price-range-pill');
    const ranges = [30, 90, 180, 365, 0];
    pills.forEach((pill, i) => {
      pill.classList.toggle('disabled', ranges[i] > 0 && spanDays < ranges[i]);
    });

    let activeRange = 0;
    for (const pill of pills) {
      if (!pill.classList.contains('disabled')) {
        activeRange = parseInt(pill.dataset.range);
        break;
      }
    }
    pills.forEach(p => p.classList.toggle('active', parseInt(p.dataset.range) === activeRange));

    function filterData(rangeDays) {
      const cutoff = rangeDays > 0 ? Date.now() - rangeDays * 86400000 : 0;
      return seriesKeys.map(k => ({
        key: k,
        points: data[k].filter(p => new Date(p.date).getTime() >= cutoff),
      })).filter(s => s.points.length > 0);
    }

    function buildDatasets(filtered) {
      return filtered.map(s => ({
        label: PRICE_SERIES_LABELS[s.key] || s.key,
        data: s.points.map(p => ({ x: p.date, y: p.price })),
        borderColor: PRICE_SERIES_COLORS[s.key] || '#888',
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.25,
      }));
    }

    const canvas = document.getElementById('price-chart-canvas');
    const filtered = filterData(activeRange);
    _priceChart = new Chart(canvas, {
      type: 'line',
      data: { datasets: buildDatasets(filtered) },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            type: 'time',
            time: { tooltipFormat: 'MMM d, yyyy' },
            ticks: { color: '#666', maxTicksLimit: 5, font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.06)' },
          },
          y: {
            ticks: {
              color: '#666', font: { size: 10 },
              callback: v => '$' + v.toFixed(2),
            },
            grid: { color: 'rgba(255,255,255,0.06)' },
          },
        },
        plugins: {
          legend: { position: 'top', labels: { color: '#888', font: { size: 10 }, boxWidth: 12 } },
          tooltip: {
            callbacks: { label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}` },
          },
          purchaseLines: { prices: purchasePrices },
        },
      },
      plugins: [crosshairPlugin, purchaseLinesPlugin],
    });

    pills.forEach(pill => {
      pill.addEventListener('click', () => {
        if (pill.classList.contains('disabled')) return;
        pills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const range = parseInt(pill.dataset.range);
        const filtered = filterData(range);
        _priceChart.data.datasets = buildDatasets(filtered);
        _priceChart.update();
      });
    });
  }

})();
