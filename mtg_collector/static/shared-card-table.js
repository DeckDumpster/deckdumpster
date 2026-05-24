/* shared-card-table.js — Pure rendering functions for card table cells.
   Depends on globals from shared.js: esc, renderMana, parseJsonField, getCkUrl.
   No DOM queries, no page state. */

const KEYRUNE_FALLBACKS = {
  tsb: 'tsp',
  pspm: 'spm',
  cst: 'csp',   // Coldsnap Theme Decks → Coldsnap
};

function keyruneSetCode(code) {
  const lc = (code || '').toLowerCase();
  return KEYRUNE_FALLBACKS[lc] || lc;
}

const TYPE_KEYWORDS = ['Creature','Instant','Sorcery','Enchantment','Artifact','Planeswalker','Land','Battle','Kindred','Token'];

function getPrimaryType(mainType) {
  const words = mainType.split(/\s+/);
  for (let i = words.length - 1; i >= 0; i--) {
    if (TYPE_KEYWORDS.includes(words[i])) return words[i];
  }
  return null;
}

const CONDITION_ABBREV = {
  'Near Mint': 'NM', 'Lightly Played': 'LP', 'Moderately Played': 'MP',
  'Heavily Played': 'HP', 'Damaged': 'D',
};

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const m = d.getMonth() + 1, day = d.getDate();
  return `${m}/${day}`;
}

/**
 * Render treatment/finish/status badge HTML.
 * opts.isWanted: optional (card) => bool callback; omit for contexts without wishlist (decks).
 */
function buildInlineTags(card, opts) {
  opts = opts || {};
  let html = '';
  if (card.finish === 'foil') html += '<span class="card-tag foil-tag" title="Foil">F</span>';
  else if (card.finish === 'etched') html += '<span class="card-tag foil-tag" title="Etched foil">E</span>';
  const fe = parseJsonField(card.frame_effects);
  const isBorderless = card.border_color === 'borderless';
  if (isBorderless) html += '<span class="card-tag treat-tag" title="Borderless">BL</span>';
  if (fe.includes('showcase')) html += '<span class="card-tag treat-tag" title="Showcase frame">SC</span>';
  if (fe.includes('extendedart')) html += '<span class="card-tag treat-tag" title="Extended art">EA</span>';
  if (card.full_art && !isBorderless) html += '<span class="card-tag treat-tag" title="Full art">FA</span>';
  if (fe.includes('inverted')) html += '<span class="card-tag treat-tag" title="Inverted frame">IN</span>';
  if (card.promo) html += '<span class="card-tag promo-tag" title="Promo">P</span>';
  if (opts.isWanted && !card.owned && opts.isWanted(card)) html += '<span class="card-tag wanted-tag" title="Wanted">W</span>';
  if (card.status === 'ordered') html += '<span class="card-tag ordered-tag" title="Ordered">ORD</span>';
  return html;
}

/**
 * Render SF/CK price link badges.
 * opts.priceSources: comma-separated string, defaults to 'tcg,ck'.
 */
function buildPriceBadges(card, opts) {
  opts = opts || {};
  let html = '';
  const sources = (opts.priceSources || 'tcg,ck').split(',');
  if (sources.includes('tcg')) {
    const sfPrice = card.tcg_price ? ` ${formatPrice(card.tcg_price)}` : '';
    html += `<a class="badge link" href="https://scryfall.com/card/${card.set_code.toLowerCase()}/${card.collector_number}" target="_blank" rel="noopener" onclick="event.stopPropagation()">SF${sfPrice}</a>`;
  }
  if (sources.includes('ck')) {
    const ckPrice = card.ck_price ? ` ${formatPrice(card.ck_price)}` : '';
    html += `<a class="badge link" href="${getCkUrl(card)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">CK${ckPrice}</a>`;
  }
  return html;
}

/**
 * Consolidate card helper computation for table rendering.
 * opts.isWanted: passed through to buildInlineTags.
 * opts.showThumbnail: (default true) controls whether imgSrc is populated.
 * Returns { imgSrc, nameHtml, manaHtml, setCode, setName, setIcon, tags }.
 */
function prepareCardHelpers(card, opts) {
  opts = opts || {};
  const showThumbnail = opts.showThumbnail !== false;
  const imgFull = card.image_uri || '';
  const imgSrc = showThumbnail ? imgFull.replace('/normal/', '/small/') : '';
  const rawMana = card.mana_cost || '';
  const isArtSeries = card.layout === 'art_series';
  const isDfc = !isArtSeries && card.name.includes(' // ');
  let displayName = isArtSeries ? card.name.split(' // ')[0] : card.name;
  let nameHtml, manaHtml;
  if (isDfc) {
    const names = card.name.split(' // ');
    const manas = rawMana.split(' // ');
    nameHtml = names.map(n => `<span class="card-face"><span class="card-name">${n}</span></span>`).join('');
    manaHtml = manas.map(m => `<span class="mana-line">${renderMana(m)}</span>`).join('');
  } else {
    nameHtml = `<span class="card-name">${displayName}</span>`;
    manaHtml = renderMana(rawMana);
  }
  const setCode = keyruneSetCode(card.set_code);
  const rarityClass = `ss-${card.rarity || 'common'}`;
  const setName = card.set_name || card.set_code.toUpperCase();
  const setIcon = `<i class="ss ss-${setCode} ${rarityClass} ss-grad"></i>`;
  const tags = buildInlineTags(card, { isWanted: opts.isWanted });
  return { imgSrc, nameHtml, manaHtml, setCode, setName, setIcon, tags };
}

/**
 * Render cell content for a given column key.
 * opts.priceSources: passed through to buildPriceBadges.
 */
function renderCellContent(colKey, card, helpers, opts) {
  opts = opts || {};
  switch (colKey) {
    case 'qty': return card.owned ? `${card.qty}` : '\u2014';
    case 'name': return `<div class="card-cell">${helpers.imgSrc ? `<img class="card-thumb" src="${helpers.imgSrc}" loading="lazy">` : ''}<span>${helpers.nameHtml}${helpers.tags}</span></div>`;
    case 'type': {
      if (card.layout === 'art_series') return `<span class="type-cell" title="Art Series">Art Series</span>`;
      const full = card.type_line || '';
      const faces = full.split(' // ');
      return `<span class="type-cell" title="${full}">${faces.map(face => {
        const parts = face.split(' \u2014 ');
        const mainText = parts[0];
        const main = mainText.replace(/Legendary /g, 'Lgdry. ');
        const primaryType = getPrimaryType(mainText);
        const mainHtml = primaryType ? `<span data-filter-type="type" data-filter-value="${primaryType}">${main}</span>` : main;
        const sub = parts[1] || '';
        const subHtml = sub ? `<span class="type-sub">${sub.split(/\s+/).map(s => s ? `<span data-filter-type="subtype" data-filter-value="${s}">${s}</span>` : '').join(' ')}</span>` : '';
        return `<span class="card-face">${mainHtml}${subHtml}</span>`;
      }).join('')}</span>`;
    }
    case 'mana': return card.cmc != null ? `<span class="mana-cost" data-filter-type="cmc" data-filter-value="${card.cmc}">${helpers.manaHtml}</span>` : `<span class="mana-cost">${helpers.manaHtml}</span>`;
    case 'set': return `<div class="set-cell" title="${helpers.setName}"><span data-filter-type="rarity" data-filter-value="${card.rarity || 'common'}">${helpers.setIcon}</span> <span data-filter-type="set" data-filter-value="${card.set_code}">${card.set_code.toUpperCase()}</span></div>`;
    case 'collector_number': return (card.collector_number || '').padStart(4, '0');
    case 'price': return buildPriceBadges(card, { priceSources: opts.priceSources });
    case 'condition': return CONDITION_ABBREV[card.condition] || card.condition || '';
    case 'date_added': {
      const dateStr = formatDate(card.acquired_at);
      if (!dateStr) return '';
      const isoDate = card.acquired_at.slice(0, 10);
      return `<span data-filter-type="date_added" data-filter-value="${isoDate}">${dateStr}</span>`;
    }
    case 'ck_price': {
      const p = card.ck_price ? formatPrice(card.ck_price) : '';
      return p ? `<a class="badge link" href="${getCkUrl(card)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${p}</a>` : '';
    }
    case 'tcg_price': {
      const p = card.tcg_price ? formatPrice(card.tcg_price) : '';
      return p ? `<a class="badge link" href="https://scryfall.com/card/${card.set_code.toLowerCase()}/${card.collector_number}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${p}</a>` : '';
    }
    default: return '';
  }
}
