/* shared-card-modal.js — Reusable card detail modal.
   Depends on: shared.js (esc, renderMana, parseJsonField, getCkUrl, DFC_LAYOUTS),
               shared-card-table.js (keyruneSetCode, getPrimaryType). */

/**
 * Create and mount the card modal DOM structure.
 * Returns an object with { overlay, imgFront, imgBack, flip, flipBtn, details, show, hide }.
 * Call once at page init, then use .show(card, opts) to display.
 */
function createCardModal() {
  const overlay = document.createElement('div');
  overlay.className = 'card-modal-overlay';
  overlay.innerHTML = `
    <div class="card-modal">
      <button class="card-modal-close">&times;</button>
      <div class="card-modal-img">
        <div class="card-flip-container">
          <div class="card-flip-front"><img src="" alt=""></div>
          <div class="card-flip-back"><img src="" alt=""></div>
        </div>
        <button class="flip-btn" title="Flip card">&#x21BB;</button>
      </div>
      <div class="card-modal-details"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  const imgFront = overlay.querySelector('.card-flip-front img');
  const imgBack = overlay.querySelector('.card-flip-back img');
  const flip = overlay.querySelector('.card-flip-container');
  const flipBtn = overlay.querySelector('.flip-btn');
  const details = overlay.querySelector('.card-modal-details');
  const closeBtn = overlay.querySelector('.card-modal-close');

  function hide() { overlay.classList.remove('active'); }

  overlay.addEventListener('click', (e) => { if (e.target === overlay) hide(); });
  closeBtn.addEventListener('click', hide);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.classList.contains('active')) hide();
  });

  /**
   * Show the card modal.
   * card: card data object (must have image_uri, name, layout, set_code, collector_number, etc.)
   * opts.renderExtra: optional (card) => HTML string appended after the links section
   */
  function show(card, opts) {
    opts = opts || {};

    // Front image
    imgFront.src = card.image_uri || '';
    imgFront.alt = card.name;

    // Back image — DFC gets real back face, others get card back
    const isDfc = DFC_LAYOUTS.includes(card.layout);
    const backSrc = isDfc ? (card.image_uri || '').replace('/front/', '/back/') : '/static/card_back.jpeg';
    imgBack.src = backSrc;
    imgBack.alt = isDfc ? 'Back face' : 'Card back';

    // Reset flip state
    flip.classList.remove('flipped');
    let showingBack = false;

    // Condition / finish labels
    const condition = card.condition || 'Near Mint';
    const finish = card.finish ? card.finish.charAt(0).toUpperCase() + card.finish.slice(1) : 'Nonfoil';

    // Prices
    const tcgPrice = card.tcg_price ? formatPrice(card.tcg_price) : '\u2014';
    const ckPrice = card.ck_price ? formatPrice(card.ck_price) : '\u2014';

    // Links
    const sfUrl = `https://scryfall.com/card/${card.set_code.toLowerCase()}/${card.collector_number}`;
    const ckUrl = getCkUrl(card);

    // Tags
    const fe = parseJsonField(card.frame_effects);
    let tagsHtml = '';
    if (card.finish === 'foil') tagsHtml += '<span class="foil-tag">Foil</span>';
    if (card.finish === 'etched') tagsHtml += '<span class="foil-tag">Etched</span>';
    if (card.border_color === 'borderless') tagsHtml += '<span class="treat-tag">Borderless</span>';
    if (fe.includes('showcase')) tagsHtml += '<span class="treat-tag">Showcase</span>';
    if (fe.includes('extendedart')) tagsHtml += '<span class="treat-tag">Extended Art</span>';
    if (card.full_art) tagsHtml += '<span class="treat-tag">Full Art</span>';
    if (fe.includes('inverted')) tagsHtml += '<span class="treat-tag">Inverted</span>';
    if (card.promo) tagsHtml += '<span class="promo-tag">Promo</span>';

    // Set info
    const setCode = keyruneSetCode(card.set_code);
    const rarityClass = `ss-${card.rarity || 'common'}`;
    const setIcon = `<i class="ss ss-${setCode} ${rarityClass} ss-grad"></i>`;
    const setName = card.set_name || card.set_code.toUpperCase();
    const rarity = card.rarity ? card.rarity.charAt(0).toUpperCase() + card.rarity.slice(1) : '';

    // DFC face splitting
    const names = card.name.split(' // ');
    const types = (card.type_line || '').split(' // ');
    const manas = (card.mana_cost || '').split(' // ');
    const isArtSeries = card.layout === 'art_series';

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

      const faceMainType = faceType.split(' \u2014 ')[0] || '';
      const facePrimary = getPrimaryType(faceMainType);
      const typeValueHtml = facePrimary ? faceType : faceType;

      const extraHtml = opts.renderExtra ? opts.renderExtra(card) : '';

      details.innerHTML = `
        <h2>${esc(faceName)}</h2>
        ${manaHtml ? `<div class="modal-mana">${manaHtml}</div>` : ''}
        <div class="modal-section">
          <span class="modal-section-title">Type</span>
          <span class="value">${typeValueHtml}</span>
          ${cmcText !== '' ? `<div class="modal-row"><span class="label">Mana Value</span><span class="value">${cmcText}</span></div>` : ''}
        </div>
        <div class="modal-section">
          <span class="modal-section-title">Printing</span>
          <div class="modal-row"><span class="label">Set</span><span class="value">${setIcon} ${esc(setName)} (${card.set_code.toUpperCase()})</span></div>
          <div class="modal-row"><span class="label">Number</span><span class="value">${card.collector_number || ''}</span></div>
          <div class="modal-row"><span class="label">Rarity</span><span class="value">${rarity}</span></div>
        </div>
        <div class="modal-section">
          <span class="modal-section-title">Card Info</span>
          <div class="modal-row"><span class="label">Condition</span><span class="value">${condition}</span></div>
          <div class="modal-row"><span class="label">Finish</span><span class="value">${finish}</span></div>
        </div>
        ${tagsHtml ? `<div class="modal-section"><span class="modal-section-title">Treatments</span><div class="modal-tags">${tagsHtml}</div></div>` : ''}
        <div class="modal-links">
          <a class="badge link" href="${sfUrl}" target="_blank" rel="noopener">SF${tcgPrice !== '\u2014' ? ' ' + tcgPrice : ''}</a>
          <a class="badge link" href="${ckUrl}" target="_blank" rel="noopener">CK${ckPrice !== '\u2014' ? ' ' + ckPrice : ''}</a>
          <a class="badge link" href="/card/${card.set_code.toLowerCase()}/${card.collector_number}">Full page &rarr;</a>
        </div>
        ${extraHtml}
      `;
    }

    renderDetails(0);

    // Flip button handler
    flipBtn.onclick = () => {
      showingBack = !showingBack;
      flip.classList.toggle('flipped');
      if (isDfc) renderDetails(showingBack ? 1 : 0);
    };

    overlay.classList.add('active');
  }

  return { overlay, show, hide };
}
