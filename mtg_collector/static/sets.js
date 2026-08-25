/* sets.js — the /sets index: every locally cached set, grouped by set_type,
   with a jump rail down the left and each group collapsible — or flat and
   ordered by completion when the sort select says so.
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
  wireControls(sets);
}

/* The sort select switches between two full renderers over the same payload —
   grouped-by-type (with its rail) and flat-by-completion (with none) — rather
   than reordering the DOM in place. Each renderer builds its own filter pass
   over its own tiles and returns it; `apply` is reassigned here rather than
   inside either renderer, so the filter input's own listener is attached once
   and always drives whichever render is current, instead of a fresh listener
   stacking on every sort change. */
function wireControls(sets) {
  const input = document.getElementById('set-filter');
  const select = document.getElementById('sets-sort');
  let apply = () => {};

  function render() {
    apply = select.value === 'completion' ? renderCompletionMode(sets) : renderGroupedMode(sets);
    apply();
  }

  input.addEventListener('input', () => apply());
  select.addEventListener('change', render);
  render();
}

function renderGroupedMode(sets) {
  const body = document.getElementById('sets-body');
  const rail = document.getElementById('sets-rail');
  const groups = groupByType(sets);
  body.innerHTML = groups.map(renderGroup).join('')
    + '<div class="empty-state" id="sets-no-match" hidden>No set matches that filter.</div>';
  rail.innerHTML = renderRail(groups);
  return wireGroups(groups);
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

/* How many of the ranked types start expanded: Expansion, Core, Commander,
   Masters — 211 sets of the ~995 at prod scale.

   Deliberately *not* pokedumpster's collapse-unless-owned rule. Ownership
   here is spread differently: that rule would expand Token (203) and Promo
   (275) as well, so over half the catalogue would default-expand and the
   collapse would have bought nothing. A rank cutoff also follows the rank —
   reorder SET_TYPE_RANK and the default follows without a second list to
   keep in step. */
const DEFAULT_OPEN_RANKS = 4;

function setTypeRank(setType) {
  const i = SET_TYPE_RANK.indexOf(setType);
  return i === -1 ? SET_TYPE_RANK.length : i;
}

/* Groups come out in SET_TYPE_RANK order; within a group the response's
   newest-first order is kept. Array sort is stable, so the types that share a
   rank — every one the list has never heard of — keep first appearance, which
   is still newest-first.

   The rail and the sections are both built from this one array, so a rail row
   can never name a section that is not there, and their counts cannot drift. */
function groupByType(sets) {
  const byType = new Map();
  for (const s of sets) {
    const key = s.set_type || '';
    if (!byType.has(key)) byType.set(key, []);
    byType.get(key).push(s);
  }
  return Array.from(byType)
    .sort((a, b) => setTypeRank(a[0]) - setTypeRank(b[0]))
    .map(([setType, rows]) => ({
      setType,
      label: setTypeLabel(setType),
      // Scryfall set types are snake_case, but this is an id and an attribute
      // selector, so anything that is not is dropped rather than trusted.
      id: `set-group-${setType.replace(/[^a-z0-9_]/gi, '') || 'other'}`,
      rows,
      // Which sets in the group have a card in hand. Rendered as the group's
      // roll-up and recounted while filtering, so the header always describes
      // what is on screen — the same rule .group-count already followed.
      owned: rows.map(s => s.owned_all > 0),
      defaultOpen: setTypeRank(setType) < DEFAULT_OPEN_RANKS,
    }));
}

/* The header is the collapse control, so it takes the button role rather than
   holding a nested <button> — an h2 is what the group order test and the page
   outline both read. The caret is a ::before on the header (see sets.css), not
   a span, so the heading's text still starts with the type's label. */
function renderGroup(g) {
  const ownedCount = g.owned.filter(Boolean).length;
  return `<section class="set-group${g.defaultOpen ? ' open' : ''}" id="${g.id}" data-set-type="${esc(g.setType)}">`
    + `<h2 class="set-group-header" role="button" tabindex="0" aria-expanded="${g.defaultOpen}" aria-controls="${g.id}-grid">`
    + `<span class="group-label">${esc(g.label)}</span>`
    + `<span class="group-count">${g.rows.length}</span>`
    + `<span class="group-owned" title="Sets in this group with at least one card owned">${ownedCount} owned</span>`
    + '</h2>'
    + `<div class="set-grid" id="${g.id}-grid">${g.rows.map(renderTile).join('')}</div>`
    + '</section>';
}

/* One row per group that actually rendered, in the same order — at prod scale
   that is all 24 ranked types, and a type Scryfall adds later gets a row at the
   end for free. A row for a type with no cached sets would jump nowhere, so
   there is none.

   No ownership dot on a row, unlike pokedumpster's: ownership there
   concentrates in a few eras, so a lit row says something. Here 13 of 24 MTG
   types hold something, and 13 of 24 rows lighting up is noise. */
function renderRail(groups) {
  return '<h2 class="rail-title">Set types</h2><ul class="rail-list">'
    + groups.map(g => '<li>'
      + `<button type="button" class="rail-row" data-set-type="${esc(g.setType)}">`
      + `<span class="rail-label">${esc(g.label)}</span>`
      + `<span class="rail-count">${g.rows.length}</span>`
      + '</button></li>').join('')
    + '</ul>';
}

/* Completion mode answers the one question the set_type grouping cannot:
   which sets am I close to finishing. Those sets are spread across every type,
   so the grouping is exactly what hides the answer — this mode dissolves it
   into one flat grid ordered by how full the set is. It has no rail: nothing
   to jump between, so the rail is cleared while it is active rather than left
   showing stale rows for a grouping that is not on screen.

   Only sets with something owned are in it. A set at 0 / 291 is not a set you
   are close to finishing, and at prod scale there are 860 of those against 133
   with a card in them — keeping them would bury the answer under a page of
   empty tiles that are all tied for last. `owned_all > 0` is also what makes
   the division safe: a set cannot own a printing it does not have, so
   `total_all` is at least 1 for every row that survives the filter.

   The heading stays, and it is not a group — it says which population the grid
   is showing, so 860 sets going missing reads as the point of the mode rather
   than as a bug. */
function renderCompletionMode(sets) {
  const body = document.getElementById('sets-body');
  const rail = document.getElementById('sets-rail');
  rail.innerHTML = '';

  const owned = sets.filter(s => s.owned_all > 0);
  if (!owned.length) {
    body.innerHTML = '<div class="empty-state">Nothing is owned from any cached set yet.</div>'
      + '<div class="empty-state" id="sets-no-match" hidden>No set matches that filter.</div>';
    document.getElementById('sets-count').textContent = '0 sets';
    return () => {};
  }
  // Array sort is stable, so sets tied on percentage — 1 / 1 and 100 / 100 are
  // both 100% — keep the response's newest-first order among themselves.
  owned.sort((a, b) => b.owned_all / b.total_all - a.owned_all / a.total_all);

  body.innerHTML = '<section class="set-group" data-sort="completion">'
    + `<h2>Owned sets<span class="group-count">${owned.length}</span></h2>`
    + `<div class="set-grid">${owned.map(renderTile).join('')}</div>`
    + '</section>'
    + '<div class="empty-state" id="sets-no-match" hidden>No set matches that filter.</div>';
  return wireFlatFilter(owned);
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

/* Collapse is a class on the section, so the grid goes to `display:none` and
   every tile stays in the DOM. That is load-bearing for the filter below: it
   still sees, hides and counts the tiles inside a collapsed group, and a
   filter that matches in there opens it rather than reporting a count against
   a blank page. */
function setOpen(g, open) {
  g.el.classList.toggle('open', open);
  g.header.setAttribute('aria-expanded', String(open));
}

/* Wires the grouped-mode DOM and returns the filter pass for it. Does not
   touch the filter input itself — `wireControls` owns that listener across
   both render modes, so it is not attached (and re-attached) here. */
function wireGroups(groups) {
  const count = document.getElementById('sets-count');
  const noMatch = document.getElementById('sets-no-match');
  const rail = document.getElementById('sets-rail');

  for (const g of groups) {
    g.el = document.getElementById(g.id);
    g.header = g.el.querySelector('.set-group-header');
    g.countEl = g.el.querySelector('.group-count');
    g.ownedEl = g.el.querySelector('.group-owned');
    g.railRow = rail.querySelector(`.rail-row[data-set-type="${CSS.escape(g.setType)}"]`);
    g.railCountEl = g.railRow.querySelector('.rail-count');
    // The tiles of *this* group only, paired with this group's own rows by
    // position. The predecessor of this code walked every tile on the page
    // against one running index into a flat array, which held only while every
    // group contributed all of its tiles in document order — an assumption a
    // collapsed or removed section breaks silently, mismatching every tile
    // after it. Per-group there is nothing to drift against.
    g.tiles = Array.from(g.el.querySelectorAll('.set-tile'));
    // Lowercased once here rather than on every keystroke. Code as well as
    // name: a set is as often reached for by `fin` as by `Final Fantasy`.
    g.haystacks = g.rows.map(s => `${s.set_name || ''} ${s.set_code || ''}`.toLowerCase());
    // What the user last chose; the filter overrides it while it is active and
    // hands the group back to it when the filter clears.
    g.userOpen = g.defaultOpen;

    g.header.addEventListener('click', () => toggle(g));
    g.header.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle(g);
      }
    });
    g.railRow.addEventListener('click', () => jumpTo(g));
  }

  const total = groups.reduce((n, g) => n + g.rows.length, 0);

  function toggle(g) {
    g.userOpen = !g.el.classList.contains('open');
    setOpen(g, g.userOpen);
  }

  function jumpTo(g) {
    // Nothing to jump to when the filter emptied the group; the rail row is
    // already dimmed to say so.
    if (g.el.hidden) return;
    g.userOpen = true;
    setOpen(g, true);
    g.el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function apply() {
    const input = document.getElementById('set-filter');
    const needle = input.value.trim().toLowerCase();
    let shown = 0;
    for (const g of groups) {
      let visible = 0;
      let ownedVisible = 0;
      for (let i = 0; i < g.tiles.length; i++) {
        const hit = !needle || g.haystacks[i].includes(needle);
        g.tiles[i].hidden = !hit;
        if (hit) {
          visible++;
          if (g.owned[i]) ownedVisible++;
        }
      }
      // A group that lost every set goes away rather than standing empty.
      g.el.hidden = visible === 0;
      g.countEl.textContent = visible;
      g.ownedEl.textContent = `${ownedVisible} owned`;
      g.railCountEl.textContent = visible;
      g.railRow.classList.toggle('is-empty', visible === 0);
      // A match inside a collapsed group has to open it — otherwise the count
      // reads "2 of 18 sets" over a page showing neither of them.
      setOpen(g, needle ? visible > 0 : g.userOpen);
      shown += visible;
    }
    noMatch.hidden = shown > 0;
    count.textContent = needle ? `${shown} of ${total} sets` : `${total} sets`;
  }

  return apply;
}

/* Wires completion mode's single flat section and returns its filter pass.
   One section, one pass, no collapse and no rail to keep in sync — the thing
   `wireGroups` does that this does not need. */
function wireFlatFilter(ordered) {
  const count = document.getElementById('sets-count');
  const noMatch = document.getElementById('sets-no-match');
  const groupEl = document.querySelector('.set-group[data-sort="completion"]');
  const countEl = groupEl.querySelector('.group-count');
  const tiles = Array.from(groupEl.querySelectorAll('.set-tile'));
  // Lowercased once here rather than on every keystroke. Code as well as name:
  // a set is as often reached for by `fin` as by `Final Fantasy`.
  const haystacks = ordered.map(s => `${s.set_name || ''} ${s.set_code || ''}`.toLowerCase());
  const total = ordered.length;

  return function apply() {
    const input = document.getElementById('set-filter');
    const needle = input.value.trim().toLowerCase();
    let shown = 0;
    for (let i = 0; i < tiles.length; i++) {
      const hit = !needle || haystacks[i].includes(needle);
      tiles[i].hidden = !hit;
      if (hit) shown++;
    }
    groupEl.hidden = shown === 0;
    countEl.textContent = shown;
    noMatch.hidden = shown > 0;
    count.textContent = needle ? `${shown} of ${total} sets` : `${total} sets`;
  };
}

loadSets();
