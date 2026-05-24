/* shared.js — Common utility functions for all pages.
   New pages should import this. Existing pages are untouched. */

/** Format a numeric value as USD with thousands separators (e.g. 3667.51 → "$3,667.51").
    Returns "$0.00" for null/undefined/NaN inputs. */
function formatPrice(value) {
  const n = parseFloat(value);
  if (!Number.isFinite(n)) return '$0.00';
  return '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

/** HTML-escape a string. */
function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/** Safely parse a JSON field (stored as TEXT in SQLite). Returns [] on failure. */
function parseJsonField(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val;
  try { return JSON.parse(val); } catch { return []; }
}

/** Convert mana cost string like {U}{B}{1} to mana-font icon HTML. */
function renderMana(cost) {
  if (!cost) return '';
  return cost.replace(/\{([^}]+)\}/g, (_, sym) => {
    const cls = sym.toLowerCase().replace(/\//g, '');
    return `<i class="ms ms-${cls} ms-cost ms-shadow"></i>`;
  });
}

/** Rarity → hex color map for border gradients. */
const RARITY_COLORS = {common: '#111', uncommon: '#6a6a6a', rare: '#c9a816', mythic: '#d4422a'};
function getRarityColor(rarity) { return RARITY_COLORS[rarity] || '#111'; }

/** Card layouts that support front/back images. */
const DFC_LAYOUTS = ['transform', 'modal_dfc', 'reversible_card', 'double_faced_token', 'art_series'];

/** Build a Card Kingdom URL for a card object. */
function getCkUrl(card) {
  if (card.ck_url) return card.ck_url;
  const ckSearch = encodeURIComponent(card.name.split(' // ')[0]);
  return `https://www.cardkingdom.com/catalog/search?search=header&filter%5Bname%5D=${ckSearch}`;
}
