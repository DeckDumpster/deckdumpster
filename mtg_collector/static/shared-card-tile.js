/* shared-card-tile.js — Pure rendering functions for the card TILE.
   Depends on globals from shared.js: formatPrice, esc, parseJsonField.
   Paired with shared-card-tile.css. No DOM queries, no page state.

   Not to be confused with shared-card-table.js, which renders table CELLS.

   Extracted from explore_sheets.html, the visual contract named by TODO.md 7.5
   ("card display should be the same as the Sheet interface"). */

/* Cards from another set than the one being browsed get a purple outer edge,
   so a reprint or a bonus-sheet card is obvious at a glance. */
function getSetColor(cardSetCode, packSetCode) {
  if (!packSetCode) return '#111';
  return (cardSetCode || '').toUpperCase() !== packSetCode.toUpperCase() ? '#5c2d91' : '#111';
}

/* promo_types values that describe HOW a card is foiled. This is the third
   axis: independent of whether the card IS foil (the .foil wash) and of which
   finish a copy is (the .foil-tag label). */
const FOIL_KIND_LABELS = {
  surgefoil: 'Surge',
  galaxyfoil: 'Galaxy',
  ripplefoil: 'Ripple',
  halofoil: 'Halo',
  confettifoil: 'Confetti',
  textured: 'Textured',
  rainbowfoil: 'Rainbow',
  doublerainbow: 'DblRnbw',
  stepandcompleat: 'Compleat',
  oilslick: 'OilSlick',
  gilded: 'Gilded',
  neonink: 'NeonInk',
};

function foilKindLabel(kind) {
  return FOIL_KIND_LABELS[kind] || kind;
}

/**
 * Render the tile's badge row.
 *
 * Every badge is driven by the data present on the card, not by a flag, so a
 * caller whose rows lack a field simply gets no badge for it: sheets rows carry
 * pull_rate and get a pull-rate badge, binder rows carry foil_kinds and get a
 * foil-kind badge, and neither has to say so.
 *
 * priceSources is the raw `price_sources` setting ("tcg,ck").
 */
function buildCardTileBadges(card, priceSources) {
  const sources = (priceSources || 'tcg,ck').split(',');
  let html = '';

  if (card.pull_rate != null) {
    html += `<span class="badge pull-rate">${(card.pull_rate * 100).toFixed(2)}%</span>`;
  }
  if (sources.includes('tcg') && card.printing_id) {
    const sfUrl = `https://scryfall.com/card/${(card.set_code || '').toLowerCase()}/${card.collector_number}`;
    const tcgPrice = card.tcg_price ? ` ${formatPrice(card.tcg_price)}` : '';
    html += `<a class="badge link" href="${sfUrl}" target="_blank" rel="noopener">SF${tcgPrice}</a>`;
  }
  if (sources.includes('ck') && card.ck_url) {
    const ckPrice = card.ck_price ? ` ${formatPrice(card.ck_price)}` : '';
    html += `<a class="badge link" href="${card.ck_url}" target="_blank" rel="noopener">CK${ckPrice}</a>`;
  }

  // frame_effects arrives as an array from /api/sheets and as a JSON string
  // from the collection endpoints; parseJsonField takes either.
  const fe = parseJsonField(card.frame_effects);
  if (card.border_color === 'borderless') html += '<span class="badge treatment">BL</span>';
  if (fe.includes('showcase')) html += '<span class="badge treatment">SC</span>';
  if (fe.includes('extendedart')) html += '<span class="badge treatment">EA</span>';
  if (card.is_full_art || card.full_art) html += '<span class="badge treatment">FA</span>';

  for (const kind of parseJsonField(card.foil_kinds)) {
    html += `<span class="badge foil-kind">${esc(foilKindLabel(kind))}</span>`;
  }
  return html;
}

/**
 * Render the finish pip row: one pip per entry in `finishes`, filled when that
 * finish is owned, showing the count when more than one is held.
 *
 * The pips are the binder's one-click add target, so each is a real <button>
 * carrying its finish in a data attribute; binding the click is the caller's job.
 */
function buildFinishPips(card) {
  const finishes = parseJsonField(card.finishes);
  if (!finishes.length) return '';
  const owned = {};
  for (const o of (card.owned || [])) owned[o.finish] = o.qty;

  let html = '<div class="pip-row">';
  for (const finish of finishes) {
    const qty = owned[finish] || 0;
    const label = qty > 1 ? `${finish.slice(0, 4)} ${qty}` : finish.slice(0, 4);
    const cls = qty > 0 ? 'finish-pip filled' : 'finish-pip';
    const color = qty > 0 ? ` style="--pip-color:${getRarityColor(card.rarity)}"` : '';
    html += `<button type="button" class="${cls}" data-finish="${esc(finish)}"${color}>${esc(label)}</button>`;
  }
  return html + '</div>';
}

/**
 * Build one card tile.
 *
 *   buildCardTile(card, opts) -> HTML string
 *
 * opts:
 *   showQty      — quantity pill when qty > 1
 *   showBadges   — the badge row under the art
 *   showPips     — the per-finish pip row (binder's one-click add)
 *   selectable   — a selection checkbox over the art
 *   lazy         — loading="lazy" on the image (default true)
 *   packSetCode  — set being browsed; off-set cards get the purple outer edge
 *   priceSources — the `price_sources` setting, for the SF/CK link badges
 *   selected     — pre-check the selection checkbox
 *   attrs        — extra attributes on the outer element (e.g. data-idx)
 *
 * Ownership state comes from the card, not from opts: `owned === false` dims the
 * tile, a wishlist hit softens that dim, and `status === 'ordered'` marks it.
 */
function buildCardTile(card, opts) {
  opts = opts || {};
  const isUnowned = card.owned === false;
  const isWanted = isUnowned && (card.wishlist_id != null || card.wanted === true);
  const isOrdered = card.status === 'ordered';

  const cls = 'sheet-card'
    + (isUnowned ? ' unowned' : '')
    + (isWanted ? ' wanted' : '')
    + (isOrdered ? ' ordered' : '');

  const rarityColor = getRarityColor(card.rarity);
  const setColor = getSetColor(card.set_code, opts.packSetCode);
  // A foil wash belongs on a card that is foil, never on a pocket you have not
  // filled — an unowned tile has no finish to be foil in.
  const isFoil = !isUnowned && (card.foil || card.finish === 'foil' || card.finish === 'etched');
  const foilClass = isFoil ? ' foil' : '';

  const qty = opts.showQty && !isUnowned && card.qty > 1
    ? `<span class="qty-badge">${card.qty}x</span>` : '';
  const wanted = isWanted ? '<span class="wanted-badge">Want</span>' : '';
  const ordered = isOrdered ? '<span class="ordered-badge" title="Ordered"></span>' : '';
  const checkbox = opts.selectable
    ? `<input type="checkbox" class="select-checkbox"${opts.selected ? ' checked' : ''}>` : '';

  const loading = opts.lazy === false ? '' : ' loading="lazy"';
  const badges = opts.showBadges
    ? `<div class="sheet-card-info">${buildCardTileBadges(card, opts.priceSources)}</div>` : '';
  const pips = opts.showPips ? buildFinishPips(card) : '';
  const attrs = opts.attrs ? ' ' + opts.attrs : '';

  return `<div class="${cls}"${attrs}>`
    + `<div class="sheet-card-img-wrap${foilClass}" style="--rarity-color:${rarityColor};--set-color:${setColor}">`
    + `<img src="${card.image_uri || ''}" alt="${esc(card.name)}"${loading}>`
    + `${qty}${wanted}${ordered}${checkbox}`
    + `</div>${badges}${pips}</div>`;
}
