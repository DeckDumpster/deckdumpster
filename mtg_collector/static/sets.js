/* sets.js — the /sets index: every locally cached set, grouped by set_type.
   Depends on globals from shared.js (esc) and shared-card-table.js
   (keyruneSetCode, which carries the KEYRUNE_FALLBACKS map). */

/* GET /api/sets/index is unpaginated and already ordered newest-first, so the
   whole index arrives in one request and the filter below never touches the
   server — 993 sets at prod scale is small enough to filter in the browser. */
async function loadSets() {
  const body = document.getElementById('sets-body');
  const res = await fetch('/api/sets/index');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    body.innerHTML = `<div class="empty-state">${esc(err.error || `Could not load sets (HTTP ${res.status})`)}</div>`;
    return;
  }
  const sets = await res.json();
  if (!sets.length) {
    body.innerHTML = '<div class="empty-state">No sets are cached yet — run: mtg cache all</div>';
    document.getElementById('sets-count').textContent = '0 sets';
    return;
  }
  // Filled in document order by renderGroups, so tile N describes ordered[N].
  const ordered = [];
  body.innerHTML = renderGroups(sets, ordered)
    + '<div class="empty-state" id="sets-no-match" hidden>No set matches that filter.</div>';
  wireFilter(ordered);
}

/* `expansion` → `Expansion`, `draft_innovation` → `Draft Innovation`. The set
   types come straight from Scryfall and there are dozens of them; a hand-kept
   label map would go stale the next time one is added. */
function setTypeLabel(setType) {
  if (!setType) return 'Other';
  return setType.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

/* The order the groups are shown in. Which set_type leads used to be whichever
   one owned the single most recently released cached set, and that is not a
   judgement about what a collector opens this page for: msc and msh shared a
   release date and the set_code tiebreak put Commander ahead of Expansion,
   then importing the Hobbit sets reshuffled it again. The order is decided
   here instead.

   Scryfall adds set types over time, so a type this list has never heard of
   sorts to the end rather than dropping out or throwing — the list needs
   maintenance to stay optimal, never to stay correct. */
const SET_TYPE_RANK = [
  'expansion', 'core', 'commander', 'masters', 'draft_innovation', 'masterpiece',
  'eternal', 'alchemy', 'box', 'duel_deck', 'from_the_vault', 'planechase',
  'archenemy', 'spellbook', 'premium_deck', 'arsenal', 'starter', 'funny',
  'vanguard', 'treasure_chest', 'minigame', 'memorabilia', 'token', 'promo',
];

function setTypeRank(setType) {
  const i = SET_TYPE_RANK.indexOf(setType);
  return i === -1 ? SET_TYPE_RANK.length : i;
}

/* Groups render in SET_TYPE_RANK order; within a group the response's
   newest-first order is kept. Array sort is stable, so the types that share a
   rank — every one the list has never heard of — keep first appearance, which
   is still newest-first. */
function renderGroups(sets, ordered) {
  const groups = new Map();
  for (const s of sets) {
    const key = s.set_type || '';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  let html = '';
  const ranked = Array.from(groups).sort((a, b) => setTypeRank(a[0]) - setTypeRank(b[0]));
  for (const [setType, rows] of ranked) {
    ordered.push(...rows);
    html += `<section class="set-group" data-set-type="${esc(setType)}">`
      + `<h2>${esc(setTypeLabel(setType))}<span class="group-count">${rows.length}</span></h2>`
      + `<div class="set-grid">${rows.map(renderTile).join('')}</div>`
      + '</section>';
  }
  return html;
}

function renderTile(s) {
  const code = (s.set_code || '').toUpperCase();
  const released = s.released_at || 'unreleased';
  return `<a class="set-tile" href="/sets/${encodeURIComponent(s.set_code)}">`
    + `<i class="ss ss-${esc(keyruneSetCode(s.set_code))} ss-2x set-symbol"></i>`
    + `<span class="set-name">${esc(s.set_name || code)}</span>`
    + `<span class="set-sub">${esc(code)} · ${esc(released)}</span>`
    + '<div class="set-meters">'
    + renderMeter('Set', s.owned_base, s.total_base)
    + renderMeter('All', s.owned_all, s.total_all)
    + '</div></a>';
}

/* A meter is a fraction, so it renders only when there is something to be a
   fraction of. `total_base` is null exactly when `base_set_size` is — a
   permanent, legitimate state for a set no source reports a boundary for — and
   `null > 0` is false, so those sets show the All meter alone instead of a
   0 / 0 bar reading NaN%. */
function renderMeter(label, owned, total) {
  if (!(total > 0)) return '';
  const pct = Math.round((owned / total) * 100);
  const complete = owned >= total ? ' complete' : '';
  return '<div class="set-meter">'
    + `<span class="set-meter-label">${esc(label)}</span>`
    + `<span class="set-meter-bar"><span class="set-meter-fill${complete}" style="width:${pct}%"></span></span>`
    + `<span class="set-meter-count">${owned} / ${total}</span>`
    + '</div>';
}

function wireFilter(ordered) {
  const input = document.getElementById('set-filter');
  const count = document.getElementById('sets-count');
  const noMatch = document.getElementById('sets-no-match');
  // Group-major and in document order, which is the order renderGroups pushed
  // into `ordered` — so one running index reads off each tile's set, and a
  // keystroke costs one pass over the tiles rather than a re-query per group.
  const groups = Array.from(document.querySelectorAll('.set-group')).map(el => ({
    el,
    countEl: el.querySelector('.group-count'),
    tiles: Array.from(el.querySelectorAll('.set-tile')),
  }));
  // Lowercased once here rather than on every keystroke. Code as well as name:
  // a set is as often reached for by `fin` as by `Final Fantasy`.
  const haystacks = ordered.map(s => `${s.set_name || ''} ${s.set_code || ''}`.toLowerCase());
  const total = ordered.length;

  function apply() {
    const needle = input.value.trim().toLowerCase();
    let shown = 0;
    let i = 0;
    for (const group of groups) {
      let visible = 0;
      for (const tile of group.tiles) {
        const hit = !needle || haystacks[i++].includes(needle);
        tile.hidden = !hit;
        if (hit) visible++;
      }
      // A group that lost every set goes away rather than standing empty.
      group.el.hidden = visible === 0;
      group.countEl.textContent = visible;
      shown += visible;
    }
    noMatch.hidden = shown > 0;
    count.textContent = needle ? `${shown} of ${total} sets` : `${total} sets`;
  }

  input.addEventListener('input', apply);
  apply();
}

loadSets();
