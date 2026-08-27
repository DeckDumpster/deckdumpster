"""Crack-a-pack web server: mtg crack-pack-server --port 8080"""

import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, unquote, urlparse

from mtg_collector.cli.page_routes import PageRoute, match_page_route
from mtg_collector.db.connection import get_db_path
from mtg_collector.db.mtgjson_faces import front_face_bulk_sql, front_face_uuid_sql
from mtg_collector.http_cache import (
    CACHE_API,
    CACHE_DOCUMENT,
    CACHE_IMMUTABLE,
    RangeNotSatisfiable,
    compute_etag,
    etag_matches,
    negotiate_gzip,
    parse_range,
)
from mtg_collector.services.pack_generator import PackGenerator


def _get_sqlite_price(db_path: str, set_code: str, collector_number: str, source: str, price_type: str) -> str | None:
    """Look up a single price from the latest_prices view."""
    conn = sqlite3.connect(db_path)

    if _shared_db_path and os.path.exists(_shared_db_path):
        from mtg_collector.db.connection import attach_shared
        attach_shared(conn, _shared_db_path)
    row = conn.execute(
        "SELECT price FROM latest_prices WHERE set_code = ? AND collector_number = ? AND source = ? AND price_type = ?",
        (set_code.lower(), collector_number, source, price_type),
    ).fetchone()
    conn.close()
    return str(row[0]) if row else None


#: Distinct (set_code, collector_number) pairs looked up per price statement.
#: Each pair binds two parameters, so a statement holds at most 1,000 of them
#: however many cards were asked for -- the point of the constant, and the whole
#: point of the batching.  Statements sized by the caller's result set are the
#: defect de-ckq removed from /api/collection, where 112,809 rows built one
#: statement with 225,618 bound parameters against a SQLITE_MAX_VARIABLE_NUMBER
#: of 250,000.  The callers left here are nowhere near that -- the largest real
#: booster product measured 779 distinct cards -- so this is the pattern being
#: closed, not a live overflow being averted.
_PRICE_LOOKUP_BATCH = 500


def _bulk_attach_prices(conn, cards: list[dict]) -> None:
    """Batch-attach tcg_price and ck_price to a list of card dicts.

    Uses batched SQL queries instead of per-card connections.
    Each card dict must have set_code, collector_number, and foil (bool).
    """
    if not cards:
        return
    unique_pairs = list({(c.get("set_code", "").lower(), c.get("collector_number", "")) for c in cards})
    if not unique_pairs:
        return
    price_map: dict[tuple, str] = {}
    for start in range(0, len(unique_pairs), _PRICE_LOOKUP_BATCH):
        batch = unique_pairs[start:start + _PRICE_LOOKUP_BATCH]
        ph = ",".join("(?,?)" for _ in batch)
        params = [v for pair in batch for v in pair]
        for r in conn.execute(
            f"SELECT set_code, collector_number, source, price_type, price "
            f"FROM latest_prices WHERE (set_code, collector_number) IN ({ph})",
            params,
        ).fetchall():
            price_map[(r["set_code"], r["collector_number"], r["source"], r["price_type"])] = str(r["price"])
    for card in cards:
        sc = card.get("set_code", "").lower()
        cn = card.get("collector_number", "")
        pt = "foil" if card.get("foil") else "normal"
        card["tcg_price"] = price_map.get((sc, cn, "tcgplayer", pt))
        card["ck_price"] = price_map.get((sc, cn, "cardkingdom", f"buylist_{pt}")) or price_map.get((sc, cn, "cardkingdom", pt))


_INGEST_IMAGES_DIR = None  # Set in _get_ingest_images_dir()

# ── Background ingest worker ──
_ingest_executor: ThreadPoolExecutor | None = None
_scryfall_rate_lock = threading.Lock()
_scryfall_last_request: float = 0.0
_background_db_path: str | None = None
_shared_db_path: str | None = None


def _batch_ingest_query(image_id=None):
    """Build the query + params for batch ingest image selection."""
    query = """SELECT id, md5, stored_name, disambiguated, claude_result, confirmed_finishes
               FROM ingest_images
               WHERE status = 'DONE'
               AND md5 NOT IN (SELECT DISTINCT image_md5 FROM ingest_lineage)"""
    params = []
    if image_id is not None:
        query += " AND id = ?"
        params.append(image_id)
    return query, params


def _get_ingest_images_dir() -> Path:
    global _INGEST_IMAGES_DIR
    if _INGEST_IMAGES_DIR is None:
        from mtg_collector.utils import get_mtgc_home
        _INGEST_IMAGES_DIR = get_mtgc_home() / "ingest_images"
    _INGEST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return _INGEST_IMAGES_DIR


def _md5_file(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_card_crop(fragments, indices, image_w=None, image_h=None):
    """Compute union bounding box of fragment indices with 10% buffer, constrained to 63:88."""
    if not indices:
        return None
    xs, ys, xws, yhs = [], [], [], []
    for i in indices:
        if i < len(fragments):
            b = fragments[i]["bbox"]
            xs.append(b["x"])
            ys.append(b["y"])
            xws.append(b["x"] + b["w"])
            yhs.append(b["y"] + b["h"])
    if not xs:
        return None
    x1, y1 = min(xs), min(ys)
    x2, y2 = max(xws), max(yhs)
    w, h = x2 - x1, y2 - y1
    # Add 10% buffer
    bx, by = w * 0.1, h * 0.1
    x1 -= bx
    y1 -= by
    w += 2 * bx
    h += 2 * by
    # Constrain to 63:88 aspect ratio
    target_ratio = 63 / 88
    current_ratio = w / h if h > 0 else target_ratio
    if current_ratio > target_ratio:
        # Too wide, increase height
        new_h = w / target_ratio
        y1 -= (new_h - h) / 2
        h = new_h
    else:
        # Too tall, increase width
        new_w = h * target_ratio
        x1 -= (new_w - w) / 2
        w = new_w
    # Clamp to image bounds
    if image_w and image_h:
        x1 = max(0, x1)
        y1 = max(0, y1)
        if x1 + w > image_w:
            w = image_w - x1
        if y1 + h > image_h:
            h = image_h - y1
    return {"x": round(x1), "y": round(y1), "w": round(w), "h": round(h)}


def _merge_overlapping_cards(claude_cards, ocr_fragments):
    """Merge Claude-identified cards whose fragment bounding boxes heavily overlap.

    Sometimes Claude splits fragments from a single card into two objects (e.g. a
    full card + a ghost card with just the artist name from the bottom corner).
    This detects when one card's fragment bbox is mostly contained in another's
    and merges the smaller into the larger, combining fragment_indices and filling
    in any fields the larger card was missing.
    """
    if len(claude_cards) <= 1:
        return claude_cards

    def _fragment_bbox(card):
        """Compute raw union bbox of a card's fragment indices (no buffer)."""
        indices = card.get("fragment_indices", [])
        if not indices:
            return None
        xs, ys, xws, yhs = [], [], [], []
        for i in indices:
            if i < len(ocr_fragments):
                b = ocr_fragments[i]["bbox"]
                xs.append(b["x"])
                ys.append(b["y"])
                xws.append(b["x"] + b["w"])
                yhs.append(b["y"] + b["h"])
        if not xs:
            return None
        return (min(xs), min(ys), max(xws), max(yhs))

    def _overlap_fraction(inner, outer):
        """What fraction of inner's area is contained within outer?"""
        ix1, iy1, ix2, iy2 = inner
        ox1, oy1, ox2, oy2 = outer
        # Intersection
        xx1 = max(ix1, ox1)
        yy1 = max(iy1, oy1)
        xx2 = min(ix2, ox2)
        yy2 = min(iy2, oy2)
        if xx2 <= xx1 or yy2 <= yy1:
            return 0.0
        intersection = (xx2 - xx1) * (yy2 - yy1)
        inner_area = (ix2 - ix1) * (iy2 - iy1)
        return intersection / inner_area if inner_area > 0 else 0.0

    def _fields_conflict(a, b):
        """Check if two cards have conflicting non-null fields."""
        for key in ("name",):
            va = a.get(key)
            vb = b.get(key)
            if va and vb and str(va).lower() != str(vb).lower():
                return True
        # If both have printing_ids, check for any overlap (overlap = same card = no conflict)
        a_ids = set(a.get("printing_ids", []))
        b_ids = set(b.get("printing_ids", []))
        if a_ids and b_ids and not a_ids & b_ids:
            return True
        return False

    # Compute bboxes
    bboxes = [_fragment_bbox(c) for c in claude_cards]

    # Find pairs to merge: smaller card absorbed into larger card
    absorbed = set()  # indices of cards absorbed into another
    merge_into = {}   # absorbed_idx -> target_idx

    for i in range(len(claude_cards)):
        if i in absorbed:
            continue
        for j in range(len(claude_cards)):
            if j == i or j in absorbed:
                continue
            if bboxes[i] is None or bboxes[j] is None:
                continue
            # Check if j is mostly inside i
            frac = _overlap_fraction(bboxes[j], bboxes[i])
            if frac >= 0.7 and not _fields_conflict(claude_cards[i], claude_cards[j]):
                absorbed.add(j)
                merge_into[j] = i

    if not absorbed:
        return claude_cards

    # Perform merges
    merged = [dict(c) for c in claude_cards]  # shallow copy each
    for src_idx, dst_idx in merge_into.items():
        src = claude_cards[src_idx]
        dst = merged[dst_idx]
        # Merge fragment_indices
        dst_frags = set(dst.get("fragment_indices", []))
        dst_frags.update(src.get("fragment_indices", []))
        dst["fragment_indices"] = sorted(dst_frags)
        # Merge printing_ids (union, preserving dst order first)
        dst_pids = list(dst.get("printing_ids", []))
        src_pids = src.get("printing_ids", [])
        dst_pid_set = set(dst_pids)
        for pid in src_pids:
            if pid not in dst_pid_set:
                dst_pids.append(pid)
                dst_pid_set.add(pid)
        dst["printing_ids"] = dst_pids
        # Fill in missing fields from src
        for key in ("name", "notes"):
            if not dst.get(key) and src.get(key):
                dst[key] = src[key]

    result = [merged[i] for i in range(len(merged)) if i not in absorbed]
    _log_ingest(f"Merged overlapping cards: {len(claude_cards)} -> {len(result)}")
    return result


def _merge_nearby_fragments(fragments, gap_threshold=2.0):
    """Merge OCR fragments whose bounding boxes are within gap_threshold pixels of each other.

    Uses union-find to group fragments, then merges each group into a single
    fragment with combined text (left-to-right) and union bounding box.
    """
    n = len(fragments)
    if n == 0:
        return fragments

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    # Check all pairs for proximity
    for i in range(n):
        bi = fragments[i]["bbox"]
        i_x1, i_y1 = bi["x"], bi["y"]
        i_x2, i_y2 = i_x1 + bi["w"], i_y1 + bi["h"]
        for j in range(i + 1, n):
            bj = fragments[j]["bbox"]
            j_x1, j_y1 = bj["x"], bj["y"]
            j_x2, j_y2 = j_x1 + bj["w"], j_y1 + bj["h"]

            # Gap = distance between nearest edges; negative means overlap
            gap_x = max(i_x1 - j_x2, j_x1 - i_x2, 0)
            gap_y = max(i_y1 - j_y2, j_y1 - i_y2, 0)

            if gap_x <= gap_threshold and gap_y <= gap_threshold:
                union(i, j)

    # Group by root
    groups: dict[int, list[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    merged = []
    for indices in groups.values():
        # Sort left-to-right by x position so text reads naturally
        indices.sort(key=lambda i: fragments[i]["bbox"]["x"])
        text = " ".join(fragments[i]["text"] for i in indices)
        confidence = min(fragments[i]["confidence"] for i in indices)

        xs = [fragments[i]["bbox"]["x"] for i in indices]
        ys = [fragments[i]["bbox"]["y"] for i in indices]
        x2s = [fragments[i]["bbox"]["x"] + fragments[i]["bbox"]["w"] for i in indices]
        y2s = [fragments[i]["bbox"]["y"] + fragments[i]["bbox"]["h"] for i in indices]

        merged.append({
            "text": text,
            "bbox": {
                "x": min(xs),
                "y": min(ys),
                "w": max(x2s) - min(xs),
                "h": max(y2s) - min(ys),
            },
            "confidence": round(confidence, 3),
        })

    # Sort top-to-bottom, left-to-right
    merged.sort(key=lambda f: (f["bbox"]["y"], f["bbox"]["x"]))
    return merged


def _extract_ocr_name(ocr_fragments, fragment_indices):
    """Extract the card name from OCR fragments by finding the topmost text.

    The card name sits at the top of the card. We take the fragments assigned
    to this card, find the topmost ones (within 3px of each other vertically,
    to handle overlapping/nearby bounding boxes), and merge their text
    left-to-right.
    """
    if not ocr_fragments or not fragment_indices:
        return ""
    # Gather the fragments for this card
    frags = []
    for i in fragment_indices:
        if i < len(ocr_fragments):
            frags.append(ocr_fragments[i])
    if not frags:
        return ""
    # Find the minimum y (topmost fragment)
    min_y = min(f["bbox"]["y"] for f in frags)
    # Collect all fragments within 3px of the topmost
    top_frags = [f for f in frags if f["bbox"]["y"] - min_y <= 3]
    # Sort left-to-right and join
    top_frags.sort(key=lambda f: f["bbox"]["x"])
    return " ".join(f["text"] for f in top_frags)


def _narrow_candidates(candidates, card_info):
    """Narrow candidates using agent's printing_id ordering.

    When the agent emits printing_ids, candidates are already in preference
    order from _resolve_candidates. For legacy card_info format (user edits),
    falls back to narrowing by set and collector number.
    """
    if len(candidates) <= 1:
        return candidates
    # New format: agent already ordered by preference via printing_ids
    if card_info.get("printing_ids"):
        return candidates
    # Legacy format: narrow by set_code/collector_number
    result = candidates
    artist = (card_info.get("artist") or "").strip()
    if artist:
        al = _normalize_artist(artist)
        matched = [c for c in result if al in _normalize_artist(c.get("artist") or "")]
        if matched:
            result = matched
    set_code = (card_info.get("set_code") or "").strip()
    if set_code:
        sl = set_code.lower()
        matched = [c for c in result if c.get("set_code", "").lower() == sl]
        if matched:
            result = matched
    cn = (card_info.get("collector_number") or "").strip()
    if cn:
        matched = [c for c in result if c.get("collector_number") == cn]
        if matched:
            result = matched
    return result


def _format_candidates(raw_cards):
    """Format raw card dicts into the candidate shape the client expects."""
    formatted = []
    for c in raw_cards:
        image_uri = None
        if "image_uris" in c:
            image_uri = c["image_uris"].get("normal") or c["image_uris"].get("small")
        elif "card_faces" in c and c["card_faces"]:
            face = c["card_faces"][0]
            if "image_uris" in face:
                image_uri = face["image_uris"].get("normal") or face["image_uris"].get("small")

        prices = c.get("prices", {})
        price = prices.get("usd") or prices.get("usd_foil")

        formatted.append({
            "printing_id": c["id"],
            "name": c.get("name", "???"),
            "set_code": c.get("set", "???"),
            "set_name": c.get("set_name", ""),
            "collector_number": c.get("collector_number", "???"),
            "rarity": c.get("rarity", "unknown"),
            "image_uri": image_uri,
            "foil": "foil" in c.get("finishes", []),
            "finishes": c.get("finishes", []),
            "promo": c.get("promo", False),
            "full_art": c.get("full_art", False),
            "border_color": c.get("border_color", ""),
            "frame_effects": c.get("frame_effects", []),
            "price": price,
            "artist": c.get("artist", ""),
        })
    return formatted



def _local_name_search(conn, name, set_code=None, limit=20):
    """Search local DB for cards by name, return card dicts for _format_candidates."""
    from mtg_collector.db.models import CardRepository, PrintingRepository

    card_repo = CardRepository(conn)
    printing_repo = PrintingRepository(conn)

    cards = card_repo.search_cards_by_name(name, limit=limit)
    results = []
    for card in cards:
        printings = printing_repo.get_by_oracle_id(card.oracle_id)
        for p in printings:
            if set_code and p.set_code != set_code.lower():
                continue
            data = p.get_card_data()
            if data:
                results.append(data)
    return results


def _strip_accents(s):
    """Normalize unicode to ASCII for accent-insensitive comparison."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _normalize_artist(s):
    """Normalize artist name for fuzzy comparison.

    Strips accents, casefolds, removes punctuation (. and -), collapses whitespace.
    """
    import re
    n = _strip_accents(s).casefold()
    n = n.replace(".", "").replace("-", "")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _resolve_candidates(conn, card_infos):
    """Resolve agent card entries to candidate printings.

    The agent emits printing_ids directly from DB queries. We look up each ID
    and return the raw card data. Results merged and deduplicated across entries.
    Falls back to name/set/cn lookup for legacy card_info format (e.g. user edits).
    """
    all_candidates = {}  # printing_id → raw dict (dedup)

    for ci in card_infos:
        printing_ids = ci.get("printing_ids", [])

        if printing_ids:
            # New format: agent emitted printing_ids directly
            placeholders = ",".join("?" for _ in printing_ids)
            rows = conn.execute(
                f"SELECT printing_id, raw_json FROM printings WHERE printing_id IN ({placeholders})",
                printing_ids,
            ).fetchall()
            row_map = {}
            for r in rows:
                if r["raw_json"]:
                    row_map[r["printing_id"]] = json.loads(r["raw_json"])
            # Insert in agent's preferred order (most likely first)
            for pid in printing_ids:
                if pid in row_map and pid not in all_candidates:
                    all_candidates[pid] = row_map[pid]
        else:
            # Legacy format: name/set_code/collector_number (user card edits)
            conditions = ["s.digital = 0"]
            params = []

            name = (ci.get("name") or "").strip()
            sc = (ci.get("set_code") or "").strip().lower()
            cn = (ci.get("collector_number") or "").strip()

            if name:
                conditions.append("c.name COLLATE NOCASE = ?")
                params.append(name)
            if sc:
                conditions.append("p.set_code = ?")
                params.append(sc)
            if cn:
                stripped = cn.lstrip("0") or "0"
                if stripped != cn:
                    conditions.append("p.collector_number IN (?, ?)")
                    params.extend([cn, stripped])
                else:
                    conditions.append("p.collector_number = ?")
                    params.append(cn)
            if len(conditions) == 1:
                continue

            where = " AND ".join(conditions)
            rows = conn.execute(
                f"""SELECT DISTINCT p.raw_json, p.artist FROM printings p
                    JOIN cards c ON p.oracle_id = c.oracle_id
                    JOIN sets s ON p.set_code = s.set_code
                    WHERE {where}""",
                params,
            ).fetchall()

            # Post-filter by artist in Python (soft — fall back to all rows if no match)
            artist = (ci.get("artist") or "").strip()
            sql_matched = [r for r in rows if r[0]]
            if artist and sql_matched:
                artist_norm = _normalize_artist(artist)
                artist_filtered = [
                    r for r in sql_matched
                    if not r["artist"] or artist_norm in _normalize_artist(r["artist"])
                ]
                use = artist_filtered if artist_filtered else sql_matched
            else:
                use = sql_matched
            for r in use:
                data = json.loads(r[0])
                all_candidates[data["id"]] = data

    # Return in insertion order (agent's preferred order preserved)
    return list(all_candidates.values())


def _log_ingest(msg):
    sys.stderr.write(f"[INGEST] {msg}\n")
    sys.stderr.flush()


def _scryfall_rate_limit():
    """Enforce 100ms spacing between bulk import requests."""
    global _scryfall_last_request
    with _scryfall_rate_lock:
        now = time.time()
        elapsed = now - _scryfall_last_request
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        _scryfall_last_request = time.time()


def _has_api_key():
    """Check if ANTHROPIC_API_KEY is available."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _has_fake_agent():
    """Check if fake agent mode is enabled."""
    return bool(os.environ.get("MTGC_FAKE_AGENT"))


def _can_process():
    """Check if image processing is possible (real or fake agent)."""
    return _has_api_key() or _has_fake_agent()


def _process_image_core(conn, image_id, img, log_fn):
    """Process a single image: OCR -> Claude -> DB lookup. Returns final status string.

    Used by both the SSE endpoint and background workers.
    log_fn(event_type, data_dict) is called for progress events.
    """
    from mtg_collector.services.agent import run_agent as real_agent
    from mtg_collector.services.fake_agent import run_agent as fake_agent
    from mtg_collector.services.ocr import run_ocr_with_boxes

    def run_agent(image_path, ocr_fragments, status_callback=None, trace_out=None, set_hint=None):
        """Dispatch to fake or real agent based on env config.

        API key only: always real agent.
        API key + FAKE_AGENT: try fake, fall back to real on miss.
        FAKE_AGENT only: fake only, error on miss.
        """
        if _has_fake_agent():
            try:
                return fake_agent(image_path, ocr_fragments=ocr_fragments,
                                  status_callback=status_callback, trace_out=trace_out)
            except ValueError:
                if _has_api_key():
                    _log_ingest("Fake agent miss, falling back to real agent")
                else:
                    raise
        return real_agent(image_path, ocr_fragments=ocr_fragments,
                          status_callback=status_callback, trace_out=trace_out,
                          set_hint=set_hint)
    from mtg_collector.utils import now_iso

    image_path = str(_get_ingest_images_dir() / img["stored_name"])
    md5 = img["md5"]

    _log_ingest(f"Processing image {image_id}: {img['filename']} (MD5={md5})")

    ocr_fragments = None
    claude_cards = None
    agent_trace = []

    api_usage = None

    # Check cache
    cache_row = conn.execute(
        "SELECT ocr_result, claude_result, agent_trace, api_usage FROM ingest_cache WHERE image_md5 = ?",
        (md5,),
    ).fetchone()
    if cache_row:
        _log_ingest(f"Cache hit for MD5={md5}")
        ocr_fragments = json.loads(cache_row["ocr_result"])
        log_fn("cached", {"step": "ocr"})
        log_fn("ocr_complete", {"fragment_count": len(ocr_fragments), "fragments": ocr_fragments})
        if cache_row["claude_result"]:
            claude_cards = json.loads(cache_row["claude_result"])
            agent_trace = json.loads(cache_row["agent_trace"]) if cache_row["agent_trace"] else []
            api_usage = json.loads(cache_row["api_usage"]) if cache_row["api_usage"] else None
            log_fn("cached", {"step": "claude"})
            log_fn("claude_complete", {"cards": claude_cards})

    # Step 1: OCR
    if ocr_fragments is None:
        log_fn("status", {"message": "Running OCR..."})
        t0 = time.time()
        raw_fragments = run_ocr_with_boxes(image_path)
        elapsed = time.time() - t0
        _log_ingest(f"OCR complete: {len(raw_fragments)} fragments in {elapsed:.1f}s")
        ocr_fragments = _merge_nearby_fragments(raw_fragments)
        _log_ingest(f"Merged {len(raw_fragments)} -> {len(ocr_fragments)} fragments")
        log_fn("ocr_complete", {"fragment_count": len(ocr_fragments), "fragments": ocr_fragments})

    # Resolve set_hint early so we can pass it to the agent
    hint_set_code = None
    raw_hint = (img.get("set_hint") or "").strip()
    if raw_hint:
        from mtg_collector.db.models import SetRepository
        set_repo = SetRepository(conn)
        s = set_repo.get(raw_hint.lower())
        if not s:
            s = set_repo.get_by_name(raw_hint)
        if s:
            hint_set_code = s.set_code
            _log_ingest(f"Resolved set_hint '{raw_hint}' -> {hint_set_code}")

    # Step 2: Agent extraction
    if claude_cards is None:
        log_fn("status", {"message": "Calling agent..."})
        t0 = time.time()
        try:
            claude_cards, _, api_usage = run_agent(
                image_path,
                ocr_fragments=ocr_fragments,
                status_callback=lambda msg: log_fn("status", {"message": msg}),
                trace_out=agent_trace,
                set_hint=hint_set_code,
            )
        except Exception as e:
            e.agent_trace = agent_trace
            raise
        elapsed = time.time() - t0
        _log_ingest(f"Agent complete: {len(claude_cards)} cards in {elapsed:.1f}s")
        _log_ingest(f"Agent structured output: {json.dumps(claude_cards, indent=2)}")
        log_fn("claude_complete", {"cards": claude_cards})

    # Merge cards whose fragment bboxes heavily overlap (e.g. ghost artist-only card)
    claude_cards = _merge_overlapping_cards(claude_cards, ocr_fragments)

    best = claude_cards[0] if claude_cards else None

    # Save to cache
    conn.execute(
        """INSERT OR REPLACE INTO ingest_cache
           (image_md5, image_path, ocr_result, claude_result, agent_trace, api_usage, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (md5, image_path, json.dumps(ocr_fragments),
         json.dumps(claude_cards), json.dumps(agent_trace),
         json.dumps(api_usage) if api_usage else None, now_iso()),
    )
    conn.commit()

    # Step 3: Local DB resolution
    log_fn("status", {"message": "Resolving card..."})

    all_matches = []
    all_crops = []

    if best:
        candidates = _resolve_candidates(conn, claude_cards)

        # If the user provided a set hint, promote candidates from that set
        # to the front of the list so the correct printing is auto-selected.
        if hint_set_code and candidates:
            hinted = [c for c in candidates if c.get("set", "").lower() == hint_set_code]
            others = [c for c in candidates if c.get("set", "").lower() != hint_set_code]
            if hinted:
                candidates = hinted + others
                _log_ingest(f"Set hint '{hint_set_code}': promoted {len(hinted)} candidate(s) to front")

        formatted = _format_candidates(candidates)
        all_matches.append(formatted)
        _log_ingest(f"Resolved {len(formatted)} candidates for '{best.get('name', '???')}'")

        frag_indices = best.get("fragment_indices", [])
        all_crops.append(_compute_card_crop(ocr_fragments, frag_indices))
    else:
        all_matches.append([])
        all_crops.append(None)

    # Check lineage for already-ingested card
    lineage_row = conn.execute(
        "SELECT card_index FROM ingest_lineage WHERE image_md5 = ? AND card_index = 0",
        (md5,),
    ).fetchone()
    disambiguated = ["already_ingested" if lineage_row else None]

    return ocr_fragments, claude_cards, all_matches, all_crops, disambiguated, agent_trace, api_usage



def _reset_ingest_image(conn, image_id, md5, now):
    """Clear all artifacts for an ingest_images row and reset it to READY_FOR_OCR.

    Deletes the ingest_cache entry, removes any previously ingested collection
    entries and lineage records, and nulls all processing columns.

    Returns the number of collection entries removed.
    Does NOT commit — caller is responsible.
    """
    lineage_rows = conn.execute(
        "SELECT collection_id FROM ingest_lineage WHERE image_md5=?", (md5,)
    ).fetchall()
    removed = 0
    if lineage_rows:
        collection_ids = [r["collection_id"] for r in lineage_rows]
        placeholders = ",".join("?" * len(collection_ids))
        conn.execute("DELETE FROM ingest_lineage WHERE image_md5=?", (md5,))
        conn.execute(f"DELETE FROM collection WHERE id IN ({placeholders})", collection_ids)
        removed = len(collection_ids)

    conn.execute("DELETE FROM ingest_cache WHERE image_md5=?", (md5,))

    conn.execute(
        """UPDATE ingest_images SET
            status='READY_FOR_OCR',
            ocr_result=NULL,
            claude_result=NULL,
            agent_trace=NULL,
            api_usage=NULL,
            scryfall_matches=NULL,
            crops=NULL,
            disambiguated=NULL,
            names_data=NULL,
            names_disambiguated=NULL,
            user_card_edits=NULL,
            confirmed_finishes=NULL,
            error_message=NULL,
            updated_at=?
           WHERE id=?""",
        (now, image_id),
    )
    return removed


def _refinish_ingest_image(conn, image_id, md5):
    """Remove all collection entries and lineage for an image so it can be re-finished.

    Preserves all Agent identification (disambiguated, claude_result, etc.).
    Clears all confirmed_finishes entries. Sets image status to DONE.

    Does NOT commit — caller is responsible.
    """
    from mtg_collector.utils import now_iso

    # Delete all lineage + collection entries for this image
    lineage_rows = conn.execute(
        "SELECT collection_id FROM ingest_lineage WHERE image_md5=?", (md5,)
    ).fetchall()
    if lineage_rows:
        collection_ids = [r["collection_id"] for r in lineage_rows]
        placeholders = ",".join("?" * len(collection_ids))
        conn.execute("DELETE FROM ingest_lineage WHERE image_md5=?", (md5,))
        conn.execute(f"DELETE FROM collection WHERE id IN ({placeholders})", collection_ids)

    # Clear all confirmed_finishes
    img = conn.execute(
        "SELECT confirmed_finishes FROM ingest_images WHERE id=?", (image_id,)
    ).fetchone()
    cleared_finishes = None
    if img and img["confirmed_finishes"]:
        finishes = json.loads(img["confirmed_finishes"])
        cleared_finishes = json.dumps([None] * len(finishes))

    conn.execute(
        "UPDATE ingest_images SET status='DONE', confirmed_finishes=?, updated_at=? WHERE id=?",
        (cleared_finishes, now_iso(), image_id),
    )


def _process_image_background(db_path, image_id):
    """Background worker: process one image end-to-end in its own thread."""
    from mtg_collector.db.schema import init_db
    from mtg_collector.utils import now_iso

    _log_ingest(f"[bg:{image_id}] Background worker started")

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row

    if _shared_db_path and os.path.exists(_shared_db_path):
        from mtg_collector.db.connection import attach_shared
        attach_shared(conn, _shared_db_path)
        # FK enforcement is incompatible with ATTACH'd shared tables.
    else:
        conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    # Atomic claim
    cursor = conn.execute(
        "UPDATE ingest_images SET status='PROCESSING', updated_at=? WHERE id=? AND status='READY_FOR_OCR'",
        (now_iso(), image_id),
    )
    conn.commit()
    if cursor.rowcount == 0:
        _log_ingest(f"[bg:{image_id}] Skipped — not READY_FOR_OCR")
        conn.close()
        return

    row = conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone()
    img = dict(row)

    def log_fn(event_type, data_obj):
        # Background worker just logs, no SSE
        if event_type == "status":
            _log_ingest(f"[bg:{image_id}] {data_obj.get('message', '')}")

    try:
        ocr_fragments, claude_cards, all_matches, all_crops, disambiguated, agent_trace, api_usage = _process_image_core(
            conn, image_id, img, log_fn,
        )

        final_status = "READY_FOR_DISAMBIGUATION"

        # Auto-select best candidate for each card slot.
        # Single printing → auto-confirm. Multiple → narrow and pick first.
        # Does NOT create collection/lineage — batch ingest does that.
        confirmed_finishes = [None] * len(disambiguated) if disambiguated else []
        for idx in range(len(disambiguated or [])):
            if disambiguated[idx] is not None:
                continue
            candidates = all_matches[idx] if idx < len(all_matches) else []
            if not candidates:
                continue
            card_info = claude_cards[idx] if idx < len(claude_cards) else {}

            unique_ids = {c.get("printing_id") or c.get("scryfall_id") for c in candidates}
            if len(unique_ids) == 1:
                pick = candidates[0]
            else:
                narrowed = _narrow_candidates(candidates, card_info)
                pick = narrowed[0]

            sid = pick.get("printing_id") or pick.get("scryfall_id")
            finishes = pick.get("finishes", ["nonfoil"])
            finish = "nonfoil" if "nonfoil" in finishes else finishes[0]
            disambiguated[idx] = sid
            confirmed_finishes[idx] = finish
            _log_ingest(f"[bg:{image_id}] Auto-selected {sid} as {finish}")

        if disambiguated and all(d is not None for d in disambiguated):
            final_status = "DONE"

        # Save state
        conn.execute(
            """UPDATE ingest_images SET
                status=?, ocr_result=?, claude_result=?, agent_trace=?, api_usage=?,
                scryfall_matches=?, crops=?, disambiguated=?, confirmed_finishes=?,
                updated_at=?
               WHERE id=?""",
            (final_status, json.dumps(ocr_fragments), json.dumps(claude_cards),
             json.dumps(agent_trace), json.dumps(api_usage) if api_usage else None,
             json.dumps(all_matches), json.dumps(all_crops),
             json.dumps(disambiguated), json.dumps(confirmed_finishes),
             now_iso(), image_id),
        )
        conn.commit()
        _log_ingest(f"[bg:{image_id}] Finished -> {final_status}")

    except Exception as e:
        tb = traceback.format_exc()
        _log_ingest(f"[bg:{image_id}] ERROR: {e}\n{tb}")
        partial_trace = getattr(e, "agent_trace", [])
        conn.execute(
            "UPDATE ingest_images SET status='ERROR', agent_trace=?, error_message=?, updated_at=? WHERE id=?",
            (json.dumps(partial_trace) if partial_trace else None, f"{e}\n{tb}", now_iso(), image_id),
        )
        conn.commit()
    finally:
        conn.close()


def _recover_pending_images(db_path):
    """On startup, re-queue any READY_FOR_OCR or stale PROCESSING images."""
    from mtg_collector.db.schema import init_db
    from mtg_collector.utils import now_iso

    print("[startup] Running database migrations ...", flush=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if _shared_db_path and os.path.exists(_shared_db_path):
        from mtg_collector.db.connection import attach_shared
        attach_shared(conn, _shared_db_path)
    init_db(conn)
    print("[startup] Database ready", flush=True)

    # Reset stale PROCESSING (>10 min old) back to READY_FOR_OCR
    cutoff = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE ingest_images SET status='READY_FOR_OCR', updated_at=?
           WHERE status='PROCESSING'
           AND updated_at < datetime(?, '-600 seconds')""",
        (now_iso(), cutoff),
    )
    conn.commit()

    # Re-queue all READY_FOR_OCR (only if processing is possible)
    rows = conn.execute("SELECT id FROM ingest_images WHERE status='READY_FOR_OCR'").fetchall()
    conn.close()

    if rows and _can_process():
        print(f"[startup] Re-queuing {len(rows)} pending image(s) for OCR", flush=True)
        for row in rows:
            _log_ingest(f"Recovering image {row['id']} for background processing")
            _ingest_executor.submit(_process_image_background, db_path, row["id"])
    elif rows:
        print(f"[startup] {len(rows)} pending image(s) waiting — ANTHROPIC_API_KEY not set, skipping processing", flush=True)


# /api/collection price and Card Kingdom URL enrichment, folded into the main
# query.  This used to be two follow-up passes whose `IN (...)` clauses were
# sized by the result set: 112,809 rows built a statement with 225,618 bound
# parameters, within 11% of this build's SQLITE_MAX_VARIABLE_NUMBER of 250,000.
# Every join below binds zero parameters and matches at most one row, so neither
# the SQL text nor the row cardinality depends on how large the result set is.
#
# `latest_prices` has PRIMARY KEY (set_code, collector_number, source,
# price_type), so pinning source and price_type makes each price join
# single-row.  price_type follows the physical copy's finish (c.finish), not the
# printing's available finishes, so a foil copy of a printing that also exists
# in nonfoil gets the foil price; etched copies price as foil.
_ENRICH_JOINS = [
    "LEFT JOIN latest_prices _ck_buy ON _ck_buy.set_code = p.set_code"
    " AND _ck_buy.collector_number = p.collector_number"
    " AND _ck_buy.source = 'cardkingdom'"
    " AND _ck_buy.price_type = CASE WHEN c.finish IN ('foil', 'etched') THEN 'buylist_foil' ELSE 'buylist_normal' END",
    "LEFT JOIN latest_prices _ck_retail ON _ck_retail.set_code = p.set_code"
    " AND _ck_retail.collector_number = p.collector_number"
    " AND _ck_retail.source = 'cardkingdom'"
    " AND _ck_retail.price_type = CASE WHEN c.finish IN ('foil', 'etched') THEN 'foil' ELSE 'normal' END",
    "LEFT JOIN latest_prices _tcg ON _tcg.set_code = p.set_code"
    " AND _tcg.collector_number = p.collector_number"
    " AND _tcg.source = 'tcgplayer'"
    " AND _tcg.price_type = CASE WHEN c.finish IN ('foil', 'etched') THEN 'foil' ELSE 'normal' END",
    # printing_id is not unique in mtgjson_printings: MTGJSON emits one row per
    # face of a double-faced card and both carry the same scryfallId, with a
    # different Card Kingdom link each.  Resolve to the front face's uuid so the
    # join stays single-row and names the card the user is looking at — the rule
    # lives in mtgjson_faces so this page, /card/:set/:cn, the binder grid and
    # the deck page cannot drift into linking one card to two products.
    "LEFT JOIN mtgjson_printings _mp ON _mp.uuid ="
    f" {front_face_uuid_sql('p.printing_id')}",
]

# The price joins alone — every _ENRICH_JOINS entry that a display price can be
# built from, without the ck_url lookup.  The totals scan the whole result, so
# they take this rather than the full set.
_ENRICH_PRICE_JOINS = _ENRICH_JOINS[:3]

# Card Kingdom publishes a buylist and a retail price; the buylist wins when
# present.  A foil copy falls back to the nonfoil URL when there is no foil one.
_ENRICH_COLUMNS = """COALESCE(_ck_buy.price, _ck_retail.price) as ck_price,
                    _tcg.price as tcg_price,
                    COALESCE(NULLIF(CASE WHEN c.finish IN ('foil', 'etched') THEN _mp.ck_url_foil END, ''), _mp.ck_url, '') as ck_url"""


# Page bounds for /api/collection. Measured on the real payload (108,630 rows
# for is:unowned): a 250-row page is 212 KB raw / 28 KB gzipped and 434 round
# trips to walk the catalog; 1000 is 855 KB / 103 KB and 108 trips. There is no
# unbounded escape hatch and no sentinel — every caller takes these semantics.
COLLECTION_LIMIT_DEFAULT = 250
COLLECTION_LIMIT_MAX = 1000


def _normalize_page_path(path: str) -> str:
    """Drop a trailing slash from a page path: `/sets/` is `/sets`.

    Every page route here is a pair -- an exact match for the parent (`/sets`,
    `/decks`, `/orders`) and a prefix match for the child (`/sets/:code`,
    `/decks/:id`) -- and a trailing slash falls to the child with an empty
    name.  `/sets/` served the binder grid for a set whose code was `""`, which
    rendered as a set you own nothing from.  A trailing slash is not a request
    for a child called nothing, so it is stripped once here rather than guarded
    at each of the pairs.

    API paths are left exactly as they arrive.  They are built by our own JS
    rather than typed, and `/api/set-browse/` has to keep reaching its handler
    so the answer is a 400 naming the empty code -- normalising it away would
    turn that into a bare 404.
    """
    if path.startswith("/api/"):
        return path
    return path.rstrip("/") or "/"


class PageParamError(ValueError):
    """A limit/offset the caller must fix. Surfaced as a 400, never clamped."""


def _parse_page_params(params: dict) -> tuple[int, int]:
    """Return (limit, offset) from query params, or raise PageParamError."""
    limit = _page_int(params, "limit", COLLECTION_LIMIT_DEFAULT)
    offset = _page_int(params, "offset", 0)
    if not 1 <= limit <= COLLECTION_LIMIT_MAX:
        raise PageParamError(f"limit must be between 1 and {COLLECTION_LIMIT_MAX}")
    if offset < 0:
        raise PageParamError("offset must be 0 or greater")
    return limit, offset


def _page_int(params: dict, name: str, default: int) -> int:
    raw = params.get(name, [""])[0].strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise PageParamError(f"{name} must be an integer") from None


#: A set code as Scryfall and MTGJSON both write it: lowercase alphanumeric.
#: Length is deliberately unbounded -- codes have grown from three characters
#: to six and a cap here would reject a real set as malformed.
_SET_CODE_RE = re.compile(r"[a-z0-9]+")


def _parse_set_code(raw: str) -> str:
    """Return the canonical set code, or raise PageParamError.

    "Not cached (run `mtg cache all` to populate)" is the right answer only for
    a code that could name a set and does not.  `/sets/` asked for the empty
    code and got that message, which names a plausible wrong cause: it sends
    the reader to the catalogue -- a fetch, an import, a backfill -- while the
    fault is entirely in the URL.  An error that is trusted and wrong costs
    more than a generic one, so a code that cannot name a set is a 400 about
    the code and says nothing about the cache.
    """
    code = raw.strip().lower()
    if not _SET_CODE_RE.fullmatch(code):
        raise PageParamError(
            f"set code must be a non-empty alphanumeric code, got {raw!r}"
        )
    return code


def _parse_set_browse_params(params: dict):
    """Return the /api/set-browse view params, or raise PageParamError.

    Every unknown value is a 400 rather than a fallback to the default. A view
    that quietly ignored `sort=collector` would hand back a grid in the wrong
    order and look like the endpoint was broken; the caller can fix a typo, and
    cannot fix a silent one.
    """
    from mtg_collector.db.set_browse import (
        DEFAULT_SECTIONS,
        FILTERS,
        SECTIONS,
        SORT_KEYS,
        BrowseParams,
    )

    def _one(name: str, default: str, allowed) -> str:
        value = params.get(name, [""])[0].strip() or default
        if value not in allowed:
            raise PageParamError(f"{name} must be one of {', '.join(allowed)}")
        return value

    raw_sections = params.get("sections", [""])[0].strip()
    if raw_sections:
        sections = tuple(s.strip() for s in raw_sections.split(",") if s.strip())
        unknown = [s for s in sections if s not in SECTIONS]
        if unknown or not sections:
            raise PageParamError(f"sections must be a comma-separated subset of {', '.join(SECTIONS)}")
    else:
        sections = DEFAULT_SECTIONS

    return BrowseParams(
        sort=_one("sort", "number", SORT_KEYS),
        order=_one("order", "asc", ("asc", "desc")),
        filter=_one("filter", "all", FILTERS),
        sections=sections,
        q=params.get("q", [""])[0].strip(),
    )


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class CrackPackHandler(BaseHTTPRequestHandler):
    """HTTP handler for crack-a-pack web UI."""

    # HTTP/1.1 keep-alive: reuses one TCP+TLS connection for the whole page's
    # assets instead of a fresh handshake per request. Requires Content-Length
    # on every response that has a body -- `_respond` sets it, and the 304 and
    # 416 paths deliberately do not, because neither carries one.
    protocol_version = "HTTP/1.1"

    def __init__(self, generator: PackGenerator, static_dir: Path, db_path: str, *args, **kwargs):
        self.generator = generator
        self.static_dir = static_dir
        self.db_path = db_path
        super().__init__(*args, **kwargs)

    def _get_conn(self):
        """Get a DB connection, optionally ATTACHing a shared reference DB."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        if _shared_db_path and os.path.exists(_shared_db_path):
            from mtg_collector.db.connection import attach_shared
            attach_shared(conn, _shared_db_path)
            # FK enforcement is incompatible with ATTACH'd shared tables —
            # SQLite FK checks only see empty main-schema tables.
        else:
            conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def do_GET(self):
        parsed = urlparse(self.path)
        path = _normalize_page_path(parsed.path)
        params = parse_qs(parsed.query)

        page = match_page_route(path)
        if page is not None:
            self._serve_page(page)
        elif path == "/api/sets":
            self._api_sets()
        elif path == "/api/sets/index":
            self._api_sets_index()
        elif path == "/api/cached-sets":
            self._api_cached_sets()
        elif path == "/api/search-suggest":
            self._api_search_suggest(params)
        elif path == "/api/products":
            set_code = params.get("set", [""])[0]
            self._api_products(set_code)
        elif path == "/api/sheets":
            set_code = params.get("set", [""])[0]
            product = params.get("product", [""])[0]
            self._api_sheets(set_code, product)
        elif path.startswith("/api/collection/") and path.endswith("/history"):
            cid = path[len("/api/collection/"):-len("/history")]
            if cid.isdigit():
                self._api_collection_history(int(cid))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path == "/api/collection/copies":
            self._api_collection_copies(params)
        elif path == "/api/collection/growth":
            self._api_collection_growth(params)
        elif path == "/api/collection":
            self._api_collection(params)
        elif path == "/api/search":
            # Legacy alias for /api/collection, kept for external callers since
            # 24fc389. Not a redirect and not a second implementation: the same
            # handler runs, so both routes take the same params, the same page
            # bounds and the same response shape, and neither can drift from the
            # other. tests/integration/test_search_alias.py pins that. Anything
            # /api/search should do differently belongs in _api_collection.
            self._api_collection(params)
        elif path == "/api/wishlist":
            self._api_wishlist_list(params)
        elif path == "/api/cards/by-name":
            self._api_card_by_name(params)
        elif path == "/api/card/by-set-cn":
            self._api_card_by_set_cn(params)
        elif path.startswith("/api/card/"):
            printing_id = path[len("/api/card/"):]
            self._api_card(printing_id)
        elif path.startswith("/api/set-browse/"):
            set_code = path[len("/api/set-browse/"):]
            self._api_set_browse(set_code, params)
        elif path in ("/api/batches", "/api/corner-batches"):
            self._api_batches_list(params)
        elif (path.startswith("/api/batches/") or path.startswith("/api/corner-batches/")) and path.endswith("/cards"):
            prefix = "/api/batches/" if path.startswith("/api/batches/") else "/api/corner-batches/"
            bid = path[len(prefix):-len("/cards")]
            if bid.isdigit():
                self._api_batch_cards(int(bid))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path == "/api/orders":
            self._api_orders_list()
        elif path.startswith("/api/orders/") and path.endswith("/cards"):
            oid = path[len("/api/orders/"):-len("/cards")]
            self._api_order_cards(int(oid))
        elif path.startswith("/api/orders/"):
            oid = path[len("/api/orders/"):]
            if oid.isdigit():
                self._api_order_get(int(oid))
        elif path == "/api/settings":
            self._api_get_settings()
        elif path == "/api/prices-status":
            self._api_prices_status()
        elif path.startswith("/api/price-history/"):
            parts = path[len("/api/price-history/"):].split("/", 1)
            if len(parts) == 2:
                self._api_price_history(parts[0], parts[1])
            else:
                self._send_json({"error": "Expected /api/price-history/{set_code}/{collector_number}"}, 400)
        elif path == "/api/shorten":
            self._api_shorten(params)
        # Ingest2 API routes
        elif path == "/api/ingest2/images":
            self._api_ingest2_images(params)
        elif path == "/api/ingest2/counts":
            self._api_ingest2_counts()
        elif path == "/api/ingest2/usage-stats":
            self._api_ingest2_usage_stats(params)
        elif path == "/api/ingest2/recent":
            self._api_ingest2_recent(params)
        elif path == "/api/ingest2/pending-disambiguation":
            self._api_ingest2_pending_disambiguation()
        elif path.startswith("/api/ingest2/images/"):
            image_id = path[len("/api/ingest2/images/"):]
            self._api_ingest2_image_detail(int(image_id))
        elif path.startswith("/api/ingest2/process/"):
            image_id = path[len("/api/ingest2/process/"):]
            self._api_ingest2_process_sse(int(image_id))
        elif path == "/api/ingest2/next-card":
            image_id = params.get("image_id", [""])[0]
            self._api_ingest2_next_card(int(image_id) if image_id else None)
        elif path.startswith("/api/ingest/image/"):
            filename = unquote(path[len("/api/ingest/image/"):])
            self._api_ingest_serve_image(filename)
        # Sealed product API routes
        elif path == "/api/sealed/products/sets":
            self._api_sealed_products_sets()
        elif path.startswith("/api/sealed/products/") and path.endswith("/contents"):
            uuid = path[len("/api/sealed/products/"):-len("/contents")]
            self._api_sealed_product_contents(uuid)
        elif path.startswith("/api/sealed/products/"):
            uuid = path[len("/api/sealed/products/"):]
            self._api_sealed_product_detail(uuid)
        elif path == "/api/sealed/products":
            self._api_sealed_products(params)
        elif path == "/api/sealed/prices-status":
            self._api_sealed_prices_status()
        elif path.startswith("/api/sealed/prices/"):
            tcg_id = path[len("/api/sealed/prices/"):]
            self._api_sealed_price_history(tcg_id)
        elif path == "/api/sealed/collection/stats":
            self._api_sealed_collection_stats()
        elif path == "/api/sealed/collection":
            self._api_sealed_collection_list(params)
        # Deck Builder API routes
        elif path == "/api/deck-builder/commanders":
            self._api_builder_commanders(params)
        elif path == "/api/deck-builder/commanders/browse":
            self._api_builder_browse_commanders(params)
        elif path.startswith("/api/deck-builder/") and path.endswith("/search"):
            did = path[len("/api/deck-builder/"):-len("/search")]
            if did.isdigit():
                self._api_builder_search(int(did), params)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/deck-builder/") and path.endswith("/mana-analysis"):
            did = path[len("/api/deck-builder/"):-len("/mana-analysis")]
            if did.isdigit():
                self._api_builder_mana_analysis(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/deck-builder/") and not path.endswith("/cards"):
            did = path[len("/api/deck-builder/"):]
            if did.isdigit():
                self._api_builder_get(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        # Printing API routes
        elif path.startswith("/api/printings/by-oracle/"):
            oracle_id = path[len("/api/printings/by-oracle/"):]
            self._api_printings_by_oracle(oracle_id)
        # Deck API routes
        elif path == "/api/decks/by-origin":
            self._api_deck_by_origin(params)
        elif path == "/api/decks":
            self._api_decks_list()
        elif path.startswith("/api/decks/") and path.endswith("/expected"):
            did = path[len("/api/decks/"):-len("/expected")]
            if did.isdigit():
                self._api_deck_expected_get(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/completeness"):
            did = path[len("/api/decks/"):-len("/completeness")]
            if did.isdigit():
                self._api_deck_completeness(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/cards"):
            did = path[len("/api/decks/"):-len("/cards")]
            if did.isdigit():
                self._api_deck_cards(int(did), params)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/"):
            did = path[len("/api/decks/"):]
            if did.isdigit():
                self._api_deck_get(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        # Precon / Jumpstart import picker
        elif path == "/api/precons/sets":
            self._api_precons_sets(params)
        elif path == "/api/precons/decks":
            self._api_precons_decks(params)
        # Binder API routes
        elif path == "/api/binders":
            self._api_binders_list()
        elif path.startswith("/api/binders/") and path.endswith("/cards"):
            bid = path[len("/api/binders/"):-len("/cards")]
            if bid.isdigit():
                self._api_binder_cards(int(bid))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/binders/"):
            bid = path[len("/api/binders/"):]
            if bid.isdigit():
                self._api_binder_get(int(bid))
            else:
                self._send_json({"error": "Not found"}, 404)
        # Collection view API routes
        elif path == "/api/views":
            self._api_views_list()
        elif path.startswith("/api/views/"):
            vid = path[len("/api/views/"):]
            if vid.isdigit():
                self._api_view_get(int(vid))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._api_generate(data)
        elif path == "/api/fetch-prices":
            self._api_fetch_prices()
        elif path == "/api/ingest2/upload":
            self._api_ingest2_upload()
        elif path == "/api/ingest2/set-params":
            self._api_ingest2_set_params()
        elif path == "/api/ingest2/confirm":
            self._api_ingest2_confirm()
        elif path == "/api/ingest2/skip":
            self._api_ingest2_skip()
        elif path == "/api/ingest2/correct":
            self._api_ingest2_correct()
        elif path == "/api/ingest2/search-card":
            self._api_ingest2_search_card()
        elif path == "/api/ingest2/update-cards":
            self._api_ingest2_update_cards()
        elif path == "/api/ingest2/add-card":
            self._api_ingest2_add_card()
        elif path == "/api/ingest2/remove-card":
            self._api_ingest2_remove_card()
        elif path == "/api/ingest2/delete":
            self._api_ingest2_delete()
        elif path == "/api/ingest2/reset":
            self._api_ingest2_reset()
        elif path == "/api/ingest2/refinish":
            self._api_ingest2_refinish()
        elif path == "/api/ingest2/batch-ingest":
            self._api_ingest2_batch_ingest()
        elif path == "/api/wishlist":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._api_wishlist_add(data)
        elif path == "/api/wishlist/bulk":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._api_wishlist_bulk_add(data)
        elif path == "/api/corners/detect":
            self._api_corners_detect()
        elif path == "/api/corners/commit":
            self._api_corners_commit()
        elif (path.startswith("/api/batches/") or path.startswith("/api/corner-batches/")) and path.endswith("/assign-deck"):
            prefix = "/api/batches/" if path.startswith("/api/batches/") else "/api/corner-batches/"
            bid = path[len(prefix):-len("/assign-deck")]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_batch_assign_deck(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/batches/") and path.endswith("/update"):
            bid = path[len("/api/batches/"):-len("/update")]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_batch_update(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path == "/api/ingest-ids/resolve":
            self._api_ingest_ids_resolve()
        elif path == "/api/ingest-ids/commit":
            self._api_ingest_ids_commit()
        elif path == "/api/order/parse":
            self._api_order_parse()
        elif path == "/api/order/resolve":
            self._api_order_resolve()
        elif path == "/api/order/commit":
            self._api_order_commit()
        elif path.startswith("/api/collection/") and path.endswith("/receive"):
            cid = path[len("/api/collection/"):-len("/receive")]
            self._api_collection_receive(int(cid))
        elif path.startswith("/api/orders/") and path.endswith("/receive"):
            oid = path[len("/api/orders/"):-len("/receive")]
            self._api_order_receive(int(oid))
        elif path.startswith("/api/orders/") and path.endswith("/add-card"):
            oid = path[len("/api/orders/"):-len("/add-card")]
            self._api_order_add_card(int(oid))
        elif path.startswith("/api/wishlist/") and path.endswith("/fulfill"):
            wid = path[len("/api/wishlist/"):-len("/fulfill")]
            self._api_wishlist_fulfill(int(wid))
        elif path == "/api/collection":
            data = self._read_json_body()
            if data is None:
                return
            self._api_collection_add(data)
        elif path == "/api/collection/bulk-delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._api_collection_bulk_delete(data)
        elif path.startswith("/api/collection/") and path.endswith("/dispose"):
            entry_id = path[len("/api/collection/"):-len("/dispose")]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._api_collection_dispose(int(entry_id), data)
        elif path == "/api/import/parse":
            self._api_import_parse()
        elif path == "/api/import/resolve":
            self._api_import_resolve()
        elif path == "/api/import/commit":
            self._api_import_commit()
        # Sealed price fetch + TCGPlayer lookup
        elif path == "/api/sealed/fetch-prices":
            self._api_sealed_fetch_prices()
        elif path == "/api/sealed/from-tcgplayer":
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_from_tcgplayer(data)
        # Sealed collection POST routes
        elif path == "/api/sealed/collection":
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_collection_add(data)
        elif path == "/api/sealed/open":
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_open(data)
        elif path == "/api/sealed/collection/bulk-dispose":
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_collection_bulk_dispose(data)
        elif path.startswith("/api/sealed/collection/") and path.endswith("/dispose"):
            entry_id = path[len("/api/sealed/collection/"):-len("/dispose")]
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_collection_dispose(int(entry_id), data)
        # Deck Builder POST routes
        elif path == "/api/deck-builder":
            data = self._read_json_body()
            if data is None:
                return
            self._api_builder_create(data)
        elif path.startswith("/api/deck-builder/") and path.endswith("/cards"):
            did = path[len("/api/deck-builder/"):-len("/cards")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_add_card(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/deck-builder/") and path.endswith("/sql-search"):
            did = path[len("/api/deck-builder/"):-len("/sql-search")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_sql_search(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/deck-builder/") and path.endswith("/add-basics"):
            did = path[len("/api/deck-builder/"):-len("/add-basics")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_add_basics(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/deck-builder/") and path.endswith("/bling"):
            did = path[len("/api/deck-builder/"):-len("/bling")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_bling(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        # Deck POST routes
        elif path == "/api/decks":
            data = self._read_json_body()
            if data is None:
                return
            self._api_deck_create(data)
        elif path == "/api/precons/import":
            data = self._read_json_body()
            if data is None:
                return
            self._api_precons_import(data)
        elif path.startswith("/api/decks/") and path.endswith("/expected"):
            did = path[len("/api/decks/"):-len("/expected")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_expected_set(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/materialize"):
            did = path[len("/api/decks/"):-len("/materialize")]
            if did.isdigit():
                self._api_deck_materialize(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/reassemble"):
            did = path[len("/api/decks/"):-len("/reassemble")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_reassemble(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/expected-cards/add"):
            did = path[len("/api/decks/"):-len("/expected-cards/add")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_expected_add(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/expected-cards/remove"):
            did = path[len("/api/decks/"):-len("/expected-cards/remove")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_expected_remove(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/cards/quantity"):
            did = path[len("/api/decks/"):-len("/cards/quantity")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_adjust_quantity(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/expected-cards/swap"):
            did = path[len("/api/decks/"):-len("/expected-cards/swap")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_expected_swap(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/cards/move"):
            did = path[len("/api/decks/"):-len("/cards/move")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_move_cards(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/cards"):
            did = path[len("/api/decks/"):-len("/cards")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_add_cards(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        # Binder POST routes
        elif path == "/api/binders":
            data = self._read_json_body()
            if data is None:
                return
            self._api_binder_create(data)
        elif path.startswith("/api/binders/") and path.endswith("/cards/move"):
            bid = path[len("/api/binders/"):-len("/cards/move")]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_binder_move_cards(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/binders/") and path.endswith("/cards"):
            bid = path[len("/api/binders/"):-len("/cards")]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_binder_add_cards(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        # Collection view POST routes
        elif path == "/api/views":
            data = self._read_json_body()
            if data is None:
                return
            self._api_view_create(data)
        elif path == "/api/set-value-data":
            data = self._read_json_body()
            if data is None:
                return
            self._api_set_value_data(data)
        # Jumpstart API routes
        elif path == "/api/jumpstart/find-card":
            data = self._read_json_body()
            if data is None:
                return
            self._api_jumpstart_find_card(data)
        elif path == "/api/jumpstart/insert-deck":
            data = self._read_json_body()
            if data is None:
                return
            self._api_jumpstart_insert_deck(data)
        elif path == "/api/jumpstart/printings-by-name":
            data = self._read_json_body()
            if data is None:
                return
            self._api_jumpstart_printings_by_name(data)
        elif path == "/api/jumpstart/sql-search":
            data = self._read_json_body()
            if data is None:
                return
            self._api_jumpstart_sql_search(data)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/settings":
            self._api_put_settings()
        elif path.startswith("/api/deck-builder/") and path.endswith("/plan"):
            did = path[len("/api/deck-builder/"):-len("/plan")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_save_plan(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/sealed/collection/"):
            entry_id = path[len("/api/sealed/collection/"):]
            data = self._read_json_body()
            if data is None:
                return
            self._api_sealed_collection_update(int(entry_id), data)
        elif path.startswith("/api/orders/"):
            oid = path[len("/api/orders/"):]
            if oid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_order_update(int(oid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/collection/"):
            entry_id = path[len("/api/collection/"):]
            if entry_id.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_collection_update(int(entry_id), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/"):
            did = path[len("/api/decks/"):]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_update(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/binders/"):
            bid = path[len("/api/binders/"):]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_binder_update(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/views/"):
            vid = path[len("/api/views/"):]
            if vid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_view_update(int(vid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path.startswith("/api/sealed/collection/"):
            entry_id = path[len("/api/sealed/collection/"):]
            confirm = params.get("confirm", [""])[0]
            if confirm != "true":
                self._send_json({"error": "Must pass ?confirm=true"}, 400)
                return
            self._api_sealed_collection_delete(int(entry_id))
        elif path.startswith("/api/collection/") and not path.startswith("/api/collection/bulk"):
            entry_id = path[len("/api/collection/"):]
            confirm = params.get("confirm", [""])[0]
            if confirm != "true":
                self._send_json({"error": "Must pass ?confirm=true"}, 400)
                return
            self._api_collection_delete(int(entry_id))
        elif path.startswith("/api/wishlist/"):
            wid = path[len("/api/wishlist/"):]
            self._api_wishlist_delete(int(wid))
        elif path.startswith("/api/deck-builder/") and path.endswith("/cards"):
            did = path[len("/api/deck-builder/"):-len("/cards")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_builder_remove_card(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/") and path.endswith("/cards"):
            did = path[len("/api/decks/"):-len("/cards")]
            if did.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_deck_remove_cards(int(did), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/decks/"):
            did = path[len("/api/decks/"):]
            if did.isdigit():
                self._api_deck_delete(int(did))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/binders/") and path.endswith("/cards"):
            bid = path[len("/api/binders/"):-len("/cards")]
            if bid.isdigit():
                data = self._read_json_body()
                if data is None:
                    return
                self._api_binder_remove_cards(int(bid), data)
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/binders/"):
            bid = path[len("/api/binders/"):]
            if bid.isdigit():
                self._api_binder_delete(int(bid))
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.startswith("/api/views/"):
            vid = path[len("/api/views/"):]
            if vid.isdigit():
                self._api_view_delete(int(vid))
            else:
                self._send_json({"error": "Not found"}, 404)
        else:
            self._send_json({"error": "Not found"}, 404)

    _CONTENT_TYPES = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".ico": "image/x-icon",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
        ".svg": "image/svg+xml",
    }

    def _serve_page(self, route: PageRoute):
        """Serve one page from the route table (see cli/page_routes.py)."""
        if route.init_data is None:
            self._serve_static(route.template)
        else:
            self._serve_static_with_data(route.template, getattr(self, route.init_data))

    def _respond(self, body: bytes, content_type: str, cache_control: str, *,
                 status: int = 200, ranges: bool = False):
        """The one way a body leaves this server (de-dai).

        Every caller names what the response IS -- a document, a
        content-addressed asset, an API payload -- and the caching rules follow
        from that.  Nobody passes a Cache-Control string any more, because the
        bug this replaces was a correct-looking string at the wrong call site.

        Handles, in order: conditional revalidation (If-None-Match -> 304), byte
        ranges, then content encoding.  A Range request forces identity so the
        range is always a range of the representation whose ETag we quote.
        """
        # A Range request forces identity: the range must be a range of the
        # representation whose ETag we quote, and the compressed one has a
        # different ETag by construction.
        ranging = status == 200 and ranges and bool(self.headers.get("Range"))
        encoding = None
        if not ranging and negotiate_gzip(
                self.headers.get("Accept-Encoding"), content_type, len(body)):
            encoding = "gzip"

        etag = compute_etag(body, encoding=encoding) if status == 200 else None

        def _common_headers():
            self.send_header("Cache-Control", cache_control)
            self.send_header("Vary", "Accept-Encoding")
            if etag:
                self.send_header("ETag", etag)

        if etag and etag_matches(self.headers.get("If-None-Match"), etag):
            # No body, and no Content-Length: a 304 describes a response the
            # client already holds, so quoting a length here would describe
            # bytes that are not on the wire.
            self.send_response(304)
            _common_headers()
            self.end_headers()
            return

        if encoding == "gzip":
            body = gzip.compress(body)

        if ranging:
            try:
                span = parse_range(self.headers.get("Range"), len(body))
            except RangeNotSatisfiable:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(body)}")
                self.send_header("Content-Length", "0")
                _common_headers()
                self.end_headers()
                return
            if span:
                start, end = span
                chunk = body[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                _common_headers()
                self.end_headers()
                self.wfile.write(chunk)
                return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        elif ranges:
            # Advertised only on identity responses.  A client that ranged a
            # gzipped representation would be quoting an ETag we never minted.
            self.send_header("Accept-Ranges", "bytes")
        _common_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, filename: str):
        filepath = self.static_dir / filename
        if not filepath.resolve().is_relative_to(self.static_dir.resolve()):
            self._send_json({"error": "Not found"}, 404)
            return
        if not filepath.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        content = filepath.read_bytes()
        content_type = self._CONTENT_TYPES.get(filepath.suffix, "application/octet-stream")
        self._respond(content, content_type, CACHE_DOCUMENT, ranges=True)

    def _serve_static_with_data(self, filename: str, data_fn):
        """Serve a static HTML file with /*INIT_DATA*/ replaced by JSON."""
        import json as _json
        filepath = self.static_dir / filename
        if not filepath.resolve().is_relative_to(self.static_dir.resolve()):
            self._send_json({"error": "Not found"}, 404)
            return
        if not filepath.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        html = filepath.read_text(encoding="utf-8")
        html = html.replace("/*INIT_DATA*/", _json.dumps(data_fn()))
        self._respond(html.encode("utf-8"), "text/html; charset=utf-8", CACHE_DOCUMENT)

    def _decks_init_data(self):
        from mtg_collector.db.models import DeckRepository
        conn = self._get_conn()
        data = DeckRepository(conn).list_all()
        conn.close()
        return data

    def _api_sets(self):
        """Sets that have MTGJSON **booster data** — not every set that exists.

        `PackGenerator.list_sets()` reads `mtgjson_booster_configs`, so a set
        with no booster config is silently absent: Commander decks, Secret
        Lairs, Jumpstart-style products, most supplemental releases. That is
        correct for the two callers, which both need a set you can open a pack
        from — `crack_pack.html:812` (/crack) and `explore_sheets.html:488`
        (/sheets). Both would break on a rename, which is why this endpoint
        kept its path when `/api/sets/index` was added under it.

        For "every set the app has cards for", use `/api/sets/index` (whole
        rows, completion counts) or `/api/cached-sets` (code + name only).
        Neither goes through MTGJSON booster data.
        """
        if not self.generator:
            self._send_json({"error": "AllPrintings.json not loaded — run: mtg data fetch"}, 503)
            return
        sets = self.generator.list_sets()
        self._send_json([{"code": code, "name": name} for code, name in sets])

    def _api_sets_index(self):
        """Every locally cached set with its completion counts, newest first.

        Backs the `/sets` page. Unpaginated: 993 sets qualify in prod and the
        set count is small and bounded, unlike collection rows.

        The population is `cards_fetched_at IS NOT NULL`, *not* `/api/sets` —
        that one is booster-data-only and drops any set without a booster
        config, which is most of what a binder holds.

        The query does no per-set work; see `db/set_index.py` for why that is
        load-bearing (21,460 ms as correlated subqueries, 39 ms aggregated
        once and joined).
        """
        from mtg_collector.db import set_index

        conn = self._get_conn()
        try:
            rows = set_index.set_index(conn)
        finally:
            conn.close()
        self._send_json(rows)

    def _api_cached_sets(self):
        """Return all sets whose card list has been fully cached."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT set_code, set_name FROM sets WHERE cards_fetched_at IS NOT NULL ORDER BY set_name"
        )
        result = [{"code": row["set_code"], "name": row["set_name"]} for row in cursor]
        conn.close()
        self._send_json(result)

    def _api_search_suggest(self, params: dict):
        """Return autocomplete suggestions for a search keyword's value.

        Restricted to the user's actual collection corpus — suggestions only
        include values present on printings the user owns. Free-text keys
        (oracle, flavor) aren't supported because suggesting substrings
        from those isn't useful.
        """
        key = params.get("key", [""])[0].lower().strip()
        prefix = params.get("prefix", [""])[0].strip()
        limit = 12

        conn = self._get_conn()
        suggestions: list = []

        if key == "added":
            aliases = [
                ("today",     "today",     "Today (local)"),
                ("yesterday", "yesterday", "Yesterday (local)"),
                ("7d",        "7d",        "7 days ago"),
                ("30d",       "30d",       "30 days ago"),
                ("90d",       "90d",       "90 days ago"),
                ("1y",        "1y",        "1 year ago"),
            ]
            plow = prefix.lower()
            for value, label, hint in aliases:
                if not prefix or value.startswith(plow):
                    suggestions.append({"value": value, "label": label, "hint": hint})
            for row in conn.execute(
                "SELECT DISTINCT SUBSTR(acquired_at, 1, 4) AS y FROM collection "
                "WHERE acquired_at IS NOT NULL ORDER BY y DESC"
            ):
                y = row["y"]
                if y and (not prefix or y.startswith(prefix)):
                    suggestions.append({"value": y, "label": y, "hint": "Year"})
            for row in conn.execute(
                "SELECT DISTINCT SUBSTR(acquired_at, 1, 7) AS ym FROM collection "
                "WHERE acquired_at IS NOT NULL ORDER BY ym DESC LIMIT 36"
            ):
                ym = row["ym"]
                if ym and (not prefix or ym.startswith(prefix)):
                    suggestions.append({"value": ym, "label": ym, "hint": "Month"})

        elif key in ("artist", "a"):
            like = f"%{prefix}%"
            for row in conn.execute(
                "SELECT DISTINCT p.artist FROM printings p "
                "INNER JOIN collection c ON c.printing_id = p.printing_id "
                "WHERE p.artist IS NOT NULL AND p.artist LIKE ? COLLATE NOCASE "
                "ORDER BY p.artist LIMIT ?",
                (like, limit),
            ):
                artist = row[0]
                # Wrap in quotes if the artist name has whitespace.
                value = f'"{artist}"' if " " in artist else artist
                suggestions.append({"value": value, "label": artist, "hint": "Artist"})

        elif key in ("keyword", "kw"):
            like = f"%{prefix}%"
            for row in conn.execute(
                "SELECT DISTINCT je.value AS kw FROM cards card "
                "INNER JOIN printings p ON p.oracle_id = card.oracle_id "
                "INNER JOIN collection c ON c.printing_id = p.printing_id, "
                "json_each(card.keywords) je "
                "WHERE card.keywords IS NOT NULL AND card.keywords != '[]' "
                "AND je.value LIKE ? COLLATE NOCASE "
                "ORDER BY kw LIMIT ?",
                (like, limit),
            ):
                kw = row["kw"]
                value = f'"{kw}"' if " " in kw else kw
                suggestions.append({"value": value, "label": kw, "hint": "Keyword"})

        elif key == "set":
            like = f"%{prefix}%"
            plow = prefix.lower()
            for row in conn.execute(
                "SELECT DISTINCT p.set_code, s.set_name FROM printings p "
                "INNER JOIN collection c ON c.printing_id = p.printing_id "
                "LEFT JOIN sets s ON s.set_code = p.set_code "
                "WHERE p.set_code LIKE ? OR s.set_name LIKE ? COLLATE NOCASE "
                "ORDER BY s.set_name LIMIT ?",
                (like, like, limit),
            ):
                code = (row["set_code"] or "").lower()
                if not code or (prefix and not code.startswith(plow) and plow not in (row["set_name"] or "").lower()):
                    continue
                suggestions.append({"value": code, "label": code.upper(),
                                    "hint": row["set_name"] or ""})

        elif key == "deck":
            like = f"%{prefix}%"
            for row in conn.execute(
                "SELECT id, name FROM decks WHERE name LIKE ? COLLATE NOCASE "
                "ORDER BY name LIMIT ?",
                (like, limit),
            ):
                name = row["name"] or ""
                value = f'"{name}"' if " " in name else name
                suggestions.append({"value": value, "label": name, "hint": "Deck"})

        elif key == "binder":
            like = f"%{prefix}%"
            for row in conn.execute(
                "SELECT id, name FROM binders WHERE name LIKE ? COLLATE NOCASE "
                "ORDER BY name LIMIT ?",
                (like, limit),
            ):
                name = row["name"] or ""
                value = f'"{name}"' if " " in name else name
                suggestions.append({"value": value, "label": name, "hint": "Binder"})

        conn.close()
        self._send_json(suggestions[:limit])

    def _api_products(self, set_code: str):
        if not self.generator:
            self._send_json({"error": "AllPrintings.json not loaded — run: mtg data fetch"}, 503)
            return
        if not set_code:
            self._send_json({"error": "Missing 'set' parameter"}, 400)
            return
        products = self.generator.list_products(set_code)
        self._send_json(products)

    def _api_sheets(self, set_code: str, product: str):
        if not self.generator:
            self._send_json({"error": "AllPrintings.json not loaded — run: mtg data fetch"}, 503)
            return
        if not set_code or not product:
            self._send_json({"error": "Missing 'set' or 'product' parameter"}, 400)
            return
        result = self.generator.get_sheet_data(set_code, product)

        # Batch-attach prices from SQLite (single query instead of per-card)
        conn = self._get_conn()
        all_cards = [c for sheet in result["sheets"].values() for c in sheet["cards"]]
        _bulk_attach_prices(conn, all_cards)
        conn.close()

        self._send_json(result)

    def _api_generate(self, data: dict):
        if not self.generator:
            self._send_json({"error": "AllPrintings.json not loaded — run: mtg data fetch"}, 503)
            return
        set_code = data.get("set_code", "")
        product = data.get("product", "")
        if not set_code or not product:
            self._send_json({"error": "Missing set_code or product"}, 400)
            return
        seed = data.get("seed")
        if seed is not None:
            seed = int(seed)
        result = self.generator.generate_pack(set_code, product, seed=seed)

        # Batch-attach prices from local DB (single query)
        conn = self._get_conn()
        _bulk_attach_prices(conn, result["cards"])
        conn.close()

        self._send_json(result)

    def _api_collection(self, params: dict):
        """Return aggregated collection data with Scryfall-style search.

        The `q` param accepts full Scryfall query syntax plus collection
        extensions (status:, added:, price:, deck:, binder:, is:wanted, etc.).
        When no status: is in the query, defaults to status:owned.
        """
        from mtg_collector.search import SearchError, compile_query, parse_query

        try:
            limit, offset = _parse_page_params(params)
        except PageParamError as e:
            self._send_json({"error": str(e)}, 400)
            return

        q = params.get("q", [""])[0]
        sort = params.get("sort", [""])[0]
        order = params.get("order", [""])[0]
        expand_copies = params.get("expand", [""])[0] == "copies"

        # Explicit card list: ?cards=set:cn,set:cn,... (shared links)
        cards_param = params.get("cards", [""])[0]
        card_pairs = []
        if cards_param:
            for entry in cards_param.split(","):
                entry = entry.strip()
                if ":" in entry:
                    sc, cn = entry.split(":", 1)
                    card_pairs.append((sc.lower(), cn))

        conn = self._get_conn()

        # Parse and compile the Scryfall query
        tz = params.get("tz", [""])[0] or None
        where_sql = "1=1"
        sql_params: list = []
        compiled = None
        if q:
            try:
                ast = parse_query(q)
                compiled = compile_query(ast, tz=tz)
                where_sql = compiled.where_sql
                sql_params = list(compiled.params)
            except SearchError as e:
                self._send_json({"error": str(e), "position": e.position}, 400)
                return

        # is:unowned flips to the LEFT-JOIN template so cards not in the
        # collection can appear in results.
        include_unowned = bool(compiled and compiled.include_unowned)

        # Status default: owned (unless query has explicit status: filter)
        has_status = compiled and compiled.has_status_filter
        if not has_status and not card_pairs and not include_unowned:
            if where_sql == "1=1":
                where_sql = "c.status IN ('owned', 'ordered')"
            else:
                where_sql = f"c.status IN ('owned', 'ordered') AND ({where_sql})"

        # Explicit card list filter (shared links)
        if card_pairs:
            pair_clauses = []
            for sc, cn in card_pairs:
                pair_clauses.append("(p.set_code = ? AND p.collector_number = ?)")
                sql_params.extend([sc, cn])
            card_filter = f"({' OR '.join(pair_clauses)})"
            where_sql = f"{card_filter} AND ({where_sql})" if where_sql != "1=1" else card_filter

        # The price column the client renders follows the price_sources
        # setting, so sorting and the totals below follow it too — otherwise
        # the table would order itself by a number it is not showing.
        price_sources_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'price_sources'"
        ).fetchone()
        first_source = (
            price_sources_row["value"] if price_sources_row else "tcg,ck"
        ).split(",")[0]
        _CK_PRICE_SQL = "COALESCE(_ck_buy.price, _ck_retail.price)"
        _TCG_PRICE_SQL = "_tcg.price"
        display_price_sql = _CK_PRICE_SQL if first_source == "ck" else _TCG_PRICE_SQL

        # Sort: use search engine order:/direction: if present, else URL params.
        # No sort_map value is unique, and neither is the card.name tiebreak
        # (~3.2 printings share a name), so every template below closes its
        # ORDER BY with the columns that identify one output row — the GROUP BY
        # key where there is one, c.id/dc.id for the per-copy template. Without
        # that the order is not total and paged responses drop and duplicate rows.
        sort_map = {
            # p.card_name, not card.name — same value (it is denormalised from
            # it), but on the table the grouped templates already drive from, so
            # idx_printings_card_name(card_name, printing_id) can serve the sort.
            # Reading it across the join cannot be made fast: GROUP BY
            # p.printing_id pins printings as the driving table, so cards can
            # never be the outer loop and idx_cards_name is never reachable for
            # ordering. Measured on 109,976 rows: 2.3 s -> 8.8 ms.
            "name": "p.card_name",
            "cmc": "card.cmc",
            "rarity": "CASE p.rarity WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1 WHEN 'rare' THEN 2 WHEN 'mythic' THEN 3 ELSE 4 END",
            "set": "p.set_code",
            "color": "card.color_identity",
            "qty": "qty",
            "collector_number": "CAST(p.collector_number AS INTEGER)",
            "date_added": "c.acquired_at",
            "added": "c.acquired_at",
            # These three are expressions from _ENRICH_COLUMNS, whose joins are
            # unconditional and single-row, so they need no needs_*_join flag.
            #
            # `price` deliberately does NOT use _lp. That join pins price_type
            # but not source, and latest_prices' key is (set_code,
            # collector_number, source, price_type) — so with both a TCG and a
            # Card Kingdom price it matches twice. The GROUP BY templates hide
            # that by collapsing the duplicate (while making which source you
            # sorted by a coin toss), but expand=copies has no GROUP BY, and
            # paging a result with duplicated rows drops and repeats cards.
            # Nothing sent `sort` before the client began paging, so this was
            # unreachable rather than fixed.
            "price": display_price_sql,
            "tcg_price": _TCG_PRICE_SQL,
            "ck_price": _CK_PRICE_SQL,
        }
        if compiled and compiled.order_by:
            sort_col = sort_map.get(compiled.order_by, "p.card_name")
        else:
            sort_col = sort_map.get(sort, "p.card_name")
        if compiled and compiled.order_dir == "desc":
            order_dir = "DESC"
        elif order:
            order_dir = "DESC" if order == "desc" else "ASC"
        else:
            order_dir = "ASC"

        sorting_by_name = sort_col == "p.card_name"

        def _order_by(*identity_cols: str) -> str:
            """ORDER BY for a template, given the columns that identify one row.

            The identity columns follow order_dir rather than being pinned ASC.
            An index can only be read backwards when every term inverts
            together, so `p.card_name DESC, p.printing_id ASC` falls back to a
            full sort — measured 4.3 s against 10 ms for `... DESC, ... DESC`.
            The direction of a tiebreak is arbitrary either way; it is there to
            make the order total, and it is equally total in either direction.

            The name is added as a secondary sort only when it is not already
            the primary. Repeating it would break the index prefix for nothing.
            """
            terms = [f"{sort_col} {order_dir}"]
            if not sorting_by_name:
                terms.append(f"p.card_name {order_dir}")
            terms.extend(f"{col} {order_dir}" for col in identity_cols)
            return "ORDER BY " + ", ".join(terms)

        def _group_by(*key_cols: str) -> str:
            """GROUP BY for a template, given its row-identity key.

            When the sort is by name, the sort column leads the grouping. That
            is a no-op semantically — printing_id is the primary key and so
            functionally determines card_name, meaning the finer key groups
            exactly the same rows — but it is what lets one scan of
            idx_printings_card_name satisfy the grouping and the ordering at
            once. Denormalising without this measured no better than not
            denormalising at all (2.4 s vs 2.7 s); with it, 8.8 ms.
            """
            cols = list(key_cols)
            if sorting_by_name:
                cols.insert(0, "p.card_name")
            return "GROUP BY " + ", ".join(cols)

        # Conditional JOINs from the search engine
        # Note: expand_copies and default templates already include dc/d/b joins.
        # Only the shared-links (card_pairs) template needs them dynamically.
        # _lp now serves only the search engine's `price:` keyword — no sort
        # resolves to it any more, so sorting no longer drags in a join that
        # can match a card twice.
        needs_price_join = compiled and compiled.needs_price_join
        needs_wishlist_join = compiled and compiled.needs_wishlist_join

        def _build_extra_joins(*, has_deck_binder_joins: bool, enrich: str = "full") -> str:
            """enrich: "full" for the page, "prices" for the totals, "none" for the count."""
            joins = []
            if not has_deck_binder_joins:
                if compiled and compiled.needs_deck_join:
                    joins.append("LEFT JOIN deck_cards dc ON dc.collection_id = c.id")
                    joins.append("LEFT JOIN decks d ON dc.deck_id = d.id")
                if compiled and "b.name" in (compiled.where_sql or ""):
                    joins.append("LEFT JOIN binders b ON c.binder_id = b.id")
            if needs_price_join:
                # price_type follows the copy's actual finish so foil copies sort
                # by their foil price, not the nonfoil price. Etched uses foil.
                joins.append(
                    "LEFT JOIN latest_prices _lp ON _lp.set_code = p.set_code"
                    " AND _lp.collector_number = p.collector_number"
                    " AND _lp.price_type = CASE WHEN c.finish IN ('foil', 'etched') THEN 'foil' ELSE 'normal' END"
                )
            if needs_wishlist_join:
                joins.append(
                    "LEFT JOIN wishlist _wl ON _wl.oracle_id = card.oracle_id AND _wl.fulfilled_at IS NULL"
                )
            if enrich == "full":
                joins.extend(_ENRICH_JOINS)
            elif enrich == "prices":
                # The totals need a price per row and nothing else. Dropping the
                # ck_url join drops its correlated scalar subquery, which runs
                # once per row of the whole result: 2.6 s -> 1.0 s on 109,976.
                joins.extend(_ENRICH_PRICE_JOINS)
            return "\n                ".join(joins)

        if card_pairs or include_unowned:
            # LEFT JOIN template: shared-link cards or is:unowned queries
            select_sql = f"""
                SELECT
                    card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                    card.colors, card.color_identity,
                    p.set_code, s.set_name, p.collector_number, p.rarity,
                    p.printing_id, p.image_uri, p.artist,
                    p.frame_effects, p.border_color, p.full_art, p.promo,
                    p.promo_types, p.finishes,
                    p.flavor_name,
                    p.layout,
                    p.face0_mana_cost as face0_mana,
                    p.face1_mana_cost as face1_mana,
                    c.finish, c.condition, c.status,
                    COALESCE(COUNT(DISTINCT c.id), 0) as qty,
                    MAX(c.acquired_at) as acquired_at,
                    CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as owned,
                    c.order_id,
                    o.seller_name as order_seller,
                    o.order_number as order_number,
                    o.order_date as order_date,
                    c.purchase_price,
                    {_ENRICH_COLUMNS}
            """
            def _body(joins: str) -> str:
                return f"""
                FROM printings p
                JOIN cards card ON p.oracle_id = card.oracle_id
                JOIN sets s ON p.set_code = s.set_code
                LEFT JOIN collection c ON p.printing_id = c.printing_id
                LEFT JOIN orders o ON c.order_id = o.id
                {joins}
                WHERE {where_sql}
                {_group_by("p.printing_id")}
            """
            body_sql = _body(_build_extra_joins(has_deck_binder_joins=False))
            count_body_sql = _body(_build_extra_joins(has_deck_binder_joins=False, enrich="none"))
            totals_body_sql = _body(_build_extra_joins(has_deck_binder_joins=False, enrich="prices"))
            order_sql = _order_by("p.printing_id")
            agg_qty_sql = "COALESCE(COUNT(DISTINCT c.id), 0)"
        elif expand_copies:
            # One row per collection entry (for deck builder picker)
            select_sql = f"""
                SELECT
                    card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                    card.colors, card.color_identity,
                    p.set_code, s.set_name, p.collector_number, p.rarity,
                    p.printing_id, p.image_uri, p.artist,
                    p.frame_effects, p.border_color, p.full_art, p.promo,
                    p.promo_types, p.finishes,
                    p.flavor_name,
                    p.layout,
                    p.face0_mana_cost as face0_mana,
                    p.face1_mana_cost as face1_mana,
                    c.finish, c.condition, c.status,
                    c.id as collection_id,
                    1 as qty,
                    c.acquired_at,
                    c.order_id,
                    o.seller_name as order_seller,
                    o.order_number as order_number,
                    o.order_date as order_date,
                    c.purchase_price,
                    dc.deck_id, dc.zone as deck_zone, c.binder_id,
                    d.name as deck_name,
                    b.name as binder_name,
                    {_ENRICH_COLUMNS}
            """
            def _body(joins: str) -> str:
                return f"""
                FROM collection c
                JOIN printings p ON c.printing_id = p.printing_id
                JOIN cards card ON p.oracle_id = card.oracle_id
                JOIN sets s ON p.set_code = s.set_code
                LEFT JOIN orders o ON c.order_id = o.id
                LEFT JOIN deck_cards dc ON dc.collection_id = c.id
                LEFT JOIN decks d ON dc.deck_id = d.id
                LEFT JOIN binders b ON c.binder_id = b.id
                {joins}
                WHERE {where_sql}
            """
            body_sql = _body(_build_extra_joins(has_deck_binder_joins=True))
            count_body_sql = _body(_build_extra_joins(has_deck_binder_joins=True, enrich="none"))
            totals_body_sql = _body(_build_extra_joins(has_deck_binder_joins=True, enrich="prices"))
            # No GROUP BY on this template: one row per collection entry, so
            # c.id (plus dc.id, which the deck join can duplicate it by) is what
            # identifies a row.
            order_sql = _order_by("p.printing_id", "c.id", "dc.id")
            agg_qty_sql = "1"
        else:
            # Default: aggregated, one row per (printing, finish, condition, status)
            select_sql = f"""
                SELECT
                    card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                    card.colors, card.color_identity,
                    p.set_code, s.set_name, p.collector_number, p.rarity,
                    p.printing_id, p.image_uri, p.artist,
                    p.frame_effects, p.border_color, p.full_art, p.promo,
                    p.promo_types, p.finishes,
                    p.flavor_name,
                    p.layout,
                    p.face0_mana_cost as face0_mana,
                    p.face1_mana_cost as face1_mana,
                    c.finish, c.condition, c.status,
                    COUNT(DISTINCT c.id) as qty,
                    MAX(c.acquired_at) as acquired_at,
                    c.order_id,
                    o.seller_name as order_seller,
                    o.order_number as order_number,
                    o.order_date as order_date,
                    c.purchase_price,
                    dc.deck_id, dc.zone as deck_zone, c.binder_id,
                    d.name as deck_name,
                    b.name as binder_name,
                    {_ENRICH_COLUMNS}
            """
            def _body(joins: str) -> str:
                return f"""
                FROM collection c
                JOIN printings p ON c.printing_id = p.printing_id
                JOIN cards card ON p.oracle_id = card.oracle_id
                JOIN sets s ON p.set_code = s.set_code
                LEFT JOIN orders o ON c.order_id = o.id
                LEFT JOIN deck_cards dc ON dc.collection_id = c.id
                LEFT JOIN decks d ON dc.deck_id = d.id
                LEFT JOIN binders b ON c.binder_id = b.id
                {joins}
                WHERE {where_sql}
                {_group_by("p.printing_id", "c.finish", "c.condition", "c.status", "c.order_id")}
            """
            body_sql = _body(_build_extra_joins(has_deck_binder_joins=True))
            count_body_sql = _body(_build_extra_joins(has_deck_binder_joins=True, enrich="none"))
            totals_body_sql = _body(_build_extra_joins(has_deck_binder_joins=True, enrich="prices"))
            order_sql = _order_by(
                "p.printing_id", "c.finish", "c.condition", "c.status", "c.order_id"
            )
            agg_qty_sql = "COUNT(DISTINCT c.id)"

        # order_sql stays per-template: the tiebreak is that template's row
        # identity, and it differs (the GROUP BY key, or c.id/dc.id per copy).
        # It is kept out of body_sql so the COUNT below does not sort.
        #
        # LIMIT/OFFSET are bound parameters, never formatted into the SQL.
        cursor = conn.execute(
            f"{select_sql}{body_sql}{order_sql} LIMIT ? OFFSET ?",
            [*sql_params, limit, offset],
        )
        rows = cursor.fetchall()

        # A short page has already answered how big the result is: the query ran
        # out of rows, so the result ends here. That covers every query whose
        # result fits in one page — which is most of them — for no extra query
        # at all. (Not when the page is empty and the offset is past the end:
        # then the offset says nothing about where the result stopped.)
        short_page = len(rows) < limit and (rows or offset == 0)

        include_unowned = bool(card_pairs) or include_unowned
        results = []
        for row in rows:
            mana_cost = row["mana_cost"]
            if not mana_cost:
                face0 = row["face0_mana"] or ""
                face1 = row["face1_mana"] or ""
                if face0 or face1:
                    mana_cost = " // ".join(p for p in [face0, face1] if p)
            card = {
                "oracle_id": row["oracle_id"],
                "name": row["flavor_name"] or row["name"],
                "oracle_name": row["name"] if row["flavor_name"] and row["flavor_name"] != row["name"] else None,
                "type_line": row["type_line"],
                "mana_cost": mana_cost,
                "cmc": row["cmc"],
                "colors": row["colors"],
                "color_identity": row["color_identity"],
                "set_code": row["set_code"],
                "set_name": row["set_name"],
                "collector_number": row["collector_number"],
                "rarity": row["rarity"],
                "printing_id": row["printing_id"],
                "image_uri": row["image_uri"],
                "artist": row["artist"],
                "frame_effects": row["frame_effects"],
                "border_color": row["border_color"],
                "full_art": bool(row["full_art"]),
                "promo": bool(row["promo"]),
                "promo_types": row["promo_types"],
                "finishes": row["finishes"],
                "layout": row["layout"] or "normal",
                "finish": row["finish"],
                "condition": row["condition"],
                "status": row["status"],
                "qty": row["qty"],
                "acquired_at": row["acquired_at"],
                "owned": bool(row["owned"]) if include_unowned else True,
            }
            if "collection_id" in row.keys():
                card["collection_id"] = row["collection_id"]
            # Deck/binder info
            if "deck_id" in row.keys() and row["deck_id"]:
                card["deck_id"] = row["deck_id"]
                card["deck_zone"] = row["deck_zone"]
                card["deck_name"] = row["deck_name"]
            if "binder_id" in row.keys() and row["binder_id"]:
                card["binder_id"] = row["binder_id"]
                card["binder_name"] = row["binder_name"]
            # Order info
            order_id = row["order_id"] if "order_id" in row.keys() else None
            if order_id:
                card["order_id"] = order_id
                card["order_seller"] = row["order_seller"]
                card["order_number"] = row["order_number"]
                card["order_date"] = row["order_date"]
                card["purchase_price"] = row["purchase_price"]
            # Prices and ck_url come from the main query's enrichment joins
            # (_ENRICH_COLUMNS); the JSON payload has always carried prices as
            # strings, so keep formatting them here rather than in SQL.
            card["tcg_price"] = None if row["tcg_price"] is None else str(row["tcg_price"])
            card["ck_price"] = None if row["ck_price"] is None else str(row["ck_price"])
            card["ck_url"] = row["ck_url"]
            results.append(card)

        # total, total_qty and total_value all describe the whole result rather
        # than the page, and none of them can be summed from the page: the client
        # fetches windows as it scrolls, so a page-scoped aggregate would climb
        # as the user scrolled — a collection value that grows while you look at
        # it is worse than none. Priced the same way the table is
        # (display_price_sql), so the status line agrees with the price column
        # beside it.
        #
        # total_qty/total_value are computed on the first window only (de-962).
        # They describe the result, not the window, so every later window used to
        # recompute a number the client already had — measured at 1.0 s of the
        # 1.5 s a scroll fetch cost once the page query itself was fixed. The
        # value on screen still never moves, because the client reads them once
        # and keeps them; the keys are simply absent from later windows rather
        # than being present and stale.
        #
        # `total` is on every window: deck-builder.js pages the card picker until
        # `offset >= total`, so dropping it there would turn its loop into a
        # fixed-cap scan.
        totals_in_hand = short_page and offset == 0
        price_key = "ck_price" if first_source == "ck" else "tcg_price"
        aggregates = {}

        if totals_in_hand:
            # The page is the whole result, so the rows in hand are the answer.
            total = len(results)
            aggregates["total_qty"] = sum(c.get("qty") or 0 for c in results)
            aggregates["total_value"] = round(sum(
                float(c[price_key] or 0) * (c.get("qty") or 0) for c in results
            ), 2)
        elif offset == 0:
            # One scan for all three. Counting and summing separately walked the
            # same grouped body twice: 1.4 s against 1.0 s for this, same answer.
            agg = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(qty), 0), COALESCE(SUM(qty * price), 0) FROM ("
                f"SELECT {agg_qty_sql} as qty, {display_price_sql} as price {totals_body_sql})",
                sql_params,
            ).fetchone()
            total = agg[0]
            aggregates["total_qty"] = agg[1]
            aggregates["total_value"] = round(agg[2], 2)
        elif short_page:
            total = offset + len(rows)
        else:
            # Count the body, which carries the GROUP BY and so counts groups,
            # matching what the page returns. The enrichment joins are left out:
            # a COUNT has no columns to enrich, and each of them matches at most
            # one row, so they cannot change the count either.
            total = conn.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 {count_body_sql})", sql_params
            ).fetchone()[0]

        conn.close()
        self._send_json(
            {
                "rows": results,
                "total": total,
                **aggregates,
                "limit": limit,
                "offset": offset,
            }
        )

    def _api_card(self, printing_id: str):
        """Return full card data for a single printing by printing_id."""
        conn = self._get_conn()

        row = conn.execute(
            """
            SELECT
                card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                card.colors, card.color_identity,
                p.set_code, s.set_name, p.collector_number, p.rarity,
                p.printing_id, p.image_uri, p.artist,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes,
                p.flavor_name,
                p.layout,
                p.face0_mana_cost as face0_mana,
                p.face1_mana_cost as face1_mana
            FROM printings p
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            WHERE p.printing_id = ?
            """,
            (printing_id,),
        ).fetchone()

        if not row:
            conn.close()
            self._send_json({"error": "Card not found"}, 404)
            return

        mana_cost = row["mana_cost"]
        if not mana_cost:
            face0 = row["face0_mana"] or ""
            face1 = row["face1_mana"] or ""
            if face0 or face1:
                mana_cost = " // ".join(p for p in [face0, face1] if p)

        result = {
            "oracle_id": row["oracle_id"],
            "name": row["flavor_name"] or row["name"],
            "oracle_name": row["name"] if row["flavor_name"] and row["flavor_name"] != row["name"] else None,
            "type_line": row["type_line"],
            "mana_cost": mana_cost,
            "cmc": row["cmc"],
            "colors": row["colors"],
            "color_identity": row["color_identity"],
            "set_code": row["set_code"],
            "set_name": row["set_name"],
            "collector_number": row["collector_number"],
            "rarity": row["rarity"],
            "printing_id": row["printing_id"],
            "image_uri": row["image_uri"],
            "artist": row["artist"],
            "frame_effects": row["frame_effects"],
            "border_color": row["border_color"],
            "full_art": bool(row["full_art"]),
            "promo": bool(row["promo"]),
            "promo_types": row["promo_types"],
            "finishes": row["finishes"],
            "layout": row["layout"] or "normal",
        }

        # Prices from SQLite
        sc = row["set_code"].lower()
        cn = row["collector_number"]
        finishes = json.loads(row["finishes"]) if row["finishes"] else []
        foil_only = "nonfoil" not in finishes
        price_type = "foil" if foil_only else "normal"
        result["ck_price"] = _get_sqlite_price(self.db_path, sc, cn, "cardkingdom", f"buylist_{price_type}") or _get_sqlite_price(self.db_path, sc, cn, "cardkingdom", price_type)
        result["tcg_price"] = _get_sqlite_price(self.db_path, sc, cn, "tcgplayer", price_type)
        result["ck_url"] = self.generator.get_ck_url(printing_id, foil_only) if self.generator else ""

        conn.close()
        self._send_json(result)

    def _api_card_by_set_cn(self, params):
        """Return full card data for a printing looked up by set_code + collector_number."""
        set_code = params.get("set", [""])[0].lower()
        cn = params.get("cn", [""])[0]
        if not set_code or not cn:
            self._send_json({"error": "Missing set or cn parameter"}, 400)
            return

        conn = self._get_conn()

        row = conn.execute(
            """
            SELECT
                card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                card.colors, card.color_identity,
                p.set_code, s.set_name, p.collector_number, p.rarity,
                p.printing_id, p.image_uri, p.artist,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes,
                p.flavor_name,
                p.layout,
                p.face0_mana_cost as face0_mana,
                p.face1_mana_cost as face1_mana
            FROM printings p
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            WHERE p.set_code = ? AND p.collector_number = ?
            """,
            (set_code, cn),
        ).fetchone()

        if not row:
            conn.close()
            self._send_json({"error": "Card not found"}, 404)
            return

        mana_cost = row["mana_cost"]
        if not mana_cost:
            face0 = row["face0_mana"] or ""
            face1 = row["face1_mana"] or ""
            if face0 or face1:
                mana_cost = " // ".join(p for p in [face0, face1] if p)

        result = {
            "oracle_id": row["oracle_id"],
            "name": row["flavor_name"] or row["name"],
            "oracle_name": row["name"] if row["flavor_name"] and row["flavor_name"] != row["name"] else None,
            "type_line": row["type_line"],
            "mana_cost": mana_cost,
            "cmc": row["cmc"],
            "colors": row["colors"],
            "color_identity": row["color_identity"],
            "set_code": row["set_code"],
            "set_name": row["set_name"],
            "collector_number": row["collector_number"],
            "rarity": row["rarity"],
            "printing_id": row["printing_id"],
            "image_uri": row["image_uri"],
            "artist": row["artist"],
            "frame_effects": row["frame_effects"],
            "border_color": row["border_color"],
            "full_art": bool(row["full_art"]),
            "promo": bool(row["promo"]),
            "promo_types": row["promo_types"],
            "finishes": row["finishes"],
            "layout": row["layout"] or "normal",
        }

        printing_id = row["printing_id"]
        finishes = json.loads(row["finishes"]) if row["finishes"] else []
        foil_only = "nonfoil" not in finishes
        price_type = "foil" if foil_only else "normal"
        result["ck_price"] = _get_sqlite_price(self.db_path, set_code, cn, "cardkingdom", f"buylist_{price_type}") or _get_sqlite_price(self.db_path, set_code, cn, "cardkingdom", price_type)
        result["tcg_price"] = _get_sqlite_price(self.db_path, set_code, cn, "tcgplayer", price_type)
        result["ck_url"] = self.generator.get_ck_url(printing_id, foil_only) if self.generator else ""

        conn.close()
        self._send_json(result)

    def _api_prices_status(self):
        conn = self._get_conn()
        log = conn.execute(
            "SELECT fetched_at FROM price_fetch_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        conn.close()
        if log and count > 0:
            self._send_json({"available": True, "last_modified": log["fetched_at"]})
        else:
            self._send_json({"available": False, "last_modified": None})

    def _api_collection_growth(self, params: dict):
        """Return daily (count, tcg_value, ck_value) series for the filtered collection.

        Mirrors the search-filter parsing in `/api/collection`. A query is
        aggregated day by day inside SQLite; the *unfiltered* series is instead
        read out of the materialized `collection_value_history` table, which is
        O(days) rather than O(price rows the collection has ever had).

        The two are separate branches on "was a query supplied?", not a fast path
        that falls back — there is one table and a filter would need a different
        one, so a filtered request never consults it and never has a miss to
        recover from. The unfiltered branch rebuilds the table when it is stale
        and then reads it, so the answer always comes from freshly-valid data.

        `?range=` is the window length in days (0 / absent = full history). The
        window is the last `range` days ending today; it is clamped to the first
        acquisition, so asking for more days than the collection has is the same
        as asking for everything. The series is cumulative and every point is
        absolute, so a windowed response is bit-identical to the corresponding
        slice of the full-history response — which is also what lets the stored
        full history serve a windowed request by slicing.

        Prices forward-fill: the most recent known price <= D is used, including
        observations from before the window. Cards with no price on/before D
        contribute 0 to value but still count.

        Response: {"dates": ["YYYY-MM-DD", ...], "counts": [...],
                   "tcg_values": [...], "ck_values": [...], "earliest": "..."}
        `earliest` is the first acquisition in the whole filtered collection,
        independent of the window, so the UI can size its range pills.
        """
        from mtg_collector.db import growth
        from mtg_collector.search import SearchError, compile_query, parse_query

        # Stripped, so a query bar holding nothing but spaces is the unfiltered
        # case it renders as rather than a filter that happens to match all.
        q = params.get("q", [""])[0].strip()
        tz = params.get("tz", [""])[0] or None
        range_days = int(params.get("range", ["0"])[0] or 0)

        where_sql = "1=1"
        sql_params: list = []
        compiled = None
        if q:
            try:
                ast = parse_query(q)
                compiled = compile_query(ast, tz=tz)
                where_sql = compiled.where_sql
                sql_params = list(compiled.params)
            except SearchError as e:
                self._send_json({"error": str(e), "position": e.position}, 400)
                return

        # is:unowned makes no sense for a growth chart — ignore.
        if compiled and compiled.include_unowned:
            self._send_json(dict(growth.EMPTY_SERIES))
            return

        # Match /api/collection's status default
        has_status = compiled and compiled.has_status_filter
        if not has_status:
            if where_sql == "1=1":
                where_sql = growth.UNFILTERED_WHERE
            else:
                where_sql = f"{growth.UNFILTERED_WHERE} AND ({where_sql})"

        # Conditional joins (mirrors /api/collection's default template — the
        # collection-anchored one, since growth is always about owned rows).
        extra_joins = []
        if compiled and compiled.needs_price_join:
            extra_joins.append(
                "LEFT JOIN latest_prices _lp ON _lp.set_code = p.set_code"
                " AND _lp.collector_number = p.collector_number AND _lp.price_type = 'normal'"
            )
        if compiled and compiled.needs_wishlist_join:
            extra_joins.append(
                "LEFT JOIN wishlist _wl ON _wl.oracle_id = card.oracle_id AND _wl.fulfilled_at IS NULL"
            )
        extra_joins_sql = "\n            ".join(extra_joins)

        conn = self._get_conn()
        try:
            if q:
                result = growth.compute_series(
                    conn,
                    where_sql=where_sql,
                    params=sql_params,
                    extra_joins_sql=extra_joins_sql,
                    range_days=range_days,
                )
            else:
                if not growth.history_is_current(conn):
                    growth.rebuild_history(conn)
                result = growth.read_history(conn, range_days)
        finally:
            conn.close()

        self._send_json(result)

    def _api_price_history(self, set_code: str, collector_number: str):
        """Return full price time series for a card."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT source, price_type, price, observed_at FROM prices "
            "WHERE set_code = ? AND collector_number = ? ORDER BY observed_at",
            (set_code.lower(), collector_number),
        ).fetchall()
        conn.close()

        result: dict[str, list] = {}
        for row in rows:
            key = f"{row['source']}_{row['price_type']}"
            result.setdefault(key, []).append({
                "date": row["observed_at"],
                "price": row["price"],
            })
        self._send_json(result)

    def _api_get_settings(self):
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        init_db(conn)
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        self._send_json({row["key"]: row["value"] for row in rows})

    def _api_put_settings(self):
        from mtg_collector.db.schema import init_db
        data = self._read_json_body()
        if data is None:
            return
        conn = self._get_conn()
        try:
            init_db(conn)
            for key, value in data.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (str(key), str(value)),
                )
            conn.commit()
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        finally:
            conn.close()
        self._send_json({row["key"]: row["value"] for row in rows})

    def _api_fetch_prices(self):
        try:
            from mtg_collector.cli.data_cmd import _fetch_prices as fetch_prices_cmd
            fetch_prices_cmd(force=True)
            # Return updated status
            conn = self._get_conn()
            try:
                log = conn.execute(
                    "SELECT fetched_at FROM price_fetch_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                last_modified = log["fetched_at"] if log else None
            finally:
                conn.close()
            self._send_json({"available": bool(log), "last_modified": last_modified})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    # ── Ingest2 API endpoints (DB-backed) ──

    def _ingest2_db(self):
        """Get a DB connection with schema init."""
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        # FK setting handled by _get_conn (skipped when ATTACH'd shared DB).
        init_db(conn)
        return conn

    def _ingest2_load_image(self, conn, image_id):
        """Load an ingest_images row as dict."""
        row = conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def _ingest2_update_image(self, conn, image_id, **updates):
        """Update columns on an ingest_images row."""
        from mtg_collector.utils import now_iso
        updates["updated_at"] = now_iso()
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [image_id]
        conn.execute(f"UPDATE ingest_images SET {set_clauses} WHERE id = ?", values)
        conn.commit()

    def _api_ingest2_counts(self):
        """Return counts per status for badge display."""
        conn = self._ingest2_db()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM ingest_images GROUP BY status"
        ).fetchall()
        conn.close()
        counts = {row["status"]: row["cnt"] for row in rows}
        self._send_json(counts)

    def _api_ingest2_recent(self, params):
        """Return all non-INGESTED images with computed status info.

        Optional ?id=X filters to a single image (for per-image polling).
        """
        image_id = params.get("id", [None])[0]
        conn = self._ingest2_db()
        where = ("WHERE (status NOT IN ('INGESTED', 'DONE')"
                 " OR (status = 'DONE' AND md5 NOT IN (SELECT DISTINCT image_md5 FROM ingest_lineage)))")
        args = []
        if image_id is not None:
            where += " AND id = ?"
            args.append(int(image_id))
        rows = conn.execute(
            f"""SELECT id, filename, stored_name, md5, status, error_message,
                      ocr_result, claude_result, scryfall_matches, disambiguated,
                      confirmed_finishes, crops, created_at, updated_at
               FROM ingest_images
               {where}
               ORDER BY id DESC""",
            args,
        ).fetchall()

        # Build lookup of confirmed finishes: prefer image record, fall back to lineage
        confirmed_finishes = {}  # (md5, card_index) → finish
        for r in rows:
            d = dict(r)
            md5_val = d.get("md5") or d.get("stored_name", "")
            # First: image record's confirmed_finishes column
            img_finishes = json.loads(d["confirmed_finishes"]) if d.get("confirmed_finishes") else []
            for idx, f in enumerate(img_finishes):
                if f is not None:
                    confirmed_finishes[(md5_val, idx)] = f
            # Second: lineage → collection (fills gaps)
            lineage_rows = conn.execute(
                """SELECT il.card_index, c.finish
                   FROM ingest_lineage il
                   JOIN collection c ON c.id = il.collection_id
                   WHERE il.image_md5 = ?""",
                (md5_val,),
            ).fetchall()
            for lr in lineage_rows:
                key = (md5_val, lr["card_index"])
                if key not in confirmed_finishes:
                    confirmed_finishes[key] = lr["finish"]

        conn.close()

        result = []
        for r in rows:
            d = dict(r)
            md5_val = d.get("md5") or d.get("stored_name", "")
            # Compute card counts
            claude_result = json.loads(d["claude_result"]) if d.get("claude_result") else []
            disambiguated = json.loads(d["disambiguated"]) if d.get("disambiguated") else []
            total_cards = len(disambiguated) if disambiguated else len(claude_result)
            done_count = sum(1 for s in disambiguated if s is not None) if disambiguated else 0
            pending_count = total_cards - done_count

            # Compute border_status
            status = d["status"]
            if status in ("READY_FOR_OCR", "PROCESSING"):
                border_status = "processing"
            elif status == "ERROR":
                border_status = "error"
            elif status == "DONE":
                border_status = "done"
            elif status == "READY_FOR_DISAMBIGUATION":
                border_status = "needs_disambiguation"
            else:
                border_status = "processing"

            # Extract card summaries — use confirmed scryfall name when
            # available so corrections are reflected on the recent page.
            scryfall_matches = json.loads(d["scryfall_matches"]) if d.get("scryfall_matches") else []
            ocr_fragments = json.loads(d["ocr_result"]) if d.get("ocr_result") else []
            cards_summary = []
            for idx, card in enumerate(claude_result):
                sid = disambiguated[idx] if idx < len(disambiguated) else None
                resolved = None
                if sid and sid != "skipped" and idx < len(scryfall_matches):
                    resolved = next((c for c in scryfall_matches[idx] if (c.get("printing_id") or c.get("scryfall_id")) == sid), None)
                if resolved:
                    # Use confirmed finish from collection if available
                    coll_finish = confirmed_finishes.get((md5_val, idx))
                    if not coll_finish:
                        finishes = resolved.get("finishes", [])
                        coll_finish = finishes[0] if finishes else "nonfoil"
                    entry = {
                        "name": resolved.get("name", card.get("name", "")),
                        "set_code": (resolved.get("set_code") or card.get("set_code") or "").upper(),
                        "collector_number": resolved.get("collector_number", ""),
                        "finish": coll_finish,
                        "image_uri": resolved.get("image_uri") or "",
                    }
                else:
                    # Use top candidate for set_code/finish when available
                    top = scryfall_matches[idx][0] if idx < len(scryfall_matches) and scryfall_matches[idx] else {}
                    top_finishes = top.get("finishes", [])
                    entry = {
                        "name": card.get("name", ""),
                        "set_code": (card.get("set_code") or top.get("set_code") or "").upper(),
                        "collector_number": card.get("collector_number") or top.get("collector_number", ""),
                        "finish": top_finishes[0] if top_finishes else "nonfoil",
                        "image_uri": top.get("image_uri") or "",
                    }
                # OCR name: topmost fragments for this card, merging nearby bboxes
                entry["ocr_name"] = _extract_ocr_name(ocr_fragments, card.get("fragment_indices", []))
                entry["claude_name"] = card.get("name", "")

                # Detect finish options across ALL candidates for badge UI
                candidates = scryfall_matches[idx] if idx < len(scryfall_matches) else []
                if candidates:
                    unique_ids = {c.get("printing_id") or c.get("scryfall_id") for c in candidates}
                    per_candidate = [frozenset(c.get("finishes", ["nonfoil"])) for c in candidates]
                    if per_candidate and all(fs == per_candidate[0] for fs in per_candidate):
                        entry["finish_options"] = sorted(per_candidate[0])
                        if len(unique_ids) == 1:
                            entry["finish_printing_id"] = next(iter(unique_ids))

                cards_summary.append(entry)

            crops = json.loads(d["crops"]) if d.get("crops") else []
            crop = crops[0] if crops else None

            result.append({
                "id": d["id"],
                "filename": d["filename"],
                "stored_name": d["stored_name"],
                "status": status,
                "border_status": border_status,
                "error_message": d["error_message"],
                "total_cards": total_cards,
                "done_count": done_count,
                "pending_count": pending_count,
                "cards": cards_summary,
                "crop": crop,
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
            })
        self._send_json(result)

    def _api_ingest2_usage_stats(self, params):
        """Aggregate API token usage and estimated cost for non-INGESTED images."""
        conn = self._ingest2_db()
        rows = conn.execute(
            """SELECT api_usage FROM ingest_images
               WHERE api_usage IS NOT NULL
               AND status != 'INGESTED'""",
        ).fetchall()
        conn.close()

        totals = {
            "haiku": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
            "sonnet": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
            "opus": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
        }
        images_with_usage = 0
        for row in rows:
            u = json.loads(row["api_usage"])
            for model in ("haiku", "sonnet", "opus"):
                if model in u:
                    totals[model]["input"] += u[model].get("input", 0)
                    totals[model]["output"] += u[model].get("output", 0)
                    totals[model]["cache_read"] += u[model].get("cache_read", 0)
                    totals[model]["cache_creation"] += u[model].get("cache_creation", 0)
            images_with_usage += 1

        # Per-million-token pricing (cache_read = 10% of input, cache_creation = 125% of input)
        PRICES = {
            "haiku":  {"input": 0.80,  "output": 4.00},
            "sonnet": {"input": 3.00,  "output": 15.00},
            "opus":   {"input": 15.00, "output": 75.00},
        }
        estimated_cost = sum(
            totals[m]["input"]  * PRICES[m]["input"]  / 1_000_000 +
            totals[m]["output"] * PRICES[m]["output"] / 1_000_000 +
            totals[m]["cache_read"] * PRICES[m]["input"] * 0.1 / 1_000_000 +
            totals[m]["cache_creation"] * PRICES[m]["input"] * 1.25 / 1_000_000
            for m in PRICES
        )
        self._send_json({
            "images_with_usage": images_with_usage,
            "usage": totals,
            "estimated_cost_usd": round(estimated_cost, 6),
        })

    def _api_ingest2_pending_disambiguation(self):
        """Return flat list of all cards needing disambiguation across all images."""
        conn = self._ingest2_db()
        rows = conn.execute(
            """SELECT id, filename, stored_name, claude_result, scryfall_matches,
                      crops, disambiguated
               FROM ingest_images
               WHERE status = 'READY_FOR_DISAMBIGUATION'
               ORDER BY id""",
        ).fetchall()
        conn.close()

        pending = []
        for r in rows:
            d = dict(r)
            claude_result = json.loads(d["claude_result"]) if d.get("claude_result") else []
            scryfall_matches = json.loads(d["scryfall_matches"]) if d.get("scryfall_matches") else []
            crops = json.loads(d["crops"]) if d.get("crops") else []
            disambiguated = json.loads(d["disambiguated"]) if d.get("disambiguated") else []

            for card_idx, status in enumerate(disambiguated):
                if status is not None:
                    continue
                pending.append({
                    "image_id": d["id"],
                    "card_idx": card_idx,
                    "image_filename": d["stored_name"],
                    "card_info": claude_result[card_idx] if card_idx < len(claude_result) else {},
                    "candidates": scryfall_matches[card_idx] if card_idx < len(scryfall_matches) else [],
                    "crop": crops[card_idx] if card_idx < len(crops) else None,
                })
        self._send_json(pending)

    def _api_ingest2_images(self, params):
        """List images filtered by status."""
        status = params.get("status", [""])[0]
        conn = self._ingest2_db()
        if status:
            rows = conn.execute(
                "SELECT id, filename, stored_name, md5, status, mode, claude_result, error_message, created_at, updated_at FROM ingest_images WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, filename, stored_name, md5, status, mode, claude_result, error_message, created_at, updated_at FROM ingest_images ORDER BY id"
            ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            # Add claude_count without sending full claude_result
            cr = d.pop("claude_result", None)
            if cr:
                cards = json.loads(cr)
                d["claude_count"] = len(cards)
            else:
                d["claude_count"] = None
            result.append(d)
        self._send_json(result)

    def _api_ingest2_image_detail(self, image_id):
        """Get full state for one image."""
        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        # Look up confirmed finishes: prefer image record, fall back to lineage
        confirmed_finishes = []
        if img and img.get("md5"):
            disamb = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
            img_finishes = json.loads(img["confirmed_finishes"]) if img.get("confirmed_finishes") else []
            lineage_rows = conn.execute(
                """SELECT il.card_index, c.finish
                   FROM ingest_lineage il
                   JOIN collection c ON c.id = il.collection_id
                   WHERE il.image_md5 = ?
                   ORDER BY il.card_index""",
                (img["md5"],),
            ).fetchall()
            fin_map = {lr["card_index"]: lr["finish"] for lr in lineage_rows}
            confirmed_finishes = []
            for i in range(len(disamb)):
                f = img_finishes[i] if i < len(img_finishes) and img_finishes[i] is not None else fin_map.get(i)
                confirmed_finishes.append(f)
        conn.close()
        if not img:
            self._send_json({"error": "Not found"}, 404)
            return
        # Parse JSON fields
        for field in ("ocr_result", "claude_result", "agent_trace", "scryfall_matches", "crops",
                      "disambiguated", "names_data", "names_disambiguated", "user_card_edits"):
            if img.get(field):
                img[field] = json.loads(img[field])
        # Pre-compute ocr_name and claude_name per card
        ocr_fragments = img.get("ocr_result") or []
        claude_cards = img.get("claude_result") or []
        card_names = []
        for card in claude_cards:
            card_names.append({
                "ocr_name": _extract_ocr_name(ocr_fragments, card.get("fragment_indices", [])),
                "claude_name": card.get("name", ""),
            })
        img["card_names"] = card_names
        img["confirmed_finishes"] = confirmed_finishes
        self._send_json(img)

    def _api_ingest2_upload(self):
        """Upload files and create DB rows."""
        from mtg_collector.utils import now_iso

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "Expected multipart/form-data"}, 400)
            return

        boundary = content_type.split("boundary=")[1].strip()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        uploaded = []
        collisions = []
        parts = body.split(f"--{boundary}".encode())

        conn = self._ingest2_db()
        ts = now_iso()

        # Extract set_hint from non-file form fields
        set_hint = None
        for part in parts:
            if not part or part.strip() == b"--" or part.strip() == b"":
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header_str = part[:header_end].decode("utf-8", errors="replace")
            if 'filename="' in header_str:
                continue  # skip file parts
            name_match = re.search(r'name="([^"]+)"', header_str)
            if name_match and name_match.group(1) == "set_hint":
                raw = part[header_end + 4:]
                if raw.endswith(b"\r\n"):
                    raw = raw[:-2]
                set_hint = raw.decode("utf-8", errors="replace").strip() or None

        for part in parts:
            if not part or part.strip() == b"--" or part.strip() == b"":
                continue

            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header_bytes = part[:header_end]
            file_content = part[header_end + 4:]
            if file_content.endswith(b"\r\n"):
                file_content = file_content[:-2]

            header_str = header_bytes.decode("utf-8", errors="replace")

            filename_match = re.search(r'filename="([^"]+)"', header_str)
            if not filename_match:
                continue

            original_name = filename_match.group(1)
            ext = Path(original_name).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue

            stored_name = original_name
            dest = _get_ingest_images_dir() / stored_name

            if dest.exists():
                collisions.append(original_name)
                continue

            dest.write_bytes(file_content)

            md5 = _md5_file(str(dest))

            cursor = conn.execute(
                """INSERT INTO ingest_images (filename, stored_name, md5, status, set_hint, created_at, updated_at)
                   VALUES (?, ?, ?, 'READY_FOR_OCR', ?, ?, ?)""",
                (original_name, stored_name, md5, set_hint, ts, ts),
            )
            image_id = cursor.lastrowid
            conn.commit()

            _log_ingest(f"Upload2: {original_name} -> {stored_name} (ID={image_id}, MD5={md5})")
            uploaded.append({
                "id": image_id,
                "filename": original_name,
                "stored_name": stored_name,
                "md5": md5,
            })

            # Submit for background processing (requires API key or fake agent)
            if _ingest_executor is not None and _can_process():
                _ingest_executor.submit(_process_image_background, self.db_path, image_id)

        conn.close()
        self._send_json({"uploaded": uploaded, "collisions": collisions})

    def _api_ingest2_set_params(self):
        """Set mode for an image."""
        data = self._read_json_body()
        if data is None:
            return
        image_id = data.get("image_id")
        conn = self._ingest2_db()
        updates = {}
        if "mode" in data:
            updates["mode"] = data["mode"]
        if updates:
            self._ingest2_update_image(conn, image_id, **updates)
        conn.close()
        self._send_json({"ok": True})

    def _api_ingest2_process_sse(self, image_id):
        """SSE endpoint: process one image through OCR -> Claude -> DB lookup, DB-backed."""
        if not _can_process():
            self._send_json({"error": "ANTHROPIC_API_KEY not set — card identification requires an API key"}, 503)
            return
        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        # Stale processing recovery
        if img["status"] == "PROCESSING":
            from datetime import datetime, timezone

            updated = datetime.fromisoformat(img["updated_at"].replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - updated).total_seconds() > 600:
                self._ingest2_update_image(conn, image_id, status="READY_FOR_OCR")
                img["status"] = "READY_FOR_OCR"

        if img["status"] not in ("READY_FOR_OCR",):
            conn.close()
            self._send_json({"error": f"Image status is {img['status']}, not READY_FOR_OCR"}, 400)
            return

        # Mark as processing
        self._ingest2_update_image(conn, image_id, status="PROCESSING")

        # Set up SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def send_event(event_type, data_obj):
            payload = f"event: {event_type}\ndata: {json.dumps(data_obj)}\n\n"
            try:
                self.wfile.write(payload.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        try:
            self._process_image2_sse(conn, image_id, img, send_event)
            send_event("done", {})
        except Exception as e:
            _log_ingest(f"Error processing image {image_id}: {e}")
            send_event("error", {"message": str(e)})
            partial_trace = getattr(e, "agent_trace", [])
            self._ingest2_update_image(
                conn, image_id,
                status="READY_FOR_OCR",
                agent_trace=json.dumps(partial_trace) if partial_trace else None,
                error_message=str(e),
            )
            send_event("done", {"error": True})
        conn.close()

    def _process_image2_sse(self, conn, image_id, img, send_event):
        """Process a single image: OCR -> Claude -> DB lookup, streaming SSE events. DB-backed."""
        ocr_fragments, claude_cards, all_matches, all_crops, disambiguated, agent_trace, api_usage = _process_image_core(
            conn, image_id, img, send_event,
        )

        # Save all state to DB
        self._ingest2_update_image(conn, image_id,
            status="READY_FOR_DISAMBIGUATION",
            ocr_result=json.dumps(ocr_fragments),
            claude_result=json.dumps(claude_cards),
            agent_trace=json.dumps(agent_trace),
            api_usage=json.dumps(api_usage) if api_usage else None,
            scryfall_matches=json.dumps(all_matches),
            crops=json.dumps(all_crops),
            disambiguated=json.dumps(disambiguated),
        )

        # Build matches_ready payload
        already_ingested = {ci for ci, d in enumerate(disambiguated) if d == "already_ingested"}
        cards_payload = []
        for ci, card_info in enumerate(claude_cards):
            cards_payload.append({
                "card_info": card_info,
                "candidates": all_matches[ci] if ci < len(all_matches) else [],
                "crop": all_crops[ci] if ci < len(all_crops) else None,
                "already_ingested": ci in already_ingested,
            })

        send_event("matches_ready", {"cards": cards_payload})

    def _api_ingest2_next_card(self, image_id):
        """Find the next undisambiguated card for an image. Auto-confirms single-candidate cards."""
        from mtg_collector.db.models import (
            CollectionEntry,
            CollectionRepository,
            PrintingRepository,
        )
        from mtg_collector.utils import now_iso

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        scryfall_matches = json.loads(img["scryfall_matches"]) if img.get("scryfall_matches") else []
        crops = json.loads(img["crops"]) if img.get("crops") else []
        claude_result = json.loads(img["claude_result"]) if img.get("claude_result") else []

        auto_confirmed = 0

        for card_idx, status in enumerate(disambiguated):
            if status is not None:
                continue

            candidates = scryfall_matches[card_idx] if card_idx < len(scryfall_matches) else []

            # Auto-confirm single-candidate cards
            if len(candidates) == 1:
                c = candidates[0]
                printing_id = c.get("printing_id") or c.get("scryfall_id")

                printing_repo = PrintingRepository(conn)
                collection_repo = CollectionRepository(conn)

                printing = printing_repo.get(printing_id)
                if printing:
                    entry = CollectionEntry(
                        id=None,
                        printing_id=printing_id,
                        finish="nonfoil",
                        condition="Near Mint",
                        source="ocr_ingest",
                    )
                    entry_id = collection_repo.add(entry)

                    md5 = img["md5"]
                    conn.execute(
                        """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (entry_id, md5, img["stored_name"], card_idx, now_iso()),
                    )

                    disambiguated[card_idx] = printing_id
                    self._ingest2_update_image(conn, image_id, disambiguated=json.dumps(disambiguated))
                    conn.commit()

                    _log_ingest(f"Auto-confirmed: {printing_id} ({c.get('set_code', '???').upper()} #{c.get('collector_number', '???')})")
                    auto_confirmed += 1
                    continue

            # Card needs human input
            total_cards = len(disambiguated)
            total_done = sum(1 for s in disambiguated if s is not None)

            # Check if all done after auto-confirms
            if all(d is not None for d in disambiguated):
                self._ingest2_update_image(conn, image_id, status="DONE")

            conn.close()
            self._send_json({
                "done": False,
                "image_id": image_id,
                "card_idx": card_idx,
                "image_filename": img["stored_name"],
                "card": claude_result[card_idx] if card_idx < len(claude_result) else {},
                "candidates": candidates,
                "crop": crops[card_idx] if card_idx < len(crops) else None,
                "total_cards": total_cards,
                "total_done": total_done,
                "auto_confirmed": auto_confirmed,
            })
            return

        # All cards done (possibly all auto-confirmed)
        if all(d is not None for d in disambiguated):
            self._ingest2_update_image(conn, image_id, status="DONE")
            conn.commit()

        total_cards = len(disambiguated)
        total_done = sum(1 for s in disambiguated if s is not None)
        conn.close()
        self._send_json({"done": True, "total_cards": total_cards, "total_done": total_done, "auto_confirmed": auto_confirmed})

    def _api_ingest2_confirm(self):
        """Confirm a candidate: update disambiguated + confirmed_finishes.

        Does NOT create a collection entry — that belongs to batch ingest.
        """
        from mtg_collector.db.models import PrintingRepository

        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        card_idx = data["card_idx"]
        printing_id = data["printing_id"]
        finish = data.get("finish", "nonfoil")

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        printing_repo = PrintingRepository(conn)
        printing = printing_repo.get(printing_id)
        if not printing:
            conn.close()
            self._send_json({"error": f"Printing {printing_id} not in local cache"}, 404)
            return

        # Update disambiguated + confirmed_finishes
        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        while len(disambiguated) <= card_idx:
            disambiguated.append(None)
        disambiguated[card_idx] = printing_id

        confirmed_finishes = json.loads(img["confirmed_finishes"]) if img.get("confirmed_finishes") else []
        while len(confirmed_finishes) <= card_idx:
            confirmed_finishes.append(None)
        confirmed_finishes[card_idx] = finish

        self._ingest2_update_image(conn, image_id, disambiguated=json.dumps(disambiguated), confirmed_finishes=json.dumps(confirmed_finishes))

        # Check if all cards done
        if all(d is not None for d in disambiguated):
            self._ingest2_update_image(conn, image_id, status="DONE")

        conn.close()

        name = printing.raw_json and json.loads(printing.raw_json).get("name", "???") or "???"
        set_code = printing.set_code
        cn = printing.collector_number
        _log_ingest(f"Confirmed: {name} ({set_code.upper()} #{cn})")

        self._send_json({"ok": True, "name": name, "set_code": set_code, "collector_number": cn})

    def _api_ingest2_add_card(self):
        """Add a new card slot to an existing image and confirm it."""
        from mtg_collector.db.models import (
            CollectionEntry,
            CollectionRepository,
            PrintingRepository,
        )
        from mtg_collector.utils import now_iso

        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        printing_id = data["printing_id"]
        finish = data.get("finish", "nonfoil")

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        # Append to all parallel arrays
        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        scryfall_matches = json.loads(img["scryfall_matches"]) if img.get("scryfall_matches") else []
        claude_result = json.loads(img["claude_result"]) if img.get("claude_result") else []
        crops = json.loads(img["crops"]) if img.get("crops") else []

        disambiguated.append(None)
        scryfall_matches.append([])
        claude_result.append({})
        crops.append(None)

        card_idx = len(disambiguated) - 1

        # Look up in local DB
        printing_repo = PrintingRepository(conn)
        collection_repo = CollectionRepository(conn)

        printing = printing_repo.get(printing_id)
        if not printing:
            conn.close()
            self._send_json({"error": f"Printing {printing_id} not in local cache"}, 404)
            return

        card_data = printing.get_card_data()

        # Create collection entry
        entry = CollectionEntry(
            id=None,
            printing_id=printing_id,
            finish=finish,
            condition="Near Mint",
            source="ocr_ingest",
        )
        entry_id = collection_repo.add(entry)

        # Insert ingest_lineage
        md5 = img["md5"]
        conn.execute(
            """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (entry_id, md5, img["stored_name"], card_idx, now_iso()),
        )

        # Update disambiguated and prepend to scryfall_matches
        disambiguated[card_idx] = printing_id
        scryfall_matches[card_idx] = _format_candidates([card_data]) if card_data else []

        # Check if all done
        status_update = {}
        if all(d is not None for d in disambiguated):
            status_update["status"] = "DONE"

        self._ingest2_update_image(
            conn, image_id,
            disambiguated=json.dumps(disambiguated),
            scryfall_matches=json.dumps(scryfall_matches),
            claude_result=json.dumps(claude_result),
            crops=json.dumps(crops),
            **status_update,
        )

        conn.commit()
        conn.close()

        name = card_data.get("name", "???") if card_data else "???"
        set_code = printing.set_code
        _log_ingest(f"AddCard: {name} ({set_code.upper()}) -> collection ID {entry_id}, image {image_id} slot {card_idx}")

        self._send_json({"ok": True, "entry_id": entry_id, "name": name, "set_code": set_code, "card_idx": card_idx})

    def _api_ingest2_remove_card(self):
        """Remove a card slot from an image. If confirmed, also remove from collection."""
        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        card_idx = data["card_idx"]

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        scryfall_matches = json.loads(img["scryfall_matches"]) if img.get("scryfall_matches") else []
        claude_result = json.loads(img["claude_result"]) if img.get("claude_result") else []
        crops = json.loads(img["crops"]) if img.get("crops") else []

        if card_idx < 0 or card_idx >= len(disambiguated):
            conn.close()
            self._send_json({"error": "Invalid card index"}, 400)
            return

        # If this card was confirmed, remove collection entry + lineage
        sid = disambiguated[card_idx]
        removed_collection = False
        if sid and sid != "skipped":
            md5 = img["md5"]
            lineage = conn.execute(
                "SELECT collection_id FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?",
                (md5, card_idx),
            ).fetchone()
            if lineage:
                conn.execute("DELETE FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?", (md5, card_idx))
                conn.execute("DELETE FROM collection WHERE id = ?", (lineage["collection_id"],))
                removed_collection = True

        # Remove from all parallel arrays
        disambiguated.pop(card_idx)
        if card_idx < len(scryfall_matches):
            scryfall_matches.pop(card_idx)
        if card_idx < len(claude_result):
            claude_result.pop(card_idx)
        if card_idx < len(crops):
            crops.pop(card_idx)

        # Fix card_index values in ingest_lineage for shifted slots
        conn.execute(
            "UPDATE ingest_lineage SET card_index = card_index - 1 WHERE image_md5 = ? AND card_index > ?",
            (img["md5"], card_idx),
        )

        # Determine status
        status_update = {}
        if len(disambiguated) == 0:
            status_update["status"] = "DONE"
        elif all(d is not None for d in disambiguated):
            status_update["status"] = "DONE"
        else:
            status_update["status"] = "READY_FOR_DISAMBIGUATION"

        self._ingest2_update_image(
            conn, image_id,
            disambiguated=json.dumps(disambiguated),
            scryfall_matches=json.dumps(scryfall_matches),
            claude_result=json.dumps(claude_result),
            crops=json.dumps(crops),
            **status_update,
        )

        conn.commit()
        conn.close()

        _log_ingest(f"RemoveCard: image {image_id} slot {card_idx}, collection_removed={removed_collection}")
        self._send_json({"ok": True, "removed_collection": removed_collection})

    def _api_ingest2_skip(self):
        """Skip a card."""
        data = self._read_json_body()
        if data is None:
            return
        image_id = data["image_id"]
        card_idx = data["card_idx"]

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        if card_idx < len(disambiguated):
            disambiguated[card_idx] = "skipped"
        self._ingest2_update_image(conn, image_id, disambiguated=json.dumps(disambiguated))

        if all(d is not None for d in disambiguated):
            self._ingest2_update_image(conn, image_id, status="DONE")

        conn.close()
        self._send_json({"ok": True})

    def _api_ingest2_correct(self):
        """Correct a mis-identified card: swap collection entry.

        If no collection entry exists yet (pre-batch-ingest), just update
        the image metadata (disambiguated + confirmed_finishes).
        """
        from mtg_collector.db.models import (
            CollectionEntry,
            CollectionRepository,
            PrintingRepository,
        )

        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        card_idx = data["card_idx"]
        printing_id = data["printing_id"]
        finish = data.get("finish", "nonfoil")

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        md5 = img["md5"]

        # Update disambiguated + confirmed_finishes on the image record
        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []
        if card_idx < len(disambiguated):
            disambiguated[card_idx] = printing_id
        confirmed_finishes = json.loads(img["confirmed_finishes"]) if img.get("confirmed_finishes") else []
        while len(confirmed_finishes) < len(disambiguated):
            confirmed_finishes.append(None)
        if card_idx < len(confirmed_finishes):
            confirmed_finishes[card_idx] = finish

        # Ensure corrected card is in scryfall_matches so recent detail can display it
        scryfall_matches = json.loads(img["scryfall_matches"]) if img.get("scryfall_matches") else []

        # Find existing ingest_lineage entry for this image+card_idx
        lineage = conn.execute(
            "SELECT collection_id FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?",
            (md5, card_idx),
        ).fetchone()

        entry_id = None
        name = "???"
        set_code = ""

        if lineage:
            # Has collection entry — swap it
            old_collection_id = lineage["collection_id"]
            printing_repo = PrintingRepository(conn)
            collection_repo = CollectionRepository(conn)

            printing = printing_repo.get(printing_id)
            if not printing:
                conn.close()
                self._send_json({"error": f"Printing {printing_id} not in local cache"}, 404)
                return

            card_data = printing.get_card_data()

            entry = CollectionEntry(
                id=None,
                printing_id=printing_id,
                finish=finish,
                condition="Near Mint",
                source="ocr_ingest",
            )
            entry_id = collection_repo.add(entry)

            conn.execute(
                "UPDATE ingest_lineage SET collection_id = ? WHERE image_md5 = ? AND card_index = ?",
                (entry_id, md5, card_idx),
            )
            collection_repo.delete(old_collection_id)

            if card_idx < len(scryfall_matches):
                existing_ids = {c.get("printing_id") or c.get("scryfall_id") for c in scryfall_matches[card_idx]}
                if printing_id not in existing_ids:
                    formatted = _format_candidates([card_data]) if card_data else []
                    scryfall_matches[card_idx] = formatted + scryfall_matches[card_idx]

            name = card_data.get("name", "???") if card_data else "???"
            set_code = printing.set_code
            _log_ingest(f"Corrected: {name} ({set_code.upper()}) -> collection ID {entry_id} (replaced {old_collection_id})")
        else:
            # No collection entry yet — just update image metadata
            # Resolve name for response
            if card_idx < len(scryfall_matches) and scryfall_matches[card_idx]:
                match = next((c for c in scryfall_matches[card_idx] if (c.get("printing_id") or c.get("scryfall_id")) == printing_id), None)
                if match:
                    name = match.get("name", "???")
                    set_code = match.get("set_code", "")

        self._ingest2_update_image(
            conn, image_id,
            disambiguated=json.dumps(disambiguated),
            confirmed_finishes=json.dumps(confirmed_finishes),
            scryfall_matches=json.dumps(scryfall_matches),
        )

        # Check if all cards done
        if all(d is not None for d in disambiguated):
            self._ingest2_update_image(conn, image_id, status="DONE")

        conn.commit()
        conn.close()

        self._send_json({"ok": True, "entry_id": entry_id, "name": name, "set_code": set_code})

    def _api_ingest2_search_card(self):
        """Manual card search during disambiguation."""
        data = self._read_json_body()
        if data is None:
            return

        image_id = data.get("image_id")
        card_idx = data.get("card_idx")
        query = (data.get("query") or "").strip()

        if not query:
            self._send_json({"error": "Empty query"}, 400)
            return

        conn = self._ingest2_db()

        # Resolve optional set_code filter (code or name)
        resolved_set = None
        raw_set = (data.get("set_code") or "").strip()
        if raw_set:
            from mtg_collector.db.models import SetRepository
            set_repo = SetRepository(conn)
            s = set_repo.get(raw_set.lower())
            if not s:
                s = set_repo.get_by_name(raw_set)
            if s:
                resolved_set = s.set_code

        results = _local_name_search(conn, query, set_code=resolved_set)
        formatted = _format_candidates(results)

        # Update scryfall_matches in DB if image_id provided
        if image_id is not None and card_idx is not None:
            img = self._ingest2_load_image(conn, image_id)
            if img and img.get("scryfall_matches"):
                matches = json.loads(img["scryfall_matches"])
                if card_idx < len(matches):
                    matches[card_idx] = formatted
                    self._ingest2_update_image(conn, image_id, scryfall_matches=json.dumps(matches))
        conn.close()

        self._send_json({"candidates": formatted})

    def _api_ingest2_update_cards(self):
        """Stage 3.1: save corrected card list after count mismatch resolution."""
        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        corrected_cards = data["cards"]  # [{name, set_code, collector_number, ...}]

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        ocr_fragments = json.loads(img["ocr_result"]) if img.get("ocr_result") else []

        # Resolve corrected card list against local DB
        all_matches = []
        all_crops = []
        for ci, card_info in enumerate(corrected_cards):
            candidates = _resolve_candidates(conn, [card_info])
            formatted = _format_candidates(candidates)
            all_matches.append(formatted)

            frag_indices = card_info.get("fragment_indices", [])
            crop = _compute_card_crop(ocr_fragments, frag_indices)
            all_crops.append(crop)

        disambiguated = [None] * len(corrected_cards)

        self._ingest2_update_image(conn, image_id,
            claude_result=json.dumps(corrected_cards),
            scryfall_matches=json.dumps(all_matches),
            crops=json.dumps(all_crops),
            disambiguated=json.dumps(disambiguated),
            user_card_edits=json.dumps(corrected_cards),
            status="READY_FOR_DISAMBIGUATION",
        )
        conn.close()

        self._send_json({"ok": True, "card_count": len(corrected_cards)})

    def _api_ingest2_reset(self):
        """Reset an image: clear all artifacts + ingest_cache, remove ingested collection entries, requeue for processing."""
        from mtg_collector.utils import now_iso

        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        _reset_ingest_image(conn, image_id, img["md5"], now_iso())
        conn.commit()
        conn.close()

        _log_ingest(f"Reset image {image_id}: {img['filename']} — requeued for processing")

        # Submit for background processing (requires API key or fake agent)
        if _ingest_executor is not None and _can_process():
            _ingest_executor.submit(_process_image_background, self.db_path, image_id)

        self._send_json({"ok": True, "processing": _can_process()})

    def _api_ingest2_refinish(self):
        """Remove all collection entries for an image so it reappears on Recents for finish re-selection."""
        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]

        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        _refinish_ingest_image(conn, image_id, img["md5"])
        conn.commit()
        conn.close()

        _log_ingest(f"Refinish image {image_id}: {img['filename']}")
        self._send_json({"ok": True})

    def _api_ingest2_batch_ingest(self):
        """Ensure all DONE images have collection entries, then mark INGESTED."""
        from mtg_collector.db.models import (
            CollectionEntry,
            CollectionRepository,
            PrintingRepository,
        )
        from mtg_collector.utils import now_iso

        data = self._read_json_body()
        if data is None:
            return

        assign_target = data.get("assign_target", "")
        image_id = data.get("image_id")
        conn = self._ingest2_db()
        rows = conn.execute(*_batch_ingest_query(image_id)).fetchall()

        printing_repo = PrintingRepository(conn)
        collection_repo = CollectionRepository(conn)
        count = 0
        batch_collection_ids = []

        for row in rows:
            img = dict(row)
            disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []

            for card_idx, sid in enumerate(disambiguated):
                if not sid or sid in ("skipped", "already_ingested"):
                    continue
                # Check if already has a lineage entry (already confirmed)
                existing = conn.execute(
                    "SELECT 1 FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?",
                    (img["md5"], card_idx),
                ).fetchone()
                if existing:
                    continue
                # Create collection entry
                printing = printing_repo.get(sid)
                if not printing:
                    continue
                confirmed = json.loads(img["confirmed_finishes"]) if img.get("confirmed_finishes") else []
                finish = None
                if card_idx < len(confirmed) and confirmed[card_idx]:
                    finish = confirmed[card_idx]
                if not finish:
                    finishes = json.loads(printing.raw_json).get("finishes", ["nonfoil"]) if printing.raw_json else ["nonfoil"]
                    finish = finishes[0] if finishes else "nonfoil"
                entry = CollectionEntry(
                    id=None,
                    printing_id=sid,
                    finish=finish,
                    condition="Near Mint",
                    source="ocr_ingest",
                )
                entry_id = collection_repo.add(entry)
                batch_collection_ids.append(entry_id)
                conn.execute(
                    """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (entry_id, img["md5"], img["stored_name"], card_idx, now_iso()),
                )

            conn.execute(
                "UPDATE ingest_images SET status = 'INGESTED' WHERE id = ?",
                (img["id"],),
            )
            count += 1

        conn.commit()

        # Optional deck/binder assignment
        if assign_target and batch_collection_ids:
            from mtg_collector.db.models import BinderRepository, DeckRepository
            if assign_target.startswith("deck:"):
                did = int(assign_target.split(":")[1])
                DeckRepository(conn).add_cards(did, batch_collection_ids, zone="mainboard")
            elif assign_target.startswith("binder:"):
                bid = int(assign_target.split(":")[1])
                BinderRepository(conn).add_cards(bid, batch_collection_ids)
            conn.commit()

        conn.close()

        _log_ingest(f"Batch ingest: processed {count} image(s)")
        self._send_json({"ok": True, "count": count})

    def _api_ingest2_delete(self):
        """Delete an image and its file."""
        data = self._read_json_body()
        if data is None:
            return

        image_id = data["image_id"]
        conn = self._ingest2_db()
        img = self._ingest2_load_image(conn, image_id)
        if not img:
            conn.close()
            self._send_json({"error": "Image not found"}, 404)
            return

        # Delete file
        filepath = _get_ingest_images_dir() / img["stored_name"]
        if filepath.is_file():
            filepath.unlink()

        conn.execute("DELETE FROM ingest_images WHERE id = ?", (image_id,))
        conn.commit()
        conn.close()

        _log_ingest(f"Deleted image {image_id}: {img['filename']}")
        self._send_json({"ok": True})

    # ── Ingest image serving (shared by ingest2 frontend) ──

    def _api_ingest_serve_image(self, filename):
        # Sanitize filename
        if "/" in filename or "\\" in filename or ".." in filename:
            self._send_json({"error": "Invalid filename"}, 400)
            return
        filepath = _get_ingest_images_dir() / filename
        if not filepath.is_file():
            self._send_json({"error": "Not found"}, 404)
            return
        content = filepath.read_bytes()
        content_type = self._CONTENT_TYPES.get(filepath.suffix, "application/octet-stream")
        # The one path that was already doing caching correctly; its headers are
        # unchanged.  See CACHE_IMMUTABLE for what these URLs actually rest on,
        # and why the window is a day rather than a year.
        self._respond(content, content_type, CACHE_IMMUTABLE, ranges=True)

    # (Legacy session-based ingest pipeline removed — use ingest2 endpoints)

    # ── Order API endpoints ──

    def _api_orders_list(self):
        """List all orders with card counts."""
        from mtg_collector.db.models import OrderRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        init_db(conn)
        repo = OrderRepository(conn)
        orders = repo.list_all()
        conn.close()
        self._send_json(orders)

    def _api_order_cards(self, order_id: int):
        """Get cards in an order."""
        from mtg_collector.db.models import OrderRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        init_db(conn)
        repo = OrderRepository(conn)
        cards = repo.get_order_cards(order_id)
        conn.close()
        self._send_json(cards)

    def _api_order_get(self, order_id: int):
        """Get a single order by ID."""
        from mtg_collector.db.models import OrderRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        init_db(conn)
        repo = OrderRepository(conn)
        order = repo.get(order_id)
        conn.close()
        if order is None:
            self._send_json({"error": "Not found"}, 404)
            return
        from dataclasses import asdict
        self._send_json(asdict(order))

    def _api_order_update(self, order_id: int, data: dict):
        """Update order metadata (partial update)."""
        from mtg_collector.db.models import OrderRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        try:
            init_db(conn)
            repo = OrderRepository(conn)
            order = repo.get(order_id)
            if order is None:
                self._send_json({"error": "Not found"}, 404)
                return
            for field in ("order_number", "source", "seller_name", "order_date",
                          "subtotal", "shipping", "tax", "total",
                          "shipping_status", "estimated_delivery", "notes"):
                if field in data:
                    setattr(order, field, data[field])
            repo.update(order)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_collection_update(self, entry_id: int, data: dict):
        """Update a collection entry (partial update)."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        try:
            init_db(conn)
            repo = CollectionRepository(conn)
            entry = repo.get(entry_id)
            if entry is None:
                self._send_json({"error": "Not found"}, 404)
                return
            if "printing_id" in data:
                entry.printing_id = data["printing_id"]
            if "condition" in data:
                entry.condition = data["condition"]
            if "finish" in data:
                entry.finish = data["finish"]
            if "purchase_price" in data:
                entry.purchase_price = data["purchase_price"]
            repo.update(entry)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_order_add_card(self, order_id: int):
        """Add a new card to an existing order."""
        from mtg_collector.db.models import CollectionEntry, CollectionRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import now_iso
        data = self._read_json_body()
        if data is None:
            return
        printing_id = data.get("printing_id")
        if not printing_id:
            self._send_json({"error": "printing_id is required"}, 400)
            return
        conn = self._get_conn()
        try:
            init_db(conn)
            entry = CollectionEntry(
                id=None,
                printing_id=printing_id,
                finish=data.get("finish", "nonfoil"),
                condition=data.get("condition", "Near Mint"),
                purchase_price=data.get("purchase_price"),
                acquired_at=now_iso(),
                source="order_import",
                status="ordered",
                order_id=order_id,
            )
            repo = CollectionRepository(conn)
            new_id = repo.add(entry)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"id": new_id})

    def _api_order_parse(self):
        """Parse order text into structured data."""
        from mtg_collector.services.order_parser import parse_order
        data = self._read_json_body()
        if data is None:
            return
        text = data.get("text", "")
        fmt = data.get("format")
        if fmt == "auto":
            fmt = None
        orders = parse_order(text, fmt)
        # Serialize to JSON-safe dicts
        result = []
        for o in orders:
            result.append({
                "order_number": o.order_number,
                "source": o.source,
                "seller_name": o.seller_name,
                "order_date": o.order_date,
                "subtotal": o.subtotal,
                "shipping": o.shipping,
                "tax": o.tax,
                "total": o.total,
                "shipping_status": o.shipping_status,
                "estimated_delivery": o.estimated_delivery,
                "items": [
                    {
                        "card_name": item.card_name,
                        "set_hint": item.set_hint,
                        "condition": item.condition,
                        "foil": item.foil,
                        "quantity": item.quantity,
                        "price": item.price,
                        "treatment": item.treatment,
                        "rarity_hint": item.rarity_hint,
                        "collector_number": item.collector_number,
                    }
                    for item in o.items
                ],
            })
        self._send_json(result)

    def _api_order_resolve(self):
        """Resolve parsed orders against local card database."""
        from mtg_collector.db.models import CardRepository, PrintingRepository, SetRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.services.order_parser import ParsedOrder, ParsedOrderItem
        from mtg_collector.services.order_resolver import resolve_orders

        data = self._read_json_body()
        if data is None:
            return

        # Reconstruct ParsedOrder objects from JSON
        orders = []
        for od in data.get("orders", []):
            order = ParsedOrder(
                order_number=od.get("order_number"),
                source=od.get("source", "tcgplayer"),
                seller_name=od.get("seller_name"),
                order_date=od.get("order_date"),
                subtotal=od.get("subtotal"),
                shipping=od.get("shipping"),
                tax=od.get("tax"),
                total=od.get("total"),
                shipping_status=od.get("shipping_status"),
                estimated_delivery=od.get("estimated_delivery"),
            )
            for item_d in od.get("items", []):
                order.items.append(ParsedOrderItem(
                    card_name=item_d["card_name"],
                    set_hint=item_d.get("set_hint"),
                    condition=item_d.get("condition", "Near Mint"),
                    foil=item_d.get("foil", False),
                    quantity=item_d.get("quantity", 1),
                    price=item_d.get("price"),
                    treatment=item_d.get("treatment"),
                    rarity_hint=item_d.get("rarity_hint"),
                    collector_number=item_d.get("collector_number"),
                ))
            orders.append(order)

        conn = self._get_conn()
        init_db(conn)

        card_repo = CardRepository(conn)
        set_repo = SetRepository(conn)
        printing_repo = PrintingRepository(conn)

        resolved = resolve_orders(orders, card_repo, set_repo, printing_repo)

        # Serialize
        result = []
        for ro in resolved:
            items = []
            for item in ro.items:
                items.append({
                    "card_name": item.card_name or item.parsed.card_name,
                    "parsed_name": item.parsed.card_name,
                    "set_hint": item.parsed.set_hint,
                    "set_code": item.set_code,
                    "collector_number": item.collector_number,
                    "printing_id": item.printing_id,
                    "image_uri": item.image_uri,
                    "condition": item.parsed.condition,
                    "foil": item.parsed.foil,
                    "quantity": item.parsed.quantity,
                    "price": item.parsed.price,
                    "treatment": item.parsed.treatment,
                    "rarity_hint": item.parsed.rarity_hint,
                    "error": item.error,
                    "resolved": item.printing_id is not None,
                })
            result.append({
                "order_number": ro.parsed.order_number,
                "source": ro.parsed.source,
                "seller_name": ro.parsed.seller_name,
                "order_date": ro.parsed.order_date,
                "subtotal": ro.parsed.subtotal,
                "shipping": ro.parsed.shipping,
                "tax": ro.parsed.tax,
                "total": ro.parsed.total,
                "shipping_status": ro.parsed.shipping_status,
                "estimated_delivery": ro.parsed.estimated_delivery,
                "items": items,
            })

        conn.close()
        self._send_json(result)

    def _api_order_commit(self):
        """Commit resolved orders to the database."""
        from mtg_collector.db.models import (
            CollectionRepository,
            OrderRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.services.order_parser import ParsedOrder, ParsedOrderItem
        from mtg_collector.services.order_resolver import (
            ResolvedItem,
            ResolvedOrder,
            commit_orders,
        )

        data = self._read_json_body()
        if data is None:
            return

        status = data.get("status", "ordered")
        source = data.get("source", "order_import")

        # Reconstruct ResolvedOrder objects
        resolved_orders = []
        for od in data.get("orders", []):
            parsed = ParsedOrder(
                order_number=od.get("order_number"),
                source=od.get("source", "tcgplayer"),
                seller_name=od.get("seller_name"),
                order_date=od.get("order_date"),
                subtotal=od.get("subtotal"),
                shipping=od.get("shipping"),
                tax=od.get("tax"),
                total=od.get("total"),
                shipping_status=od.get("shipping_status"),
                estimated_delivery=od.get("estimated_delivery"),
            )
            ro = ResolvedOrder(parsed=parsed)
            for item_d in od.get("items", []):
                parsed_item = ParsedOrderItem(
                    card_name=item_d.get("parsed_name", item_d["card_name"]),
                    set_hint=item_d.get("set_hint"),
                    condition=item_d.get("condition", "Near Mint"),
                    foil=item_d.get("foil", False),
                    quantity=item_d.get("quantity", 1),
                    price=item_d.get("price"),
                    treatment=item_d.get("treatment"),
                    rarity_hint=item_d.get("rarity_hint"),
                    collector_number=item_d.get("collector_number"),
                )
                ri = ResolvedItem(
                    parsed=parsed_item,
                    printing_id=item_d.get("printing_id"),
                    card_name=item_d.get("card_name"),
                    set_code=item_d.get("set_code"),
                    collector_number=item_d.get("collector_number"),
                    image_uri=item_d.get("image_uri"),
                    error=item_d.get("error"),
                )
                ro.items.append(ri)
            resolved_orders.append(ro)

        conn = self._get_conn()
        try:
            init_db(conn)
            collection_repo = CollectionRepository(conn)
            order_repo = OrderRepository(conn)

            from mtg_collector.db.models import BatchRepository
            batch_repo = BatchRepository(conn)

            summary = commit_orders(
                resolved_orders, order_repo, collection_repo, conn,
                status=status, source=source, batch_repo=batch_repo,
            )

            # Optional deck/binder assignment for newly added cards
            assign_target = data.get("assign_target", "")
            if assign_target and summary.get("collection_ids"):
                from mtg_collector.db.models import BinderRepository, DeckRepository
                cids = summary["collection_ids"]
                if assign_target.startswith("deck:"):
                    did = int(assign_target.split(":")[1])
                    zone = data.get("assign_zone", "mainboard")
                    DeckRepository(conn).add_cards(did, cids, zone=zone)
                elif assign_target.startswith("binder:"):
                    bid = int(assign_target.split(":")[1])
                    BinderRepository(conn).add_cards(bid, cids)
                conn.commit()
        finally:
            conn.close()
        self._send_json(summary)

    def _api_collection_history(self, collection_id: int):
        """Return combined status + movement history for a collection entry."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        init_db(conn)
        repo = CollectionRepository(conn)

        # Status history
        status_rows = conn.execute(
            "SELECT * FROM status_log WHERE collection_id = ? ORDER BY changed_at, id",
            (collection_id,),
        ).fetchall()
        status_history = [
            {"type": "status", "id": r["id"], "collection_id": r["collection_id"],
             "from_status": r["from_status"], "to_status": r["to_status"],
             "changed_at": r["changed_at"], "note": r["note"]}
            for r in status_rows
        ]

        # Movement history
        movement_history = [
            dict(row, type="movement")
            for row in repo.get_movement_history(collection_id)
        ]

        # Combined chronological
        combined = sorted(
            status_history + movement_history,
            key=lambda x: (x["changed_at"], x["id"]),
        )

        conn.close()
        self._send_json({
            "status_history": status_history,
            "movement_history": movement_history,
            "combined": combined,
        })

    def _api_collection_copies(self, params: dict):
        """Return individual collection rows for a printing, with order data."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db
        printing_id = params.get("printing_id", [""])[0]
        if not printing_id:
            self._send_json({"error": "printing_id required"}, 400)
            return
        finish = params.get("finish", [""])[0] or None
        condition = params.get("condition", [""])[0] or None
        status = params.get("status", [""])[0] or None
        conn = self._get_conn()
        init_db(conn)
        repo = CollectionRepository(conn)
        copies = repo.get_copies(printing_id, finish=finish, condition=condition, status=status)
        conn.close()
        self._send_json(copies)

    def _api_collection_receive(self, collection_id: int):
        """Receive a single ordered card (flip ordered -> owned)."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db
        conn = self._get_conn()
        try:
            init_db(conn)
            repo = CollectionRepository(conn)
            ok = repo.receive_card(collection_id)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"received": 1 if ok else 0})

    def _api_order_receive(self, order_id: int):
        """Mark ordered cards in an order as owned. Accepts optional card_ids in JSON body."""
        from mtg_collector.db.models import OrderRepository
        from mtg_collector.db.schema import init_db
        data = self._read_json_body()  # None when no body — backward-compatible
        card_ids = data.get("card_ids") if data else None
        conn = self._get_conn()
        try:
            init_db(conn)
            repo = OrderRepository(conn)
            count = repo.receive_order(order_id, card_ids=card_ids)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"received": count})

    # ── Corner Ingest API endpoints ──

    def _api_corners_detect(self):
        """Upload a photo, run Claude Vision corner detection, resolve cards."""
        if not _has_api_key():
            self._send_json({"error": "ANTHROPIC_API_KEY not set — corner detection requires an API key"}, 503)
            return
        from mtg_collector.cli.ingest_ids import RARITY_MAP, lookup_card
        from mtg_collector.db.models import PrintingRepository, SetRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.services.claude import ClaudeVision

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "Expected multipart/form-data"}, 400)
            return

        boundary = content_type.split("boundary=")[1].strip()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Extract the file from multipart
        file_content = None
        original_name = None
        parts = body.split(f"--{boundary}".encode())
        for part in parts:
            if not part or part.strip() == b"--" or part.strip() == b"":
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header_bytes = part[:header_end]
            data = part[header_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            header_str = header_bytes.decode("utf-8", errors="replace")
            filename_match = re.search(r'filename="([^"]+)"', header_str)
            if not filename_match:
                continue
            original_name = filename_match.group(1)
            ext = Path(original_name).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            file_content = data
            break

        if file_content is None:
            self._send_json({"error": "No image file found in upload"}, 400)
            return

        # Save to ingest images dir with timestamped name
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ext = Path(original_name).suffix.lower()
        stored_name = f"corners_{ts}{ext}"
        dest = _get_ingest_images_dir() / stored_name
        dest.write_bytes(file_content)
        image_key = stored_name

        _log_ingest(f"Corner detect: saved {original_name} as {stored_name}")

        # Run Claude Vision corner detection
        try:
            claude = ClaudeVision()
            detections, skipped = claude.read_card_corners(str(dest))
        except Exception as e:
            self._send_json({"error": f"Claude Vision error: {e}"}, 500)
            return

        if not detections and not skipped:
            self._send_json({"cards": [], "skipped": [], "errors": ["No card corners detected"], "image_key": image_key})
            return

        # Resolve each detection using local DB
        conn = self._get_conn()
        init_db(conn)

        set_repo = SetRepository(conn)
        printing_repo = PrintingRepository(conn)

        # Normalize set codes
        unique_sets = {}
        errors = []
        for d in detections:
            raw = d["set"]
            if raw.lower() not in unique_sets:
                normalized = set_repo.normalize_code(raw)
                if not normalized:
                    errors.append(f"Unknown set code: {raw} (run `mtg cache all` to populate)")
                    continue
                unique_sets[raw.lower()] = normalized

        # Resolve cards
        resolved_cards = []
        for d in detections:
            raw_set = d["set"]
            if raw_set.lower() not in unique_sets:
                continue
            set_code = unique_sets[raw_set.lower()]

            cn_raw = d["collector_number"]
            cn_stripped = cn_raw.lstrip("0") or "0"

            rarity_code = d.get("rarity", "C")
            if rarity_code not in RARITY_MAP:
                rarity_code = "C"
            rarity_expected = RARITY_MAP[rarity_code]

            card_data = lookup_card(set_code, cn_raw, cn_stripped, rarity_expected, printing_repo)
            if not card_data:
                if rarity_expected == "token":
                    errors.append(f"Token not found: {rarity_code} {cn_raw} in t{set_code} (run `mtg cache all` to refresh token data)")
                else:
                    errors.append(f"Card not found: {rarity_code} {cn_raw} {set_code.upper()} (run `mtg cache all` to populate)")
                continue

            # Extract image URI
            image_uri = None
            if "image_uris" in card_data:
                image_uri = card_data["image_uris"].get("normal") or card_data["image_uris"].get("small")
            elif "card_faces" in card_data and card_data["card_faces"]:
                face = card_data["card_faces"][0]
                if "image_uris" in face:
                    image_uri = face["image_uris"].get("normal") or face["image_uris"].get("small")

            resolved_cards.append({
                "printing_id": card_data["id"],
                "name": card_data.get("name", "Unknown"),
                "image_uri": image_uri,
                "set_code": set_code,
                "collector_number": card_data.get("collector_number", cn_raw),
                "rarity": card_data.get("rarity", rarity_expected),
                "foil": d.get("foil", False),
                "condition": "Near Mint",
            })

        # Check for Jumpstart face card (rarity "F") and look up deck theme
        jumpstart_info = None
        for d in detections:
            if d.get("rarity") == "F":
                raw_set = d["set"]
                if raw_set.lower() in unique_sets:
                    js_set = unique_sets[raw_set.lower()]
                    js_cn_raw = d["collector_number"]
                    js_cn_stripped = js_cn_raw.lstrip("0") or "0"
                    row = conn.execute(
                        """SELECT spc.source_name, sp.set_code, sp.name
                           FROM printings p
                           JOIN mtgjson_uuid_map um ON p.set_code = um.set_code AND p.collector_number = um.collector_number
                           JOIN sealed_product_cards spc ON um.uuid = spc.mtgjson_uuid
                           JOIN sealed_products sp ON spc.sealed_product_uuid = sp.uuid
                           WHERE p.set_code = ? AND p.collector_number IN (?, ?)
                             AND spc.source_type = 'deck' AND spc.source_name IS NOT NULL
                           LIMIT 1""",
                        (js_set, js_cn_raw, js_cn_stripped),
                    ).fetchone()
                    if row:
                        jumpstart_info = {
                            "set_code": row[1],
                            "theme": row[0],
                            "product_name": row[2],
                        }
                break  # first F card wins

        conn.close()

        _log_ingest(f"Corner detect: {len(resolved_cards)} resolved, {len(skipped)} skipped, {len(errors)} errors")

        result = {
            "cards": resolved_cards,
            "skipped": skipped,
            "errors": errors,
            "image_key": image_key,
        }
        if jumpstart_info:
            result["jumpstart"] = jumpstart_info

        self._send_json(result)

    def _api_corners_commit(self):
        """Commit reviewed corner-detected cards to collection."""
        from mtg_collector.db.models import (
            Batch,
            BatchRepository,
            CollectionEntry,
            CollectionRepository,
            DeckRepository,
            PrintingRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import (
            normalize_condition,
            normalize_finish,
            now_iso,
            store_source_image,
        )

        data = self._read_json_body()
        if data is None:
            return

        image_key = data.get("image_key")
        cards = data.get("cards", [])
        batch_uuid = data.get("batch_uuid")
        deck_id = data.get("deck_id")
        deck_zone = data.get("deck_zone", "mainboard")

        if not cards:
            self._send_json({"error": "No cards to commit"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            collection_repo = CollectionRepository(conn)
            printing_repo = PrintingRepository(conn)
            batch_repo = BatchRepository(conn)

            # Look up or create batch by UUID
            batch_id = None
            if batch_uuid:
                existing = batch_repo.get_by_uuid(batch_uuid)
                if existing:
                    batch_id = existing["id"]
                else:
                    batch_id = batch_repo.create(Batch(
                        id=None,
                        batch_uuid=batch_uuid,
                        batch_type="corner",
                        deck_id=deck_id if deck_id else None,
                        deck_zone=deck_zone if deck_id else None,
                    ))

            # Store source image permanently if image_key provided
            source_image = None
            if image_key:
                src_path = _get_ingest_images_dir() / image_key
                if src_path.exists():
                    source_image = store_source_image(str(src_path))

            added = []
            entry_ids = []
            for i, card in enumerate(cards):
                printing_id = card.get("printing_id")
                if not printing_id:
                    continue

                printing = printing_repo.get(printing_id)
                if not printing:
                    continue

                foil = card.get("foil", False)
                finish = normalize_finish("foil" if foil else "nonfoil")
                condition = normalize_condition(card.get("condition", "Near Mint"))

                entry = CollectionEntry(
                    id=None,
                    printing_id=printing_id,
                    finish=finish,
                    condition=condition,
                    source="corner_ingest",
                    source_image=source_image,
                    batch_id=batch_id,
                )
                entry_id = collection_repo.add(entry)
                entry_ids.append(entry_id)

                # Insert lineage record with batch_id
                md5 = _md5_file(str(_get_ingest_images_dir() / image_key)) if image_key else ""
                conn.execute(
                    """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, batch_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (entry_id, md5, image_key or "", i, batch_id, now_iso()),
                )

                name = "???"
                if printing.raw_json:
                    name = json.loads(printing.raw_json).get("name", "???")

                added.append({
                    "entry_id": entry_id,
                    "name": name,
                    "printing_id": printing_id,
                })

                _log_ingest(f"Corner commit: {name} ({printing.set_code.upper()} #{printing.collector_number}) -> collection ID {entry_id}")

            # Update batch card count
            if batch_id and entry_ids:
                batch_repo.increment_card_count(batch_id, len(entry_ids))

            # Assign cards to deck if requested
            if deck_id and entry_ids:
                deck_repo = DeckRepository(conn)
                try:
                    deck_repo.add_cards(int(deck_id), entry_ids, zone=deck_zone)
                except ValueError as e:
                    conn.rollback()
                    self._send_json({"error": str(e)}, 409)
                    return

            conn.commit()
        finally:
            conn.close()

        self._send_json({"added": added, "batch_id": batch_id})

    # ── Batch API endpoints ──

    def _api_batches_list(self, params=None):
        """List all batches with optional type filter."""
        from mtg_collector.db.models import BatchRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)
        repo = BatchRepository(conn)
        batch_type = None
        if params and "type" in params:
            batch_type = params["type"][0]
        self._send_json(repo.list_all(batch_type=batch_type))
        conn.close()

    def _api_batch_cards(self, batch_id: int):
        """Get cards in a batch."""
        from mtg_collector.db.models import BatchRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)
        repo = BatchRepository(conn)
        batch = repo.get(batch_id)
        if not batch:
            conn.close()
            self._send_json({"error": "Batch not found"}, 404)
            return
        cards = repo.get_cards(batch_id)
        conn.close()
        self._send_json({"batch": batch, "cards": cards})

    def _api_batch_assign_deck(self, batch_id: int, data: dict):
        """Retroactively assign a batch's cards to a deck."""
        from mtg_collector.db.models import (
            BatchRepository,
            DeckRepository,
        )
        from mtg_collector.db.schema import init_db

        deck_id = data.get("deck_id")
        deck_zone = data.get("deck_zone", "mainboard")
        if not deck_id:
            self._send_json({"error": "deck_id required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)
            batch_repo = BatchRepository(conn)
            deck_repo = DeckRepository(conn)

            batch = batch_repo.get(batch_id)
            if not batch:
                self._send_json({"error": "Batch not found"}, 404)
                return

            # Get collection IDs for this batch
            cards = batch_repo.get_cards(batch_id)
            collection_ids = [c["id"] for c in cards]

            if not collection_ids:
                self._send_json({"error": "No cards in batch"}, 400)
                return

            try:
                deck_repo.add_cards(int(deck_id), collection_ids, zone=deck_zone)
            except ValueError as e:
                self._send_json({"error": str(e)}, 409)
                return

            batch_repo.set_deck(batch_id, int(deck_id), deck_zone)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "assigned": len(collection_ids)})

    def _api_batch_update(self, batch_id: int, data: dict):
        """Update batch metadata (name, product_type, set_code, notes)."""
        from mtg_collector.db.models import BatchRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = BatchRepository(conn)

            batch = repo.get(batch_id)
            if not batch:
                self._send_json({"error": "Batch not found"}, 404)
                return

            updated = repo.update(
                batch_id,
                name=data.get("name", batch["name"]),
                product_type=data.get("product_type"),
                set_code=data.get("set_code"),
                notes=data.get("notes"),
            )
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "updated": updated})

    # ── Manual ID Ingest API endpoints ──

    def _api_ingest_ids_resolve(self):
        from mtg_collector.cli.ingest_ids import RARITY_MAP, lookup_card
        from mtg_collector.db.models import PrintingRepository, SetRepository
        from mtg_collector.db.schema import init_db

        data = self._read_json_body()
        if data is None:
            return
        entries = data.get("entries", [])
        if not entries:
            self._send_json({"error": "No entries provided"}, 400)
            return

        conn = self._get_conn()
        init_db(conn)
        set_repo = SetRepository(conn)
        printing_repo = PrintingRepository(conn)

        # Normalize set codes
        set_map = {}
        set_errors = []
        for e in entries:
            raw = e.get("set_code", "").strip()
            if raw.lower() not in set_map:
                normalized = set_repo.normalize_code(raw)
                if normalized:
                    set_map[raw.lower()] = normalized
                else:
                    set_errors.append({"set_code": raw, "error": f"Unknown set code '{raw}'"})
                    set_map[raw.lower()] = None

        resolved = []
        failed = []
        for idx, e in enumerate(entries):
            rarity_code = e.get("rarity", "").upper()
            if rarity_code not in RARITY_MAP:
                failed.append({"index": idx, **e, "error": f"Invalid rarity code '{rarity_code}'"})
                continue

            raw_set = e.get("set_code", "").strip()
            set_code = set_map.get(raw_set.lower())
            if not set_code:
                failed.append({"index": idx, **e, "error": f"Unknown set code '{raw_set}'"})
                continue

            cn_raw = e.get("collector_number", "").strip()
            cn_stripped = cn_raw.lstrip("0") or "0"
            rarity = RARITY_MAP[rarity_code]

            card_data = lookup_card(set_code, cn_raw, cn_stripped, rarity, printing_repo)
            if not card_data:
                failed.append({"index": idx, "rarity_code": rarity_code, "collector_number": cn_raw,
                              "set_code": raw_set, "foil": e.get("foil", False), "error": "Card not found (run `mtg cache all` to populate)"})
                continue

            actual_rarity = card_data.get("rarity", "")
            image_uris = card_data.get("image_uris") or {}
            if not image_uris and card_data.get("card_faces"):
                image_uris = card_data["card_faces"][0].get("image_uris", {})
            image_uri = image_uris.get("normal", image_uris.get("small", ""))

            resolved.append({
                "index": idx,
                "rarity_code": rarity_code,
                "rarity": rarity,
                "collector_number": card_data.get("collector_number", cn_raw),
                "set_code": set_code,
                "set_name": card_data.get("set_name", ""),
                "foil": e.get("foil", False),
                "printing_id": card_data["id"],
                "card_name": card_data.get("name", "Unknown"),
                "image_uri": image_uri,
                "actual_rarity": actual_rarity,
                "rarity_mismatch": rarity != "promo" and rarity != "token" and actual_rarity != rarity,
            })

        conn.close()
        self._send_json({"resolved": resolved, "failed": failed, "set_errors": set_errors})

    def _api_ingest_ids_commit(self):
        import uuid as _uuid

        from mtg_collector.db.models import (
            Batch,
            BatchRepository,
            CollectionEntry,
            CollectionRepository,
            PrintingRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import normalize_condition, normalize_finish

        data = self._read_json_body()
        if data is None:
            return
        cards = data.get("cards", [])
        condition = normalize_condition(data.get("condition", "Near Mint"))
        source = data.get("source", "manual_id")

        conn = self._get_conn()
        try:
            init_db(conn)
            collection_repo = CollectionRepository(conn)
            printing_repo = PrintingRepository(conn)

            # Optional batch support
            batch_id = None
            batch_name = data.get("batch_name")
            if batch_name:
                batch_repo = BatchRepository(conn)
                batch_id = batch_repo.create(Batch(
                    id=None,
                    batch_uuid=str(_uuid.uuid4()),
                    name=batch_name,
                    batch_type="manual_id",
                    product_type=data.get("product_type"),
                    set_code=data.get("batch_set_code"),
                ))

            added = 0
            collection_ids = []
            for card in cards:
                printing_id = card.get("printing_id")
                if not printing_id:
                    continue
                printing = printing_repo.get(printing_id)
                if not printing:
                    continue
                finish = normalize_finish("foil" if card.get("foil") else "nonfoil")
                entry = CollectionEntry(id=None, printing_id=printing_id, finish=finish,
                                       condition=condition, source=source, batch_id=batch_id)
                new_id = collection_repo.add(entry)
                collection_ids.append(new_id)
                added += 1

            # Update batch card count and complete
            if batch_id and collection_ids:
                batch_repo.increment_card_count(batch_id, len(collection_ids))
                batch_repo.complete(batch_id)

            conn.commit()

            # Optional deck/binder assignment
            assign_target = data.get("assign_target", "")
            if assign_target and collection_ids:
                from mtg_collector.db.models import BinderRepository, DeckRepository
                if assign_target.startswith("deck:"):
                    did = int(assign_target.split(":")[1])
                    DeckRepository(conn).add_cards(did, collection_ids, zone="mainboard")
                elif assign_target.startswith("binder:"):
                    bid = int(assign_target.split(":")[1])
                    BinderRepository(conn).add_cards(bid, collection_ids)
                conn.commit()
        finally:
            conn.close()
        self._send_json({"added": added, "failed": len(cards) - added})

    # ── CSV Import API endpoints ──

    def _api_import_parse(self):
        """Parse CSV text into structured rows."""
        import tempfile

        from mtg_collector.importers import detect_format, get_importer

        data = self._read_json_body()
        if data is None:
            return
        text = data.get("text", "").strip()
        fmt = data.get("format", "auto")

        if not text:
            self._send_json({"error": "No CSV text provided"}, 400)
            return

        # Write to temp file for existing importer to parse
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = tmp.name

        try:
            # Detect format
            if fmt == "auto":
                try:
                    fmt = detect_format(tmp_path)
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
                    return

            importer = get_importer(fmt)
            rows = importer.parse_file(tmp_path)

            # Extract lookup fields for each row
            parsed_rows = []
            for row in rows:
                name, set_code, cn, qty = importer.row_to_lookup(row)
                parsed_rows.append({
                    "name": name,
                    "set_code": set_code,
                    "collector_number": cn,
                    "quantity": qty,
                    "raw": row,
                })

            self._send_json({"format": fmt, "rows": parsed_rows, "total_rows": len(parsed_rows)})
        except Exception as e:
            self._send_json({"error": f"Failed to parse CSV: {e}"}, 400)
        finally:
            os.unlink(tmp_path)

    def _api_import_resolve(self):
        """Resolve parsed CSV rows using local DB."""
        from mtg_collector.db.models import CardRepository, PrintingRepository, SetRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.importers import get_importer

        data = self._read_json_body()
        if data is None:
            return
        fmt = data.get("format")
        rows = data.get("rows", [])

        if not fmt or not rows:
            self._send_json({"error": "Missing format or rows"}, 400)
            return

        importer = get_importer(fmt)
        conn = self._get_conn()
        init_db(conn)
        card_repo = CardRepository(conn)
        set_repo = SetRepository(conn)
        printing_repo = PrintingRepository(conn)

        resolved = []
        total = 0
        resolved_count = 0
        failed_count = 0

        for idx, row in enumerate(rows):
            name = row.get("name")
            set_code = row.get("set_code")
            cn = row.get("collector_number")
            qty = row.get("quantity", 1)
            total += 1

            printing_id = importer._resolve_card(card_repo, printing_repo, name, set_code, cn)
            if printing_id:
                printing = printing_repo.get(printing_id)
                card = card_repo.get(printing.oracle_id) if printing else None
                s = set_repo.get(printing.set_code) if printing else None
                image_uri = printing.image_uri or "" if printing else ""

                resolved.append({
                    "index": idx,
                    "name": card.name if card else name,
                    "set_code": printing.set_code if printing else set_code,
                    "set_name": s.set_name if s else "",
                    "collector_number": printing.collector_number if printing else cn,
                    "quantity": qty,
                    "printing_id": printing_id,
                    "image_uri": image_uri,
                    "resolved": True,
                    "error": None,
                    "raw": row.get("raw", {}),
                })
                resolved_count += 1
            else:
                resolved.append({
                    "index": idx,
                    "name": name,
                    "set_code": set_code,
                    "collector_number": cn,
                    "quantity": qty,
                    "printing_id": None,
                    "image_uri": "",
                    "resolved": False,
                    "error": f"Could not find: {name} ({set_code or 'any set'})",
                    "raw": row.get("raw", {}),
                })
                failed_count += 1

        conn.close()
        self._send_json({
            "resolved": resolved,
            "summary": {"total": total, "resolved": resolved_count, "failed": failed_count},
        })

    def _api_import_commit(self):
        """Commit resolved CSV import cards to the collection."""
        import uuid as _uuid

        from mtg_collector.db.models import Batch, BatchRepository, CollectionRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.importers import get_importer

        data = self._read_json_body()
        if data is None:
            return
        fmt = data.get("format")
        cards = data.get("cards", [])

        if not fmt or not cards:
            self._send_json({"error": "Missing format or cards"}, 400)
            return

        importer = get_importer(fmt)
        conn = self._get_conn()
        try:
            init_db(conn)
            collection_repo = CollectionRepository(conn)

            # Optional batch support
            batch_id = None
            batch_name = data.get("batch_name")
            if batch_name:
                batch_repo = BatchRepository(conn)
                batch_id = batch_repo.create(Batch(
                    id=None,
                    batch_uuid=str(_uuid.uuid4()),
                    name=batch_name,
                    batch_type="csv_import",
                    product_type=data.get("product_type"),
                    set_code=data.get("batch_set_code"),
                ))

            added = 0
            errors = []
            collection_ids = []
            for card in cards:
                printing_id = card.get("printing_id")
                raw = card.get("raw", {})
                qty = card.get("quantity", 1)
                if not printing_id:
                    continue
                try:
                    entry = importer.row_to_entry(raw, printing_id)
                    entry.batch_id = batch_id
                    for _ in range(qty):
                        new_id = collection_repo.add(entry)
                        collection_ids.append(new_id)
                        added += 1
                except Exception as e:
                    errors.append(f"Error adding {card.get('name', '?')}: {e}")

            # Update batch card count and complete
            if batch_id and collection_ids:
                batch_repo.increment_card_count(batch_id, len(collection_ids))
                batch_repo.complete(batch_id)

            conn.commit()

            # Optional deck/binder assignment
            assign_target = data.get("assign_target", "")
            if assign_target and collection_ids:
                from mtg_collector.db.models import BinderRepository, DeckRepository
                if assign_target.startswith("deck:"):
                    did = int(assign_target.split(":")[1])
                    DeckRepository(conn).add_cards(did, collection_ids, zone="mainboard")
                elif assign_target.startswith("binder:"):
                    bid = int(assign_target.split(":")[1])
                    BinderRepository(conn).add_cards(bid, collection_ids)
                conn.commit()
        finally:
            conn.close()
        self._send_json({"cards_added": added, "cards_skipped": len(cards) - added, "errors": errors})

    def _api_set_value_data(self, data):
        sets = data.get("sets", [])
        if not sets:
            self._send_json({"error": "Missing 'sets'"}, 400)
            return
        source = data.get("source", "tcgplayer")
        price_type = data.get("price_type", "normal")
        # CK prices are stored as buylist_normal/buylist_foil
        db_price_type = f"buylist_{price_type}" if source == "cardkingdom" else price_type
        placeholders = ",".join("?" for _ in sets)
        params = [source, db_price_type] + [s.lower() for s in sets]
        conn = self._get_conn()
        rows = conn.execute(
            f"""SELECT c.name, p.set_code, s.set_name, p.collector_number,
                       p.rarity, c.colors, lp.price,
                       p.finishes, p.frame_effects, p.border_color,
                       p.full_art, p.promo, p.promo_types,
                       (SELECT COUNT(*) FROM collection col
                        WHERE col.printing_id = p.printing_id) AS owned
                FROM printings p
                JOIN cards c ON p.oracle_id = c.oracle_id
                JOIN sets s ON p.set_code = s.set_code
                LEFT JOIN latest_prices lp
                    ON lp.set_code = p.set_code
                    AND lp.collector_number = p.collector_number
                    AND lp.source = ? AND lp.price_type = ?
                WHERE p.set_code IN ({placeholders})
                ORDER BY p.set_code, lp.price DESC""",
            params,
        ).fetchall()
        conn.close()
        result = [
            {
                "name": r["name"],
                "set_code": r["set_code"],
                "set_name": r["set_name"],
                "collector_number": r["collector_number"],
                "rarity": r["rarity"],
                "colors": r["colors"],
                "price": float(r["price"]) if r["price"] is not None else None,
                "finishes": r["finishes"],
                "frame_effects": r["frame_effects"],
                "border_color": r["border_color"],
                "full_art": r["full_art"],
                "promo": r["promo"],
                "promo_types": r["promo_types"],
                "owned": r["owned"],
            }
            for r in rows
        ]
        self._send_json(result)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        body = self.rfile.read(content_length)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return None

    # ===== Deck API handlers =====

    def _api_decks_list(self):
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        self._send_json(repo.list_all())
        conn.close()

    def _api_deck_by_origin(self, params: dict):
        set_code = params.get("set_code", [None])[0]
        theme = params.get("theme", [None])[0]
        if not set_code or not theme:
            self._send_json({"error": "set_code and theme are required"}, 400)
            return
        variation = params.get("variation", [None])[0]
        if variation is not None:
            variation = int(variation)
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        deck = repo.find_by_origin(set_code, theme, variation)
        conn.close()
        self._send_json(deck)

    # ---------- Precon / Jumpstart import picker ----------

    # MTGJSON deck types we expose. Jumpstart goes in its own kind because
    # of the variant grouping; everything else lives under "precon".
    _PRECON_TYPES = (
        "Commander Deck", "Theme Deck", "Intro Pack", "Planeswalker Deck",
        "Duel Deck", "Deck Builder's Toolkit", "Arena Starter Deck",
        "Welcome Deck", "Starter Kit", "Box Set",
    )
    _JUMPSTART_TYPES = ("Jumpstart",)

    def _precon_kind_types(self, kind: str) -> tuple:
        if kind == "jumpstart":
            return self._JUMPSTART_TYPES
        return self._PRECON_TYPES

    def _api_precons_sets(self, params: dict):
        """List sets that have decks of the requested kind, with deck counts.

        Query params: kind=jumpstart|precon (default: precon)
        """
        kind = params.get("kind", ["precon"])[0]
        types = self._precon_kind_types(kind)
        placeholders = ",".join("?" * len(types))
        conn = self._get_conn()
        rows = conn.execute(
            f"""SELECT d.set_code, COALESCE(s.set_name, d.set_code) AS set_name,
                       COUNT(*) AS deck_count
                FROM mtgjson_decks d
                LEFT JOIN sets s ON s.set_code = d.set_code
                WHERE d.type IN ({placeholders})
                GROUP BY d.set_code
                ORDER BY MAX(d.release_date) DESC, set_name""",
            types,
        ).fetchall()
        conn.close()
        self._send_json([dict(r) for r in rows])

    def _api_precons_decks(self, params: dict):
        """List decks in a set, grouped by base_name for jumpstart.

        Query params: set_code=X (required), kind=jumpstart|precon (default: precon)
        """
        set_code = params.get("set_code", [None])[0]
        if not set_code:
            self._send_json({"error": "set_code is required"}, 400)
            return
        kind = params.get("kind", ["precon"])[0]
        types = self._precon_kind_types(kind)
        placeholders = ",".join("?" * len(types))
        conn = self._get_conn()
        rows = conn.execute(
            f"""SELECT name, base_name, variation, type, main_count, release_date
                FROM mtgjson_decks
                WHERE set_code = ? AND type IN ({placeholders})
                ORDER BY base_name, variation, name""",
            (set_code.lower(), *types),
        ).fetchall()
        conn.close()

        if kind == "jumpstart":
            # Group siblings under the same base_name.
            groups = {}
            order = []
            for r in rows:
                key = r["base_name"]
                if key not in groups:
                    groups[key] = {
                        "base_name": key,
                        "type": r["type"],
                        "variations": [],
                    }
                    order.append(key)
                groups[key]["variations"].append({
                    "name": r["name"],
                    "variation": r["variation"],
                    "main_count": r["main_count"],
                })
            self._send_json([groups[k] for k in order])
        else:
            self._send_json([
                {
                    "name": r["name"],
                    "type": r["type"],
                    "main_count": r["main_count"],
                    "release_date": r["release_date"],
                }
                for r in rows
            ])

    def _api_precons_import(self, data: dict):
        """Create a new deck from a known MTGJSON decklist.

        Body: {set_code, deck_name, custom_name?, sleeve_color?, deck_box?, storage_location?, state?}

        Always populates deck_expected_cards from the MTGJSON deck data.
        UUIDs that can't be resolved to a local printing are reported in
        the response under `unresolved` but do not abort the import — the
        user can populate those cards manually or run `mtg cache all`.
        """
        set_code = (data.get("set_code") or "").lower()
        deck_name = data.get("deck_name")
        if not set_code or not deck_name:
            self._send_json(
                {"error": "set_code and deck_name are required"}, 400)
            return

        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT set_code, name, base_name, variation, type, deck_data
                   FROM mtgjson_decks WHERE set_code = ? AND name = ?""",
                (set_code, deck_name),
            ).fetchone()
            if not row:
                self._send_json(
                    {"error": f"No MTGJSON deck '{deck_name}' in set {set_code}"},
                    404)
                return

            set_name_row = conn.execute(
                "SELECT set_name FROM sets WHERE set_code = ?", (set_code,)
            ).fetchone()
            set_name = set_name_row["set_name"] if set_name_row else set_code.upper()

            zones = json.loads(row["deck_data"])
            # Resolve each UUID through mtgjson_uuid_map → printings.
            uuids = []
            for zone in ("mainBoard", "sideBoard", "commander"):
                for c in zones.get(zone, []):
                    uuids.append((zone, c["uuid"], c.get("count", 1)))

            if uuids:
                placeholders = ",".join("?" * len(uuids))
                resolved = conn.execute(
                    f"""SELECT m.uuid, p.printing_id
                        FROM mtgjson_uuid_map m
                        JOIN printings p ON p.set_code = m.set_code
                                        AND p.collector_number = m.collector_number
                        WHERE m.uuid IN ({placeholders})""",
                    [u[1] for u in uuids],
                ).fetchall()
                uuid_to_pid = {r["uuid"]: r["printing_id"] for r in resolved}
            else:
                uuid_to_pid = {}

            ZONE_MAP = {"mainBoard": "mainboard", "sideBoard": "sideboard",
                        "commander": "commander"}
            expected = []
            unresolved = []
            for zone, uuid, count in uuids:
                pid = uuid_to_pid.get(uuid)
                if pid is None:
                    unresolved.append({"zone": zone, "uuid": uuid, "count": count})
                    continue
                expected.append({
                    "printing_id": pid,
                    "zone": ZONE_MAP[zone],
                    "quantity": count,
                })

            # Build deck record.
            from mtg_collector.db.models import Deck, DeckRepository
            repo = DeckRepository(conn)
            base_name = row["base_name"]
            variation = row["variation"]
            deck_type = row["type"] or ""
            is_jumpstart = "jumpstart" in deck_type.lower()
            default_label = f"{deck_name} ({set_name})"
            name = (data.get("custom_name") or "").strip() or default_label
            fmt = data.get("format")
            if not fmt and is_jumpstart:
                fmt = "jumpstart"
            elif not fmt and "commander" in deck_type.lower():
                fmt = "commander"
            deck = Deck(
                id=None,
                name=name,
                description=data.get("description") or deck_type or None,
                format=fmt,
                is_precon=True,
                sleeve_color=data.get("sleeve_color"),
                deck_box=data.get("deck_box"),
                storage_location=data.get("storage_location"),
                origin_set_code=set_code,
                origin_theme=base_name,
                origin_variation=variation,
                state_id=self._resolve_state_id(data.get("state", "idea")),
            )
            deck_id = repo.add(deck)
            if expected:
                repo.set_expected_cards(deck_id, expected)
            conn.commit()
            created = repo.get(deck_id)
        finally:
            conn.close()

        self._send_json({
            "deck": created,
            "expected_count": len(expected),
            "unresolved": unresolved,
        }, 201)

    def _api_deck_get(self, deck_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        deck = repo.get(deck_id)
        conn.close()
        if deck is None:
            self._send_json({"error": "Deck not found"}, 404)
            return
        self._send_json(deck)

    @staticmethod
    def _resolve_state_id(state_name: str) -> int:
        from mtg_collector.db.models import DECK_STATE_IDEA, STATE_NAME_TO_ID
        return STATE_NAME_TO_ID.get(state_name, DECK_STATE_IDEA)

    def _api_deck_create(self, data: dict):
        name = data.get("name")
        if not name:
            self._send_json({"error": "name is required"}, 400)
            return
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import Deck, DeckRepository
            repo = DeckRepository(conn)
            origin_var = data.get("origin_variation")
            if origin_var is not None:
                origin_var = int(origin_var)
            deck = Deck(
                id=None, name=name, description=data.get("description"),
                format=data.get("format"), is_precon=bool(data.get("is_precon")),
                sleeve_color=data.get("sleeve_color"), deck_box=data.get("deck_box"),
                storage_location=data.get("storage_location"),
                origin_set_code=data.get("origin_set_code"),
                origin_theme=data.get("origin_theme"),
                origin_variation=origin_var,
                state_id=self._resolve_state_id(data.get("state", "idea")),
            )
            deck_id = repo.add(deck)
            conn.commit()
            result = repo.get(deck_id)
        finally:
            conn.close()
        self._send_json(result, 201)

    def _api_deck_update(self, deck_id: int, data: dict):
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            if not repo.get(deck_id):
                self._send_json({"error": "Deck not found"}, 404)
                return
            if "state" in data:
                data["state_id"] = self._resolve_state_id(data.pop("state"))
            repo.update(deck_id, data)
            conn.commit()
            result = repo.get(deck_id)
        finally:
            conn.close()
        self._send_json(result)

    def _api_deck_delete(self, deck_id: int):
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            if not repo.delete(deck_id):
                self._send_json({"error": "Deck not found"}, 404)
                return
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_deck_cards(self, deck_id: int, params: dict):
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        zone = params.get("zone", [None])[0]
        cards = repo.get_cards_for_state(deck_id, zone=zone)

        for card in cards:
            card["layout"] = card.get("layout") or "normal"
            card["tcg_price"] = None
            card["ck_price"] = None
            card["ck_url"] = ""

        # Bulk price lookup
        if cards:
            price_keys = []
            for card in cards:
                finishes = json.loads(card["finishes"]) if card.get("finishes") else []
                price_type = "normal" if "nonfoil" in finishes else "foil"
                sc = card["set_code"].lower()
                cn = card["collector_number"]
                price_keys.append((sc, cn, price_type))

            unique_cards = list({(sc, cn) for sc, cn, _ in price_keys})
            ph = ",".join("(?,?)" for _ in unique_cards)
            params_q = [v for pair in unique_cards for v in pair]
            price_map: dict = {}
            for r in conn.execute(
                f"SELECT set_code, collector_number, source, price_type, price "
                f"FROM latest_prices WHERE (set_code, collector_number) IN ({ph})",
                params_q,
            ).fetchall():
                price_map[(r["set_code"], r["collector_number"], r["source"], r["price_type"])] = str(r["price"])

            # Bulk CK URL lookup
            ck_url_map: dict = {}
            if self.generator:
                pids = [card["printing_id"] for card in cards]
                ph2 = ",".join("?" for _ in pids)
                # One row per printing_id, or the dict below keeps whichever face
                # the scan returned last — which is the back face, and a different
                # Card Kingdom link from the one /api/collection shows.
                for r in conn.execute(
                    front_face_bulk_sql("mp.printing_id, mp.ck_url, mp.ck_url_foil", ph2),
                    pids,
                ).fetchall():
                    ck_url_map[r["printing_id"]] = (r["ck_url"] or "", r["ck_url_foil"] or "")

            for i, card in enumerate(cards):
                sc, cn, pt = price_keys[i]
                card["ck_price"] = price_map.get((sc, cn, "cardkingdom", f"buylist_{pt}")) or price_map.get((sc, cn, "cardkingdom", pt))
                card["tcg_price"] = price_map.get((sc, cn, "tcgplayer", pt))
                foil = card["finish"] in ("foil", "etched")
                urls = ck_url_map.get(card["printing_id"], ("", ""))
                card["ck_url"] = (urls[1] if foil else urls[0]) or urls[0]

        conn.close()
        self._send_json(cards)

    def _api_deck_add_cards(self, deck_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        zone = data.get("zone", "mainboard")
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            count = repo.add_cards(deck_id, collection_ids, zone=zone)
            conn.commit()
        except ValueError as e:
            self._send_json({"error": str(e)}, 409)
            return
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_deck_remove_cards(self, deck_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            count = repo.remove_cards(deck_id, collection_ids)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_deck_adjust_quantity(self, deck_id: int, data: dict):
        """Adjust card quantity by +1 or -1. Works for all deck states."""
        printing_id = data.get("printing_id")
        zone = data.get("zone", "mainboard")
        delta = data.get("delta")
        if not printing_id or delta not in (1, -1):
            self._send_json({"error": "printing_id and delta (+1/-1) required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            result = repo.adjust_card_quantity(deck_id, printing_id, zone, delta)
            conn.commit()
        except (ValueError, Exception) as e:
            conn.close()
            code = 409 if isinstance(e, ValueError) else 500
            self._send_json({"error": str(e)}, code)
            return
        conn.close()
        self._send_json(result)

    def _api_deck_move_cards(self, deck_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        zone = data.get("zone", "mainboard")
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            count = repo.move_cards(collection_ids, deck_id, zone=zone)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_deck_expected_get(self, deck_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        cards = repo.get_expected_cards(deck_id)
        conn.close()
        self._send_json(cards)

    def _api_deck_expected_set(self, deck_id: int, data: dict):
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            if not repo.get(deck_id):
                self._send_json({"error": "Deck not found"}, 404)
                return

            if "decklist" in data:
                # Parse text decklist and resolve to printing_ids
                from mtg_collector.db.models import CardRepository, PrintingRepository
                from mtg_collector.importers.decklist import parse_line
                card_repo = CardRepository(conn)
                printing_repo = PrintingRepository(conn)
                lines = data["decklist"].strip().split("\n")
                cards = []
                errors = []
                for i, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = parse_line(line, i)
                    except ValueError as e:
                        errors.append(str(e))
                        continue
                    name = parsed["Name"]
                    set_code = (parsed.get("Edition") or "").strip().lower() or None
                    cn = parsed.get("Collector Number") or None
                    qty = int(parsed.get("Count", 1))
                    # Resolve card: try set+CN first, then name lookup
                    printing_id = None
                    if set_code and cn:
                        p = printing_repo.get_by_set_cn(set_code, cn)
                        if p:
                            printing_id = p.printing_id
                    if not printing_id:
                        card = card_repo.get_by_name(name) or card_repo.search_by_name(name)
                        if card:
                            # Prefer owned printing, fallback to most recent non-digital
                            owned = conn.execute(
                                """SELECT p.printing_id FROM collection col
                                   JOIN printings p ON col.printing_id = p.printing_id
                                   JOIN sets s ON p.set_code = s.set_code
                                   WHERE p.oracle_id = ? AND col.status = 'owned'
                                   ORDER BY s.released_at DESC LIMIT 1""",
                                (card.oracle_id,),
                            ).fetchone()
                            if owned:
                                printing_id = owned[0]
                            else:
                                printings = printing_repo.get_by_oracle_id(card.oracle_id)
                                if printings:
                                    printing_id = printings[0].printing_id
                    if not printing_id:
                        errors.append(f"Line {i}: card not found: {name}")
                        continue
                    cards.append({
                        "printing_id": printing_id,
                        "zone": "mainboard",
                        "quantity": qty,
                    })
                if errors:
                    self._send_json({"error": "Some cards could not be resolved",
                                     "details": errors}, 400)
                    return
                count = repo.set_expected_cards(deck_id, cards)
            elif "cards" in data:
                count = repo.set_expected_cards(deck_id, data["cards"])
            else:
                self._send_json({"error": "Provide 'cards' or 'decklist'"}, 400)
                return

            conn.commit()
            result = repo.get_expected_cards(deck_id)
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count, "cards": result})

    def _api_deck_expected_add(self, deck_id: int, data: dict):
        """Add cards to an idea/ready deck's expected list by printing_id."""
        printing_ids = data.get("printing_ids", [])
        zone = data.get("zone", "mainboard")
        if not printing_ids:
            self._send_json({"error": "printing_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            count = repo.add_expected_cards(deck_id, printing_ids, zone)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_deck_expected_remove(self, deck_id: int, data: dict):
        """Remove entries from a deck's expected list.

        Accepts either a specific printing_id, or an oracle_id + zone to
        drop every printing of that card in the given zone (used by the
        completeness UI, which groups by oracle_id).
        """
        printing_id = data.get("printing_id")
        oracle_id = data.get("oracle_id")
        zone = data.get("zone", "mainboard")
        if not printing_id and not oracle_id:
            self._send_json(
                {"error": "printing_id or oracle_id is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        try:
            if printing_id:
                count = repo.remove_expected_cards(deck_id, [printing_id])
            else:
                count = repo.remove_expected_cards_by_oracle(
                    deck_id, oracle_id, zone)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "removed": count})

    def _api_printings_by_oracle(self, oracle_id: str):
        """Return all printings for an oracle_id with set name and owned count."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT p.printing_id, p.oracle_id, p.set_code,
                      p.collector_number, p.rarity, p.image_uri,
                      s.set_name,
                      (SELECT COUNT(*) FROM collection c
                       WHERE c.printing_id = p.printing_id
                       AND c.status = 'owned') as owned_count
               FROM printings p
               JOIN sets s ON p.set_code = s.set_code
               WHERE p.oracle_id = ? AND s.digital = 0
               ORDER BY s.released_at DESC, p.collector_number""",
            (oracle_id,),
        ).fetchall()
        conn.close()
        self._send_json([dict(r) for r in rows])

    def _api_deck_expected_swap(self, deck_id: int, data: dict):
        """Swap one printing for another in a deck's expected list."""
        old_pid = data.get("old_printing_id")
        new_pid = data.get("new_printing_id")
        if not old_pid or not new_pid:
            self._send_json(
                {"error": "old_printing_id and new_printing_id required"}, 400)
            return
        conn = self._get_conn()
        try:
            old = conn.execute(
                "SELECT oracle_id FROM printings WHERE printing_id = ?",
                (old_pid,),
            ).fetchone()
            new = conn.execute(
                "SELECT oracle_id FROM printings WHERE printing_id = ?",
                (new_pid,),
            ).fetchone()
            if not old or not new:
                self._send_json({"error": "Printing not found"}, 404)
                return
            if old["oracle_id"] != new["oracle_id"]:
                self._send_json(
                    {"error": "Printings must be the same card"}, 400)
                return
            row = conn.execute(
                "SELECT zone, quantity FROM deck_expected_cards "
                "WHERE deck_id = ? AND printing_id = ?",
                (deck_id, old_pid),
            ).fetchone()
            if not row:
                self._send_json({"error": "Card not in expected list"}, 404)
                return
            zone, quantity = row["zone"], row["quantity"]
            conn.execute(
                "DELETE FROM deck_expected_cards "
                "WHERE deck_id = ? AND printing_id = ?",
                (deck_id, old_pid),
            )
            conn.execute(
                "INSERT OR REPLACE INTO deck_expected_cards "
                "(deck_id, printing_id, zone, quantity) VALUES (?, ?, ?, ?)",
                (deck_id, new_pid, zone, quantity),
            )
            conn.execute(
                "DELETE FROM deck_cards "
                "WHERE deck_id = ? AND printing_id = ? "
                "AND collection_id IS NULL",
                (deck_id, old_pid),
            )
            conn.execute(
                "INSERT INTO deck_cards "
                "(deck_id, printing_id, collection_id, zone, quantity) "
                "VALUES (?, ?, NULL, ?, ?)",
                (deck_id, new_pid, zone, quantity),
            )
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_deck_completeness(self, deck_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        if not repo.get(deck_id):
            conn.close()
            self._send_json({"error": "Deck not found"}, 404)
            return
        result = repo.get_deck_completeness(deck_id)
        conn.close()
        self._send_json(result)

    def _api_deck_materialize(self, deck_id: int):
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            deck = repo.get(deck_id)
            if not deck:
                self._send_json({"error": "Deck not found"}, 404)
                return
            from mtg_collector.db.models import DECK_STATE_CONSTRUCTED
            if deck["state_id"] == DECK_STATE_CONSTRUCTED:
                self._send_json({"error": "Deck is already constructed"}, 400)
                return
            result = repo.materialize_deck(deck_id)
            conn.commit()
        finally:
            conn.close()
        self._send_json(result)

    def _api_deck_reassemble(self, deck_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            if not repo.get(deck_id):
                self._send_json({"error": "Deck not found"}, 404)
                return
            count = repo.move_cards(collection_ids, deck_id, zone="mainboard")
            conn.commit()
            result = repo.get_deck_completeness(deck_id)
        finally:
            conn.close()
        self._send_json({"ok": True, "moved": count, "completeness": result})

    # ===== Deck Builder API handlers =====

    def _api_builder_commanders(self, params: dict):
        """Autocomplete legendary creatures from collection."""
        q = params.get("q", [""])[0].strip()
        if len(q) < 2:
            self._send_json([])
            return
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT DISTINCT c.oracle_id, c.name, c.mana_cost, c.color_identity,
                      p.printing_id, p.image_uri, p.set_code, p.collector_number
               FROM cards c
               JOIN printings p ON p.oracle_id = c.oracle_id
               JOIN collection col ON col.printing_id = p.printing_id
               WHERE ((c.type_line LIKE '%Legendary%' AND c.type_line LIKE '%Creature%')
                  OR c.oracle_text LIKE '%can be your commander%')
               AND c.name LIKE ?
               AND col.status = 'owned'
               ORDER BY c.name
               LIMIT 20""",
            (f"%{q}%",),
        ).fetchall()
        conn.close()
        seen = set()
        results = []
        for r in rows:
            if r["oracle_id"] in seen:
                continue
            seen.add(r["oracle_id"])
            results.append({
                "oracle_id": r["oracle_id"],
                "name": r["name"],
                "mana_cost": r["mana_cost"],
                "color_identity": r["color_identity"],
                "printing_id": r["printing_id"],
                "image_uri": r["image_uri"],
                "set_code": r["set_code"],
                "collector_number": r["collector_number"],
            })
        self._send_json(results)

    def _api_builder_create(self, data: dict):
        """Create a new commander deck."""
        commander_oracle_id = data.get("commander_oracle_id")
        if not commander_oracle_id:
            self._send_json({"error": "commander_oracle_id is required"}, 400)
            return
        conn = self._get_conn()
        try:
            card = conn.execute("SELECT name FROM cards WHERE oracle_id = ?",
                                (commander_oracle_id,)).fetchone()
            if not card:
                self._send_json({"error": "Commander not found"}, 404)
                return
            from mtg_collector.db.models import DECK_STATE_CONSTRUCTED
            state_id = self._resolve_state_id(data.get("state", "idea"))
            if state_id != DECK_STATE_CONSTRUCTED:
                # Use DeckBuilderService for idea/ready decks to pre-populate
                # template role categories (Lands, Ramp, etc.)
                from mtg_collector.services.deck_builder import DeckBuilderService
                svc = DeckBuilderService(conn)
                try:
                    result = svc.create_deck(commander_oracle_id)
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400)
                    return
            else:
                from mtg_collector.db.models import Deck, DeckRepository
                repo = DeckRepository(conn)
                deck_name = data.get("name") or card["name"]
                deck = Deck(
                    id=None, name=deck_name, format="commander",
                    state_id=DECK_STATE_CONSTRUCTED,
                    commander_oracle_id=commander_oracle_id,
                    commander_printing_id=data.get("commander_printing_id"),
                )
                deck_id = repo.add(deck)
                conn.commit()
                result = repo.get(deck_id)
        finally:
            conn.close()
        self._send_json(result, 201)

    def _categorize_card_type(self, type_line: str) -> str:
        """Categorize a card by its type line, priority order."""
        if not type_line:
            return "Other"
        tl = type_line.lower()
        if "creature" in tl:
            return "Creatures"
        if "planeswalker" in tl:
            return "Planeswalkers"
        if "instant" in tl:
            return "Instants"
        if "sorcery" in tl:
            return "Sorceries"
        if "enchantment" in tl:
            return "Enchantments"
        if "artifact" in tl:
            return "Artifacts"
        if "land" in tl:
            return "Lands"
        return "Other"

    def _api_builder_get(self, deck_id: int):
        """Get deck data with commander info and type-grouped cards."""
        conn = self._get_conn()
        from mtg_collector.db.models import DeckRepository
        repo = DeckRepository(conn)
        deck = repo.get(deck_id)
        if not deck:
            conn.close()
            self._send_json({"error": "Deck not found"}, 404)
            return
        # Get commander info
        commander = None
        commander_pid = deck.get("commander_printing_id")
        commander_oid = deck.get("commander_oracle_id")
        if commander_pid:
            row = conn.execute(
                """SELECT c.oracle_id, c.name, c.mana_cost, c.color_identity, c.type_line,
                          p.printing_id, p.image_uri, p.set_code, p.collector_number
                   FROM printings p
                   JOIN cards c ON c.oracle_id = p.oracle_id
                   WHERE p.printing_id = ?""",
                (commander_pid,),
            ).fetchone()
            if row:
                commander = dict(row)
        elif commander_oid:
            row = conn.execute(
                """SELECT c.oracle_id, c.name, c.mana_cost, c.color_identity, c.type_line,
                          p.printing_id, p.image_uri, p.set_code, p.collector_number
                   FROM cards c
                   JOIN printings p ON p.oracle_id = c.oracle_id
                   WHERE c.oracle_id = ?
                   LIMIT 1""",
                (commander_oid,),
            ).fetchone()
            if row:
                commander = dict(row)
        # Get deck cards grouped by type, collapsed by printing_id
        cards = repo.get_cards_for_state(deck_id)
        groups = {}
        type_order = ["Creatures", "Planeswalkers", "Instants", "Sorceries",
                      "Enchantments", "Artifacts", "Lands", "Other"]
        for c in cards:
            cat = self._categorize_card_type(c.get("type_line", ""))
            group = groups.setdefault(cat, {})
            pid = c.get("printing_id", c["id"])
            if pid in group:
                group[pid]["quantity"] += 1
                group[pid]["collection_ids"].append(c["id"])
            else:
                entry = dict(c)
                entry["quantity"] = c.get("quantity") or 1
                entry["collection_ids"] = [c["id"]]
                group[pid] = entry
        ordered_groups = {}
        for t in type_order:
            if t in groups:
                ordered_groups[t] = list(groups[t].values())
        conn.close()
        self._send_json({
            "deck": deck,
            "commander": commander,
            "groups": ordered_groups,
        })

    def _api_builder_search(self, deck_id: int, params: dict):
        """Search owned cards filtered by commander color identity."""
        q = params.get("q", [""])[0].strip()
        if len(q) < 2:
            self._send_json([])
            return
        conn = self._get_conn()
        deck = conn.execute("SELECT commander_oracle_id, state_id FROM decks WHERE id = ?",
                            (deck_id,)).fetchone()
        if not deck:
            conn.close()
            self._send_json({"error": "Deck not found"}, 404)
            return
        # Get commander color identity for filtering
        cmd_colors = []
        if deck["commander_oracle_id"]:
            row = conn.execute("SELECT color_identity FROM cards WHERE oracle_id = ?",
                               (deck["commander_oracle_id"],)).fetchone()
            if row and row["color_identity"]:
                cmd_colors = json.loads(row["color_identity"]) if isinstance(row["color_identity"], str) else row["color_identity"]
        # Get IDs already in this deck
        from mtg_collector.db.models import DECK_STATE_CONSTRUCTED
        if deck["state_id"] != DECK_STATE_CONSTRUCTED:
            in_deck = {r["printing_id"] for r in conn.execute(
                "SELECT printing_id FROM deck_expected_cards WHERE deck_id = ?", (deck_id,)
            ).fetchall()}
        else:
            in_deck = {r["printing_id"] for r in conn.execute(
                "SELECT printing_id FROM deck_cards WHERE deck_id = ?", (deck_id,)
            ).fetchall()}
        # Search owned cards matching color identity
        search = f"%{q}%"
        if deck["state_id"] != DECK_STATE_CONSTRUCTED:
            # Idea/Ready: search all owned cards regardless of deck assignment
            rows = conn.execute(
                """SELECT col.id, col.printing_id, col.finish, col.condition,
                          p.set_code, p.collector_number, p.rarity, p.image_uri,
                          c.name, c.type_line, c.mana_cost, c.cmc,
                          c.color_identity, c.oracle_id
                   FROM collection col
                   JOIN printings p ON col.printing_id = p.printing_id
                   JOIN cards c ON p.oracle_id = c.oracle_id
                   WHERE col.status = 'owned'
                     AND (c.name LIKE ? OR c.type_line LIKE ? OR c.oracle_text LIKE ?)
                   ORDER BY c.name
                   LIMIT 50""",
                (search, search, search),
            ).fetchall()
        else:
            # Physical: only cards not already in a constructed deck or binder
            rows = conn.execute(
                """SELECT col.id, col.printing_id, col.finish, col.condition,
                          p.set_code, p.collector_number, p.rarity, p.image_uri,
                          c.name, c.type_line, c.mana_cost, c.cmc,
                          c.color_identity, c.oracle_id
                   FROM collection col
                   JOIN printings p ON col.printing_id = p.printing_id
                   JOIN cards c ON p.oracle_id = c.oracle_id
                   WHERE col.status = 'owned'
                     AND NOT EXISTS (
                       SELECT 1 FROM deck_cards dc
                       JOIN decks d ON dc.deck_id = d.id
                       WHERE dc.collection_id = col.id AND d.state_id = ?
                     )
                     AND col.binder_id IS NULL
                     AND (c.name LIKE ? OR c.type_line LIKE ? OR c.oracle_text LIKE ?)
                   ORDER BY c.name
                   LIMIT 50""",
                (DECK_STATE_CONSTRUCTED, search, search, search),
            ).fetchall()
        conn.close()
        # Filter by color identity subset and exclude already-in-deck
        results = []
        for r in rows:
            if r["printing_id"] in in_deck:
                continue
            card_ci = json.loads(r["color_identity"]) if isinstance(r["color_identity"], str) and r["color_identity"] else []
            # Lands and colorless cards always pass; otherwise check subset
            if card_ci and cmd_colors:
                if not set(card_ci).issubset(set(cmd_colors)):
                    continue
            results.append(dict(r))
            if len(results) >= 30:
                break
        self._send_json(results)

    def _api_builder_add_card(self, deck_id: int, data: dict):
        """Add a card to the deck. Supports optional categories and audit return."""
        collection_id = data.get("collection_id")
        zone = data.get("zone", "mainboard")
        categories = data.get("categories")
        if not collection_id:
            self._send_json({"error": "collection_id is required"}, 400)
            return
        conn = self._get_conn()
        try:
            # If categories provided, use DeckBuilderService for full add+audit
            if categories:
                from mtg_collector.services.deck_builder import DeckBuilderService
                svc = DeckBuilderService(conn)
                try:
                    result = svc.add_card(deck_id, collection_id, categories)
                except ValueError as e:
                    self._send_json({"error": str(e)}, 409)
                    return
                self._send_json(result)
                return
            # Legacy path: simple add without categories
            deck = conn.execute("SELECT id, state_id FROM decks WHERE id = ?",
                                (deck_id,)).fetchone()
            if not deck:
                self._send_json({"error": "Deck not found"}, 404)
                return
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            try:
                count = repo.add_cards(deck_id, [collection_id], zone)
                conn.commit()
            except ValueError as e:
                self._send_json({"error": str(e)}, 409)
                return
        finally:
            conn.close()
        self._send_json({"ok": True, "added": count})

    def _api_builder_remove_card(self, deck_id: int, data: dict):
        """Remove a card from the deck."""
        collection_id = data.get("collection_id")
        if not collection_id:
            self._send_json({"error": "collection_id is required"}, 400)
            return
        conn = self._get_conn()
        try:
            from mtg_collector.db.models import DeckRepository
            repo = DeckRepository(conn)
            count = repo.remove_cards(deck_id, [collection_id])
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "removed": count})

    def _api_builder_browse_commanders(self, params: dict):
        """Browse owned legendary creatures with filters."""
        filters = {}
        for key in ("colors", "colors_min", "colors_max", "cmc_max",
                     "set_before", "set_after", "type", "text", "name",
                     "sort", "limit"):
            val = params.get(key, [""])[0]
            if val:
                filters[key] = val
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        results = svc.browse_commanders(filters)
        conn.close()
        self._send_json(results)

    def _api_builder_save_plan(self, deck_id: int, data: dict):
        """Save deck plan and optional sub-plans."""
        plan = data.get("plan")
        sub_plans = data.get("sub_plans")
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        if plan is not None:
            svc.save_plan(deck_id, plan)
        if sub_plans is not None:
            svc.save_sub_plans(deck_id, sub_plans)
        conn.close()
        self._send_json({"ok": True})

    def _api_builder_sql_search(self, deck_id: int, data: dict):
        """Search owned cards using a SQL WHERE clause."""
        where_clause = data.get("where_clause", "")
        if not where_clause:
            self._send_json({"error": "where_clause is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        try:
            results = svc.sql_search(deck_id, where_clause)
        except ValueError as e:
            conn.close()
            self._send_json({"error": str(e)}, 400)
            return
        except Exception as e:
            conn.close()
            self._send_json({"error": f"SQL error: {e}"}, 400)
            return
        conn.close()
        self._send_json(results)

    def _api_builder_add_basics(self, deck_id: int, data: dict):
        """Add basic lands to a deck."""
        basic_map = {"plains": "Plains", "island": "Island", "swamp": "Swamp",
                     "mountain": "Mountain", "forest": "Forest"}
        counts = {}
        for key, name in basic_map.items():
            val = data.get(key)
            if val and int(val) > 0:
                counts[name] = int(val)
        if not counts:
            self._send_json({"error": "Specify at least one basic land count"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        try:
            result = svc.add_basics(deck_id, counts)
        except ValueError as e:
            conn.close()
            self._send_json({"error": str(e)}, 400)
            return
        conn.close()
        self._send_json(result)

    def _api_builder_bling(self, deck_id: int, data: dict):
        """Upgrade deck cards to blingiest printings."""
        dry_run = bool(data.get("dry_run", False))
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        result = svc.bling_upgrade(deck_id, dry_run=dry_run)
        conn.close()
        self._send_json(result)

    def _api_builder_mana_analysis(self, deck_id: int):
        """Analyze mana requirements for a deck."""
        conn = self._get_conn()
        from mtg_collector.services.deck_builder import DeckBuilderService
        svc = DeckBuilderService(conn)
        try:
            result = svc.mana_analysis(deck_id)
        except ValueError as e:
            conn.close()
            self._send_json({"error": str(e)}, 404)
            return
        conn.close()
        self._send_json(result)

    # ===== Card lookup API handlers =====

    def _api_card_by_name(self, params: dict):
        """Look up card(s) by name. Searches both oracle and printing names."""
        name = params.get("name", [""])[0].strip()
        if not name:
            self._send_json({"error": "name parameter is required"}, 400)
            return
        conn = self._get_conn()

        def _attach_printing(oracle_id):
            """Find best printing (prefer owned) for an oracle_id."""
            p = conn.execute(
                """SELECT p.set_code, p.collector_number, p.printing_id,
                          p.flavor_name
                   FROM collection col
                   JOIN printings p ON col.printing_id = p.printing_id
                   WHERE p.oracle_id = ? AND col.status = 'owned'
                   ORDER BY col.id DESC LIMIT 1""",
                (oracle_id,),
            ).fetchone()
            if not p:
                p = conn.execute(
                    """SELECT p.set_code, p.collector_number, p.printing_id,
                              p.flavor_name
                       FROM printings p
                       JOIN sets s ON s.set_code = p.set_code
                       WHERE p.oracle_id = ? AND s.digital = 0
                       ORDER BY s.released_at DESC LIMIT 1""",
                    (oracle_id,),
                ).fetchone()
            return p

        # Exact match — prefer cards with real printings over token-only
        row = conn.execute(
            """SELECT c.*,
                      (SELECT json_extract(p2.raw_json, '$.power')
                       FROM printings p2 WHERE p2.oracle_id = c.oracle_id
                       AND p2.raw_json IS NOT NULL LIMIT 1) as power,
                      (SELECT json_extract(p2.raw_json, '$.toughness')
                       FROM printings p2 WHERE p2.oracle_id = c.oracle_id
                       AND p2.raw_json IS NOT NULL LIMIT 1) as toughness
               FROM cards c
               WHERE c.name = ?
               ORDER BY CASE WHEN EXISTS (
                   SELECT 1 FROM printings p
                   JOIN sets s ON s.set_code = p.set_code
                   WHERE p.oracle_id = c.oracle_id AND s.digital = 0
                     AND s.set_type NOT IN ('token', 'memorabilia')
               ) THEN 0 ELSE 1 END
               LIMIT 1""",
            (name,),
        ).fetchone()
        # Fallback: exact match on printing name (flavor_name)
        if not row:
            row = conn.execute(
                """SELECT c.oracle_id, c.name, c.mana_cost, c.type_line,
                          c.oracle_text, c.colors, c.color_identity, c.cmc
                   FROM printings p
                   JOIN cards c ON c.oracle_id = p.oracle_id
                   WHERE p.flavor_name = ?
                   LIMIT 1""",
                (name,),
            ).fetchone()
        if row:
            result = dict(row)
            printing = _attach_printing(row["oracle_id"])
            if printing:
                result["set_code"] = printing["set_code"]
                result["collector_number"] = printing["collector_number"]
                result["printing_id"] = printing["printing_id"]
                if printing["flavor_name"] and printing["flavor_name"] != result["name"]:
                    result["printing_name"] = printing["flavor_name"]
            conn.close()
            self._send_json([result])
            return
        # LIKE fallback — search both oracle and printing names
        rows = conn.execute(
            """SELECT c.*,
                      (SELECT json_extract(p2.raw_json, '$.power')
                       FROM printings p2 WHERE p2.oracle_id = c.oracle_id
                       AND p2.raw_json IS NOT NULL LIMIT 1) as power,
                      (SELECT json_extract(p2.raw_json, '$.toughness')
                       FROM printings p2 WHERE p2.oracle_id = c.oracle_id
                       AND p2.raw_json IS NOT NULL LIMIT 1) as toughness
               FROM cards c
               LEFT JOIN printings p ON p.oracle_id = c.oracle_id
               LEFT JOIN sets s ON s.set_code = p.set_code
               WHERE (c.name LIKE ? OR p.flavor_name LIKE ?)
                 AND (s.digital = 0 AND s.set_type NOT IN ('token', 'memorabilia'))
               GROUP BY c.oracle_id
               LIMIT 50""",
            (f"%{name}%", f"%{name}%"),
        ).fetchall()
        results = []
        for r in rows:
            card = dict(r)
            printing = _attach_printing(r["oracle_id"])
            if printing:
                card["set_code"] = printing["set_code"]
                card["collector_number"] = printing["collector_number"]
                card["printing_id"] = printing["printing_id"]
                if printing["flavor_name"] and printing["flavor_name"] != card["name"]:
                    card["printing_name"] = printing["flavor_name"]
            results.append(card)
        conn.close()
        self._send_json(results)

    # ===== Jumpstart API handlers =====

    def _api_jumpstart_find_card(self, data: dict):
        """Search cards with jumpstart-style filters."""
        conn = self._get_conn()
        conditions = ["s.digital = 0", "s.set_type NOT IN ('token', 'memorabilia')"]
        params = []
        owned = data.get("owned", False)

        if data.get("rarity"):
            conditions.append("p.rarity = ?")
            params.append(data["rarity"].lower())

        if data.get("type"):
            type_map = {
                "creature": "Creature", "instant": "Instant",
                "sorcery": "Sorcery", "enchantment": "Enchantment",
                "artifact": "Artifact", "planeswalker": "Planeswalker",
            }
            card_type = type_map.get(data["type"].lower(), data["type"])
            conditions.append(
                "(c.type_line LIKE ? AND c.type_line NOT LIKE '%//%' || ? || '%')"
            )
            params.append(f"%{card_type}%")
            params.append(card_type)

        if data.get("cmc") is not None:
            conditions.append("c.cmc = ?")
            params.append(float(data["cmc"]))

        if data.get("mv_min") is not None:
            conditions.append("c.cmc >= ?")
            params.append(float(data["mv_min"]))

        if data.get("mv_max") is not None:
            conditions.append("c.cmc <= ?")
            params.append(float(data["mv_max"]))

        if data.get("color"):
            color = data["color"].upper()
            if data.get("type") and data["type"].lower() == "artifact":
                conditions.append(
                    "(c.colors = ? OR c.colors = '[]' OR c.colors IS NULL)"
                )
                params.append(f'["{color}"]')
            else:
                conditions.append("c.colors = ?")
                params.append(f'["{color}"]')

        if data.get("theme"):
            theme_pat = f"%{data['theme']}%"
            conditions.append(
                "(c.oracle_text LIKE ? OR c.type_line LIKE ? OR c.name LIKE ?"
                " OR p.flavor_name LIKE ?)"
            )
            params.extend([theme_pat] * 4)

        # When owned, join through collection to ensure printing info
        # comes from an owned printing (not an arbitrary one)
        collection_join = ""
        if owned:
            collection_join = (
                "JOIN collection col ON col.printing_id = p.printing_id"
                " AND col.status = 'owned'"
            )

        where = " AND ".join(conditions)
        limit = int(data.get("limit", 50))

        query = f"""
            SELECT c.name as oracle_name, c.mana_cost, c.type_line, c.cmc,
                   p.rarity, c.oracle_text, c.oracle_id, c.colors, c.color_identity,
                   COALESCE(p.flavor_name, c.name) as name,
                   p.set_code, p.collector_number,
                   json_extract(p.raw_json, '$.power') as power,
                   json_extract(p.raw_json, '$.toughness') as toughness,
                   lp.price as price
            FROM cards c
            JOIN printings p ON p.oracle_id = c.oracle_id
            JOIN sets s ON s.set_code = p.set_code
            {collection_join}
            LEFT JOIN latest_prices lp ON lp.set_code = p.set_code
                AND lp.collector_number = p.collector_number
                AND lp.price_type = 'normal'
            WHERE {where}
            GROUP BY c.oracle_id
            ORDER BY name
            LIMIT ?
        """
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for r in rows:
            row = dict(r)
            if row["oracle_name"] == row["name"]:
                row.pop("oracle_name")
            results.append(row)
        self._send_json(results)

    def _api_jumpstart_printings_by_name(self, data: dict):
        """Resolve card names to owned printing set_code/collector_number."""
        names = data.get("names", [])
        if not names:
            self._send_json({"error": "names array is required"}, 400)
            return
        conn = self._get_conn()
        results = {}
        for name in names:
            # Prefer owned printing — try oracle name then printing name
            row = conn.execute("""
                SELECT p.set_code, p.collector_number
                FROM collection col
                JOIN printings p ON p.printing_id = col.printing_id
                JOIN cards c ON c.oracle_id = p.oracle_id
                WHERE (c.name = ? OR p.flavor_name = ?)
                    AND col.status = 'owned'
                LIMIT 1
            """, (name, name)).fetchone()
            if not row:
                row = conn.execute("""
                    SELECT p.set_code, p.collector_number
                    FROM printings p
                    JOIN cards c ON c.oracle_id = p.oracle_id
                    JOIN sets s ON s.set_code = p.set_code
                    WHERE (c.name = ? OR p.flavor_name = ?)
                        AND s.digital = 0
                    ORDER BY s.released_at DESC LIMIT 1
                """, (name, name)).fetchone()
            if row:
                results[name] = {"set_code": row["set_code"],
                                 "collector_number": row["collector_number"]}
        conn.close()
        self._send_json(results)

    def _api_jumpstart_sql_search(self, data: dict):
        """Search owned cards using a SQL WHERE clause for jumpstart building."""
        where_clause = data.get("where_clause", "")
        if not where_clause:
            self._send_json({"error": "where_clause is required"}, 400)
            return
        if ";" in where_clause:
            self._send_json({"error": "Semicolons are not allowed in WHERE clauses."}, 400)
            return
        if re.search(r"\b(ATTACH|DETACH|PRAGMA)\b", where_clause, re.IGNORECASE):
            self._send_json({"error": "Only read-only WHERE clauses are allowed."}, 400)
            return

        conn = self._get_conn()

        where = f"({where_clause})"
        params = []
        sql = f"""SELECT col.id, col.printing_id, col.finish, col.condition,
                         p.set_code, p.collector_number, p.rarity, p.image_uri,
                         c.name, c.type_line, c.mana_cost, c.cmc,
                         c.oracle_id, c.oracle_text,
                         (SELECT MIN(CASE p2.rarity
                            WHEN 'common' THEN 1 WHEN 'uncommon' THEN 2
                            WHEN 'rare' THEN 3 WHEN 'mythic' THEN 4 ELSE 5 END)
                          FROM printings p2 WHERE p2.oracle_id = c.oracle_id) AS min_rarity_rank
                  FROM collection col
                  JOIN printings p ON col.printing_id = p.printing_id
                  JOIN cards c ON p.oracle_id = c.oracle_id
                  WHERE col.status = 'owned'
                    AND {where}
                  ORDER BY c.cmc, c.name
                  LIMIT 200"""

        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            conn.close()
            self._send_json({"error": f"SQL error: {e}"}, 400)
            return

        # Dedup by oracle_id; override rarity with lowest across all printings
        rank_to_rarity = {1: "common", 2: "uncommon", 3: "rare", 4: "mythic"}
        seen = set()
        results = []
        for row in rows:
            oid = row["oracle_id"]
            if oid in seen:
                continue
            seen.add(oid)
            d = dict(row)
            rank = d.pop("min_rarity_rank", None)
            if rank and rank in rank_to_rarity:
                d["rarity"] = rank_to_rarity[rank]
            results.append(d)
            if len(results) >= 50:
                break

        conn.close()
        self._send_json(results)

    def _api_jumpstart_insert_deck(self, data: dict):
        """Create a Jumpstart idea deck with expected cards."""
        color = data.get("color")
        theme = data.get("theme")
        description = data.get("description", "")
        card_names = data.get("cards", [])
        basics_count = int(data.get("basics", 7))

        if not color or not theme or not card_names:
            self._send_json(
                {"error": "color, theme, and cards are required"}, 400)
            return

        thriving_names = {"W": "Thriving Heath", "U": "Thriving Isle",
                          "B": "Thriving Moor", "R": "Thriving Bluff",
                          "G": "Thriving Grove"}
        basic_names = {"W": "Plains", "U": "Island", "B": "Swamp",
                       "R": "Mountain", "G": "Forest"}

        conn = self._get_conn()
        try:
            # Check for duplicate deck name
            deck_name = f"{theme} (Jumpstart)"
            existing = conn.execute(
                "SELECT id FROM decks WHERE name = ?", (deck_name,)
            ).fetchone()
            if existing:
                self._send_json(
                    {"error": f"Deck '{deck_name}' already exists (id={existing[0]})"}, 409)
                return

            # Resolve all card names to printing_ids
            def _resolve_printing(name):
                # Go straight through printings — owned copy preferred
                # Match by oracle name OR printing name (flavor_name)
                row = conn.execute(
                    """SELECT p.printing_id FROM collection col
                       JOIN printings p ON col.printing_id = p.printing_id
                       JOIN cards c ON p.oracle_id = c.oracle_id
                       JOIN sets s ON p.set_code = s.set_code
                       WHERE (c.name = ?
                              OR p.flavor_name = ?)
                         AND col.status = 'owned'
                         AND s.set_type NOT IN ('token', 'memorabilia')
                       ORDER BY s.released_at DESC LIMIT 1""",
                    (name, name),
                ).fetchone()
                if row:
                    return row[0], None
                # Fall back to any real printing
                row = conn.execute(
                    """SELECT p.printing_id FROM printings p
                       JOIN cards c ON p.oracle_id = c.oracle_id
                       JOIN sets s ON p.set_code = s.set_code
                       WHERE (c.name = ?
                              OR p.flavor_name = ?)
                         AND s.digital = 0
                         AND s.set_type NOT IN ('token', 'memorabilia')
                       ORDER BY s.released_at DESC LIMIT 1""",
                    (name, name),
                ).fetchone()
                if row:
                    return row[0], None
                return None, f"No non-digital printing for: {name}"

            def _ensure_in_collection(name):
                oracle = conn.execute(
                    "SELECT oracle_id FROM cards WHERE name = ?", (name,)
                ).fetchone()
                if not oracle:
                    oracle = conn.execute(
                        """SELECT c.oracle_id FROM printings p
                           JOIN cards c ON c.oracle_id = p.oracle_id
                           WHERE p.flavor_name = ?
                           LIMIT 1""",
                        (name,),
                    ).fetchone()
                if not oracle:
                    return
                oid = oracle[0]
                existing = conn.execute(
                    """SELECT col.id FROM collection col
                       JOIN printings p ON col.printing_id = p.printing_id
                       WHERE p.oracle_id = ? AND col.status = 'owned' LIMIT 1""",
                    (oid,),
                ).fetchone()
                if existing:
                    return
                printing = conn.execute(
                    """SELECT p.printing_id FROM printings p
                       JOIN sets s ON s.set_code = p.set_code
                       WHERE p.oracle_id = ? AND s.digital = 0
                       ORDER BY s.released_at DESC LIMIT 1""",
                    (oid,),
                ).fetchone()
                if printing:
                    from mtg_collector.utils import now_iso
                    conn.execute(
                        """INSERT INTO collection (printing_id, finish, status, source, acquired_at)
                           VALUES (?, 'nonfoil', 'owned', 'manual', ?)""",
                        (printing[0], now_iso()),
                    )

            expected_cards = []
            for name in card_names:
                pid, err = _resolve_printing(name)
                if err:
                    self._send_json({"error": err}, 400)
                    return
                expected_cards.append({"printing_id": pid, "zone": "mainboard",
                                       "quantity": 1, "name": name})

            # Ensure thriving land in collection and resolve
            if color == "C":
                pass  # Colorless decks have no thriving/basic lands
            elif len(color) == 1:
                thriving_name = thriving_names.get(color)
                basic_name = basic_names.get(color)
                if not thriving_name:
                    self._send_json({"error": f"Invalid color: {color}"}, 400)
                    return
                _ensure_in_collection(thriving_name)
                thriving_pid, err = _resolve_printing(thriving_name)
                if err:
                    self._send_json({"error": err}, 400)
                    return
                basic_pid, err = _resolve_printing(basic_name)
                if err:
                    self._send_json({"error": err}, 400)
                    return

                expected_cards.append({"printing_id": thriving_pid, "zone": "mainboard",
                                       "quantity": 1, "name": thriving_name})
                expected_cards.append({"printing_id": basic_pid, "zone": "mainboard",
                                       "quantity": basics_count, "name": basic_name})
            else:
                # Multicolor: one thriving land for the first color,
                # split basics evenly between colors
                colors = list(color)
                first_color = colors[0]
                thriving_name = thriving_names.get(first_color)
                if not thriving_name:
                    self._send_json({"error": f"Invalid color: {color}"}, 400)
                    return
                _ensure_in_collection(thriving_name)
                thriving_pid, err = _resolve_printing(thriving_name)
                if err:
                    self._send_json({"error": err}, 400)
                    return
                expected_cards.append({"printing_id": thriving_pid, "zone": "mainboard",
                                       "quantity": 1, "name": thriving_name})
                # Split basics: e.g. 7 basics across 2 colors → 4 + 3
                per_color = basics_count // len(colors)
                remainder = basics_count % len(colors)
                for i, c in enumerate(colors):
                    bname = basic_names.get(c)
                    if not bname:
                        self._send_json({"error": f"Invalid color in pair: {c}"}, 400)
                        return
                    qty = per_color + (1 if i < remainder else 0)
                    if qty > 0:
                        bpid, err = _resolve_printing(bname)
                        if err:
                            self._send_json({"error": err}, 400)
                            return
                        expected_cards.append({"printing_id": bpid, "zone": "mainboard",
                                               "quantity": qty, "name": bname})

            # Dedup by (printing_id, zone) — card list may already contain
            # a land that was also auto-appended above
            deduped = {}
            for card in expected_cards:
                key = (card["printing_id"], card["zone"])
                if key in deduped:
                    deduped[key]["quantity"] += card["quantity"]
                else:
                    deduped[key] = dict(card)
            expected_cards = list(deduped.values())

            # Create deck
            from mtg_collector.utils import now_iso
            ts = now_iso()
            conn.execute(
                """INSERT INTO decks (name, description, format, state_id,
                   origin_set_code, origin_theme, is_precon, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (deck_name, description, "jumpstart", 1, "J25", theme, 0, ts, ts),
            )
            deck_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for card in expected_cards:
                conn.execute(
                    """INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity)
                       VALUES (?, ?, ?, ?)""",
                    (deck_id, card["printing_id"], card["zone"], card["quantity"]),
                )

            conn.commit()

            self._send_json({
                "deck_id": deck_id,
                "name": deck_name,
                "cards": expected_cards,
            }, 201)
        finally:
            conn.close()

    # ===== Binder API handlers =====

    def _api_binders_list(self):
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        self._send_json(repo.list_all())
        conn.close()

    def _api_binder_get(self, binder_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        binder = repo.get(binder_id)
        conn.close()
        if binder is None:
            self._send_json({"error": "Binder not found"}, 404)
            return
        self._send_json(binder)

    def _api_binder_create(self, data: dict):
        name = data.get("name")
        if not name:
            self._send_json({"error": "name is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import Binder, BinderRepository
        repo = BinderRepository(conn)
        binder = Binder(
            id=None, name=name, description=data.get("description"),
            color=data.get("color"), binder_type=data.get("binder_type"),
            storage_location=data.get("storage_location"),
        )
        try:
            binder_id = repo.add(binder)
            conn.commit()
            result = repo.get(binder_id)
        finally:
            conn.close()
        self._send_json(result, 201)

    def _api_binder_update(self, binder_id: int, data: dict):
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        try:
            if not repo.get(binder_id):
                self._send_json({"error": "Binder not found"}, 404)
                return
            repo.update(binder_id, data)
            conn.commit()
            result = repo.get(binder_id)
        finally:
            conn.close()
        self._send_json(result)

    def _api_binder_delete(self, binder_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        try:
            if not repo.delete(binder_id):
                self._send_json({"error": "Binder not found"}, 404)
                return
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_binder_cards(self, binder_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        cards = repo.get_cards(binder_id)
        conn.close()
        self._send_json(cards)

    def _api_binder_add_cards(self, binder_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        try:
            count = repo.add_cards(binder_id, collection_ids)
            conn.commit()
        except ValueError as e:
            self._send_json({"error": str(e)}, 409)
            return
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_binder_remove_cards(self, binder_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        try:
            count = repo.remove_cards(binder_id, collection_ids)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    def _api_binder_move_cards(self, binder_id: int, data: dict):
        collection_ids = data.get("collection_ids", [])
        if not collection_ids:
            self._send_json({"error": "collection_ids is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import BinderRepository
        repo = BinderRepository(conn)
        try:
            count = repo.move_cards(collection_ids, binder_id)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True, "count": count})

    # ===== Collection View API handlers =====

    def _api_views_list(self):
        conn = self._get_conn()
        from mtg_collector.db.models import CollectionViewRepository
        repo = CollectionViewRepository(conn)
        self._send_json(repo.list_all())
        conn.close()

    def _api_view_get(self, view_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import CollectionViewRepository
        repo = CollectionViewRepository(conn)
        view = repo.get(view_id)
        conn.close()
        if view is None:
            self._send_json({"error": "View not found"}, 404)
            return
        self._send_json(view)

    def _api_view_create(self, data: dict):
        name = data.get("name")
        filters_json = data.get("filters_json")
        if not name:
            self._send_json({"error": "name is required"}, 400)
            return
        if filters_json is None:
            self._send_json({"error": "filters_json is required"}, 400)
            return
        conn = self._get_conn()
        from mtg_collector.db.models import CollectionView, CollectionViewRepository
        repo = CollectionViewRepository(conn)
        if isinstance(filters_json, dict):
            filters_json = json.dumps(filters_json)
        view = CollectionView(
            id=None, name=name, description=data.get("description"),
            filters_json=filters_json,
        )
        try:
            view_id = repo.add(view)
            conn.commit()
            result = repo.get(view_id)
        finally:
            conn.close()
        self._send_json(result, 201)

    def _api_view_update(self, view_id: int, data: dict):
        conn = self._get_conn()
        from mtg_collector.db.models import CollectionViewRepository
        repo = CollectionViewRepository(conn)
        try:
            if not repo.get(view_id):
                self._send_json({"error": "View not found"}, 404)
                return
            if "filters_json" in data and isinstance(data["filters_json"], dict):
                data["filters_json"] = json.dumps(data["filters_json"])
            repo.update(view_id, data)
            conn.commit()
            result = repo.get(view_id)
        finally:
            conn.close()
        self._send_json(result)

    def _api_view_delete(self, view_id: int):
        conn = self._get_conn()
        from mtg_collector.db.models import CollectionViewRepository
        repo = CollectionViewRepository(conn)
        try:
            if not repo.delete(view_id):
                self._send_json({"error": "View not found"}, 404)
                return
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_shorten(self, params):
        import requests

        url = params.get("url", [""])[0]
        shorteners = [
            ("https://da.gd/s", {"url": url}),
            ("https://is.gd/create.php", {"format": "simple", "url": url}),
        ]
        for base, qs in shorteners:
            try:
                resp = requests.get(base, params=qs, timeout=5)
                short = resp.text.strip()
                if resp.ok and short.startswith("http"):
                    self._send_json({"short_url": short})
                    return
            except Exception:
                continue
        self._send_json({"error": "Shortening failed"}, 502)

    def _api_wishlist_list(self, params: dict):
        """List wishlist entries."""
        from mtg_collector.db.models import WishlistRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)

        repo = WishlistRepository(conn)
        fulfilled_param = params.get("fulfilled", [""])[0]
        fulfilled = None
        if fulfilled_param == "true":
            fulfilled = True
        elif fulfilled_param == "false":
            fulfilled = False

        name = params.get("name", [""])[0] or None
        limit_str = params.get("limit", [""])[0]
        limit = int(limit_str) if limit_str else None

        entries = repo.list_all(fulfilled=fulfilled, name=name, limit=limit)
        conn.close()
        self._send_json(entries)

    def _api_wishlist_add(self, data: dict):
        """Add a wishlist entry."""
        from mtg_collector.db.models import (
            CardRepository,
            PrintingRepository,
            WishlistEntry,
            WishlistRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import now_iso

        name = data.get("name", "").strip()
        if not name:
            self._send_json({"error": "name is required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            card_repo = CardRepository(conn)
            printing_repo = PrintingRepository(conn)

            card = card_repo.get_by_name(name) or card_repo.search_by_name(name)
            if not card:
                self._send_json({"error": f"No card found matching '{name}' (run `mtg cache all` to populate)"}, 404)
                return

            oracle_id = card.oracle_id
            set_code = data.get("set_code")
            printing_id = None

            if set_code:
                cn = data.get("collector_number")
                printings = printing_repo.get_by_oracle_id(oracle_id)
                for p in printings:
                    if p.set_code == set_code.lower():
                        if cn and p.collector_number != cn:
                            continue
                        printing_id = p.printing_id
                        break

            repo = WishlistRepository(conn)
            entry = WishlistEntry(
                id=None,
                oracle_id=oracle_id,
                printing_id=printing_id,
                max_price=data.get("max_price"),
                priority=data.get("priority", 0),
                notes=data.get("notes"),
                added_at=now_iso(),
                source="server",
            )
            new_id = repo.add(entry)
            conn.commit()
        finally:
            conn.close()

        self._send_json({"id": new_id, "name": card.name, "oracle_id": oracle_id, "printing_id": printing_id})

    def _api_wishlist_bulk_add(self, data: dict):
        """Bulk-add cards to the wishlist."""
        from mtg_collector.db.models import (
            CardRepository,
            PrintingRepository,
            WishlistEntry,
            WishlistRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import now_iso

        cards = data.get("cards", [])
        if not cards:
            self._send_json({"added": [], "errors": []})
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            card_repo = CardRepository(conn)
            printing_repo = PrintingRepository(conn)
            wishlist_repo = WishlistRepository(conn)

            added = []
            errors = []

            for item in cards:
                name = (item.get("name") or "").strip()
                if not name:
                    errors.append({"name": name, "error": "name is required"})
                    continue
                set_code = item.get("set_code")
                cn = item.get("collector_number")
                try:
                    card = card_repo.get_by_name(name) or card_repo.search_by_name(name)
                    if not card:
                        errors.append({"name": name, "error": f"No card found matching '{name}'"})
                        continue
                    oracle_id = card.oracle_id
                    printing_id = None
                    if set_code:
                        printings = printing_repo.get_by_oracle_id(oracle_id)
                        for p in printings:
                            if p.set_code == set_code.lower():
                                if cn and p.collector_number != cn:
                                    continue
                                printing_id = p.printing_id
                                break
                    entry = WishlistEntry(
                        id=None,
                        oracle_id=oracle_id,
                        printing_id=printing_id,
                        priority=item.get("priority", 0),
                        added_at=now_iso(),
                        source="server",
                    )
                    new_id = wishlist_repo.add(entry)
                    added.append({"id": new_id, "name": card.name, "oracle_id": oracle_id, "printing_id": printing_id})
                except Exception as exc:
                    errors.append({"name": name, "error": str(exc)})

            conn.commit()
        finally:
            conn.close()
        self._send_json({"added": added, "errors": errors})

    def _api_wishlist_delete(self, wid: int):
        """Delete a wishlist entry."""
        from mtg_collector.db.models import WishlistRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = WishlistRepository(conn)
            deleted = repo.delete(wid)
            conn.commit()
        finally:
            conn.close()

        if deleted:
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _api_wishlist_fulfill(self, wid: int):
        """Mark a wishlist entry as fulfilled."""
        from mtg_collector.db.models import WishlistRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)

            repo = WishlistRepository(conn)
            fulfilled = repo.fulfill(wid)
            conn.commit()
        finally:
            conn.close()

        if fulfilled:
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _api_set_browse(self, set_code: str, params: dict):
        """One set as a binder page: every printing, owned counts, prices."""
        from mtg_collector.db.models import SetRepository
        from mtg_collector.db.schema import init_db
        from mtg_collector.db.set_browse import browse_set

        try:
            set_code = _parse_set_code(set_code)
            limit, offset = _parse_page_params(params)
            view = _parse_set_browse_params(params)
        except PageParamError as e:
            self._send_json({"error": str(e)}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            # A set with no cached card list has no binder to render, and
            # inventing an empty one would read as a set you own none of.
            if not SetRepository(conn).is_cards_cached(set_code):
                self._send_json(
                    {"error": f"Set '{set_code}' not cached (run `mtg cache all` to populate)"},
                    404,
                )
                return

            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'price_sources'"
            ).fetchone()
            first_source = (row["value"] if row else "tcg,ck").split(",")[0]

            payload = browse_set(
                conn, set_code, view,
                limit=limit, offset=offset, display_source=first_source,
            )
        finally:
            conn.close()

        self._send_json(payload)

    def _api_collection_add(self, data: dict):
        """Add a card to the collection manually.

        An optional `batch` descriptor — `{batch_uuid, batch_type, name,
        set_code}` — files the new copy under a batch, creating that batch on
        the first add that carries the uuid and joining it on every later one.
        The binder grid's session batch works this way: browsing posts nothing
        and so creates nothing, and one pip click is still one request.

        `condition` is optional and defaults to Near Mint.  An unrecognised one
        is a 400 rather than a coercion to the default: the binder grid's
        condition select sticks for a whole browsing pass, so silently filing a
        binder of Lightly Played cards as Near Mint would mislabel the lot.
        """
        from mtg_collector.db.models import (
            Batch,
            BatchRepository,
            CollectionEntry,
            CollectionRepository,
            WishlistRepository,
        )
        from mtg_collector.db.schema import init_db
        from mtg_collector.utils import CONDITIONS

        printing_id = data.get("printing_id", "").strip()
        if not printing_id:
            self._send_json({"error": "printing_id is required"}, 400)
            return

        finish = data.get("finish", "nonfoil")
        condition = data.get("condition") or "Near Mint"
        if condition not in CONDITIONS:
            self._send_json({"error": f"Unknown condition: {condition}"}, 400)
            return
        acquired_at = data.get("acquired_at")
        purchase_price = data.get("purchase_price")
        source = data.get("source", "manual")

        # Both halves of the descriptor are required when it is present: the
        # uuid is the batch's identity, and a missing type would file the copy
        # under the schema's 'corner' default and mislabel it forever.
        batch_spec = data.get("batch")
        if batch_spec is not None:
            batch_uuid = (batch_spec.get("batch_uuid") or "").strip()
            batch_type = (batch_spec.get("batch_type") or "").strip()
            if not batch_uuid:
                self._send_json({"error": "batch.batch_uuid is required"}, 400)
                return
            if not batch_type:
                self._send_json({"error": "batch.batch_type is required"}, 400)
                return

        if purchase_price is not None:
            purchase_price = float(purchase_price)

        conn = self._get_conn()
        try:
            init_db(conn)

            batch_id = None
            batch_repo = BatchRepository(conn)
            if batch_spec is not None:
                batch_id = batch_repo.get_or_create(Batch(
                    id=None,
                    batch_uuid=batch_uuid,
                    name=batch_spec.get("name"),
                    batch_type=batch_type,
                    set_code=batch_spec.get("set_code"),
                ))

            collection_repo = CollectionRepository(conn)
            entry = CollectionEntry(
                id=None,
                printing_id=printing_id,
                finish=finish,
                condition=condition,
                acquired_at=acquired_at,
                purchase_price=purchase_price,
                source=source,
                batch_id=batch_id,
            )
            new_id = collection_repo.add(entry)
            if batch_id is not None:
                batch_repo.increment_card_count(batch_id, 1)

            # Auto-fulfill matching wishlist entry
            fulfilled_wishlist_id = None
            wishlist_repo = WishlistRepository(conn)
            # Check for a printing-specific wishlist entry first
            row = conn.execute(
                "SELECT id FROM wishlist WHERE printing_id = ? AND fulfilled_at IS NULL LIMIT 1",
                (printing_id,),
            ).fetchone()
            if row:
                wishlist_repo.fulfill(row["id"])
                fulfilled_wishlist_id = row["id"]
            else:
                # Check for an oracle-level wishlist entry
                row = conn.execute(
                    """SELECT w.id FROM wishlist w
                       JOIN printings p ON p.oracle_id = w.oracle_id
                       WHERE p.printing_id = ? AND w.printing_id IS NULL
                         AND w.fulfilled_at IS NULL LIMIT 1""",
                    (printing_id,),
                ).fetchone()
                if row:
                    wishlist_repo.fulfill(row["id"])
                    fulfilled_wishlist_id = row["id"]

            conn.commit()
        finally:
            conn.close()

        result = {"id": new_id}
        if fulfilled_wishlist_id is not None:
            result["fulfilled_wishlist_id"] = fulfilled_wishlist_id
        if batch_id is not None:
            result["batch_id"] = batch_id
        self._send_json(result)

    def _api_collection_copies(self, params: dict):
        """Return per-copy data for a card (by printing_id + optional filters)."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db

        printing_id = params.get("printing_id", [""])[0]
        if not printing_id:
            self._send_json({"error": "printing_id required"}, 400)
            return

        finish = params.get("finish", [""])[0] or None
        condition = params.get("condition", [""])[0] or None
        status = params.get("status", [""])[0] or None

        conn = self._get_conn()
        init_db(conn)

        repo = CollectionRepository(conn)
        copies = repo.get_copies(printing_id, finish=finish, condition=condition, status=status)
        conn.close()
        self._send_json(copies)

    def _api_collection_dispose(self, entry_id: int, data: dict):
        """Transition a collection entry to a disposition status."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db

        new_status = data.get("new_status")
        if not new_status:
            self._send_json({"error": "new_status required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            repo = CollectionRepository(conn)
            try:
                repo.dispose(
                    entry_id,
                    new_status,
                    sale_price=data.get("sale_price"),
                    note=data.get("note"),
                )
                conn.commit()
            except ValueError as e:
                self._send_json({"error": str(e)}, 400)
                return
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_collection_delete(self, entry_id: int):
        """Hard-delete a collection entry with lineage cleanup."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = CollectionRepository(conn)
            try:
                deleted = repo.delete_with_lineage(entry_id)
                conn.commit()
            except ValueError as e:
                self._send_json({"error": str(e)}, 400)
                return
        finally:
            conn.close()
        if deleted:
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _api_collection_bulk_delete(self, data: dict):
        """Bulk-delete collection entries with lineage cleanup."""
        from mtg_collector.db.models import CollectionRepository
        from mtg_collector.db.schema import init_db

        ids = data.get("ids", [])
        if not ids:
            self._send_json({"error": "ids array required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = CollectionRepository(conn)
            result = repo.bulk_delete(ids)
            conn.commit()
        finally:
            conn.close()
        self._send_json({
            "deleted": len(result["deleted"]),
            "skipped": len(result["skipped"]),
            "deleted_ids": result["deleted"],
            "skipped_ids": result["skipped"],
        })

    # ── Sealed product API handlers ─────────────────────────────────

    def _api_sealed_products(self, params: dict):
        """Search/list sealed products (reference data)."""
        from mtg_collector.db.models import SealedProductCardRepository, SealedProductRepository
        from mtg_collector.db.schema import init_db

        q = params.get("q", [""])[0]
        set_code = params.get("set_code", [""])[0]
        category = params.get("category", [""])[0]
        limit = int(params.get("limit", ["50"])[0])

        conn = self._get_conn()
        init_db(conn)
        repo = SealedProductRepository(conn)

        if q:
            products = repo.search_by_name(q, limit=limit)
        elif set_code:
            products = repo.list_by_set(set_code.lower())
        else:
            # Default: return nothing without a search term or set filter
            conn.close()
            self._send_json([])
            return

        if category:
            products = [p for p in products if p.category == category]

        spc_repo = SealedProductCardRepository(conn)
        result = []
        for p in products[:limit]:
            image_url = None
            if p.tcgplayer_product_id:
                image_url = f"https://tcgplayer-cdn.tcgplayer.com/product/{p.tcgplayer_product_id}_200w.jpg"
            # Look up set name
            set_name = None
            row = conn.execute("SELECT set_name FROM sets WHERE set_code = ?", (p.set_code,)).fetchone()
            if row:
                set_name = row["set_name"]
            result.append({
                "uuid": p.uuid,
                "name": p.name,
                "set_code": p.set_code,
                "set_name": set_name,
                "category": p.category,
                "subtype": p.subtype,
                "tcgplayer_product_id": p.tcgplayer_product_id,
                "card_count": p.card_count,
                "product_size": p.product_size,
                "release_date": p.release_date,
                "image_url": image_url,
                "purchase_url_tcgplayer": p.purchase_url_tcgplayer,
                "purchase_url_cardkingdom": p.purchase_url_cardkingdom,
                "has_contents": spc_repo.has_cards(p.uuid),
            })

        conn.close()
        self._send_json(result)

    def _api_sealed_products_sets(self):
        """List sets that have sealed products."""
        from mtg_collector.db.models import SealedProductRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)
        repo = SealedProductRepository(conn)
        sets = repo.list_sets_with_products()
        conn.close()
        self._send_json(sets)

    def _api_sealed_product_detail(self, uuid: str):
        """Get a single sealed product by UUID."""
        from mtg_collector.db.models import SealedProductRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)
        repo = SealedProductRepository(conn)
        product = repo.get(uuid)
        if not product:
            conn.close()
            self._send_json({"error": f"Sealed product '{uuid}' not found"}, 404)
            return

        image_url = None
        if product.tcgplayer_product_id:
            image_url = f"https://tcgplayer-cdn.tcgplayer.com/product/{product.tcgplayer_product_id}_200w.jpg"
        set_name = None
        row = conn.execute("SELECT set_name FROM sets WHERE set_code = ?", (product.set_code,)).fetchone()
        if row:
            set_name = row["set_name"]
        conn.close()

        self._send_json({
            "uuid": product.uuid,
            "name": product.name,
            "set_code": product.set_code,
            "set_name": set_name,
            "category": product.category,
            "subtype": product.subtype,
            "tcgplayer_product_id": product.tcgplayer_product_id,
            "card_count": product.card_count,
            "product_size": product.product_size,
            "release_date": product.release_date,
            "image_url": image_url,
            "purchase_url_tcgplayer": product.purchase_url_tcgplayer,
            "purchase_url_cardkingdom": product.purchase_url_cardkingdom,
            "contents_json": product.contents_json,
        })

    def _api_sealed_product_contents(self, uuid: str):
        """Preview the card contents of a sealed product."""
        import json as _json

        from mtg_collector.db.models import SealedProductCardRepository, SealedProductRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)

        product_repo = SealedProductRepository(conn)
        product = product_repo.get(uuid)
        if not product:
            conn.close()
            self._send_json({"error": f"Sealed product '{uuid}' not found"}, 404)
            return

        spc_repo = SealedProductCardRepository(conn)
        cards = spc_repo.get_cards_for_product(uuid)

        # Separate resolvable vs unresolvable
        resolvable = []
        unresolvable = []
        for card in cards:
            if card["printing_id"]:
                resolvable.append(card)
            else:
                unresolvable.append({
                    "mtgjson_uuid": card["mtgjson_uuid"],
                    "quantity": card["quantity"],
                    "is_foil": card["is_foil"],
                    "zone": card["zone"],
                    "source_type": card["source_type"],
                    "source_name": card["source_name"],
                })

        total_cards = sum(c["quantity"] for c in resolvable)

        # Parse sealed sub-products and other items from contents_json
        sealed_sub_products = []
        other_items = []
        if product.contents_json:
            try:
                contents = _json.loads(product.contents_json)
            except (ValueError, TypeError):
                contents = {}

            for sealed_ref in contents.get("sealed", []):
                sub_uuid = sealed_ref.get("uuid")
                found = False
                if sub_uuid:
                    found = product_repo.get(sub_uuid) is not None
                sealed_sub_products.append({
                    "name": sealed_ref.get("name", "Unknown"),
                    "count": sealed_ref.get("count", 1),
                    "uuid": sub_uuid,
                    "set": sealed_ref.get("set"),
                    "found_in_catalog": found,
                })

            for pack_ref in contents.get("pack", []):
                sealed_sub_products.append({
                    "name": f"Booster Pack ({pack_ref.get('code', '?')})",
                    "count": pack_ref.get("count", 1),
                    "uuid": None,
                    "set": pack_ref.get("set"),
                    "found_in_catalog": False,
                })

            for other_ref in contents.get("other", []):
                other_items.append({
                    "name": other_ref.get("name", "Unknown item"),
                    "count": other_ref.get("count", 1),
                })

        openable = len(resolvable) > 0

        conn.close()
        self._send_json({
            "cards": resolvable,
            "total_cards": total_cards,
            "unresolvable": unresolvable,
            "sealed_sub_products": sealed_sub_products,
            "other_items": other_items,
            "openable": openable,
        })

    def _api_sealed_open(self, data: dict):
        """Open a sealed product: add its cards to the collection."""
        import uuid as _uuid

        from mtg_collector.db.models import (
            Batch,
            BatchRepository,
            CollectionEntry,
            CollectionRepository,
            SealedCollectionEntry,
            SealedCollectionRepository,
            SealedProductCardRepository,
            SealedProductRepository,
        )
        from mtg_collector.db.schema import init_db

        sealed_product_uuid = data.get("sealed_product_uuid")
        if not sealed_product_uuid:
            self._send_json({"error": "sealed_product_uuid required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            product_repo = SealedProductRepository(conn)
            product = product_repo.get(sealed_product_uuid)
            if not product:
                self._send_json({"error": f"Sealed product '{sealed_product_uuid}' not found"}, 404)
                return

            spc_repo = SealedProductCardRepository(conn)
            cards = spc_repo.get_cards_for_product(sealed_product_uuid)
            resolvable = [c for c in cards if c["printing_id"]]

            if not resolvable:
                self._send_json({"error": "No resolvable cards in this product"}, 400)
                return

            condition = data.get("condition", "Near Mint")
            deck_id = data.get("deck_id")
            track_in_sealed = data.get("track_in_sealed", False)

            # Create batch
            batch_repo = BatchRepository(conn)
            batch = Batch(
                id=None,
                batch_uuid=str(_uuid.uuid4()),
                name=f"Opened: {product.name}",
                batch_type="sealed_open",
                product_type=product.category,
                set_code=product.set_code,
            )
            batch_id = batch_repo.create(batch)

            # Add cards to collection
            collection_repo = CollectionRepository(conn)
            cards_added = 0
            errors = []
            collection_ids = []

            for card in resolvable:
                finish = "foil" if card["is_foil"] else "nonfoil"
                for _ in range(card["quantity"]):
                    try:
                        entry = CollectionEntry(
                            id=None,
                            printing_id=card["printing_id"],
                            finish=finish,
                            condition=condition,
                            source="sealed_open",
                            batch_id=batch_id,
                        )
                        new_id = collection_repo.add(entry)
                        collection_ids.append(new_id)
                        cards_added += 1
                    except Exception as e:
                        errors.append(f"Error adding {card.get('name', '?')}: {e}")

            # Update batch card count and complete
            if collection_ids:
                batch_repo.increment_card_count(batch_id, len(collection_ids))

            # Assign to deck if requested
            if deck_id and collection_ids:
                from mtg_collector.db.models import DeckRepository
                DeckRepository(conn).add_cards(int(deck_id), collection_ids, zone="mainboard")

            batch_repo.complete(batch_id)

            # Handle sealed sub-products
            sealed_added = 0
            if product.contents_json:
                import json as _json
                try:
                    contents = _json.loads(product.contents_json)
                except (ValueError, TypeError):
                    contents = {}

                sealed_repo = SealedCollectionRepository(conn)
                for sealed_ref in contents.get("sealed", []):
                    sub_uuid = sealed_ref.get("uuid")
                    if not sub_uuid:
                        continue
                    sub_product = product_repo.get(sub_uuid)
                    if not sub_product:
                        continue
                    for _ in range(sealed_ref.get("count", 1)):
                        sub_entry = SealedCollectionEntry(
                            id=None,
                            sealed_product_uuid=sub_uuid,
                            quantity=1,
                            source="sealed_open",
                            notes=f"From opening: {product.name}",
                        )
                        sealed_repo.add(sub_entry)
                        sealed_added += 1

            # Update existing sealed collection entry or create a new one
            sealed_collection_id = data.get("sealed_collection_id")
            sealed_repo = SealedCollectionRepository(conn)

            # Find the entry to mark as opened
            existing_entry = None
            if sealed_collection_id:
                existing_entry = sealed_repo.get(int(sealed_collection_id))
            else:
                # Find first owned entry matching this product
                owned = [
                    e for e in sealed_repo.list_all(status="owned")
                    if e["sealed_product_uuid"] == sealed_product_uuid
                ]
                if owned:
                    existing_entry = sealed_repo.get(owned[0]["id"])

            if existing_entry and existing_entry.status == "owned":
                if existing_entry.quantity > 1:
                    # Split: decrement qty on existing, create new opened entry
                    existing_entry.quantity -= 1
                    sealed_repo.update(existing_entry)
                    opened_entry = SealedCollectionEntry(
                        id=None,
                        sealed_product_uuid=sealed_product_uuid,
                        quantity=1,
                        condition=existing_entry.condition,
                        purchase_price=existing_entry.purchase_price,
                        purchase_date=existing_entry.purchase_date,
                        source=existing_entry.source,
                        seller_name=existing_entry.seller_name,
                        notes=existing_entry.notes,
                        status="opened",
                    )
                    sealed_repo.add(opened_entry)
                else:
                    sealed_repo.dispose(existing_entry.id, "opened")
            elif track_in_sealed:
                # No existing entry to update — create a new one
                parent_entry = SealedCollectionEntry(
                    id=None,
                    sealed_product_uuid=sealed_product_uuid,
                    quantity=1,
                    condition=condition,
                    purchase_price=data.get("purchase_price"),
                    purchase_date=data.get("purchase_date"),
                    source="sealed_open",
                    status="opened",
                )
                sealed_repo.add(parent_entry)

            conn.commit()
        finally:
            conn.close()

        self._send_json({
            "batch_id": batch_id,
            "cards_added": cards_added,
            "sealed_added": sealed_added,
            "errors": errors,
        })

    def _api_sealed_price_history(self, tcgplayer_product_id: str):
        """Return price time series for a sealed product."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT low_price, mid_price, high_price, market_price, direct_low_price, observed_at "
            "FROM sealed_prices WHERE tcgplayer_product_id = ? ORDER BY observed_at",
            (tcgplayer_product_id,),
        ).fetchall()
        conn.close()
        self._send_json([dict(r) for r in rows])

    def _api_sealed_prices_status(self):
        """Return info about cached sealed prices."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT MAX(observed_at) as last_date, COUNT(DISTINCT tcgplayer_product_id) as product_count "
            "FROM sealed_prices"
        ).fetchone()
        conn.close()
        self._send_json({
            "available": row["last_date"] is not None,
            "last_date": row["last_date"],
            "product_count": row["product_count"],
        })

    def _api_sealed_collection_list(self, params: dict):
        """List user's sealed collection with filters."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        set_code = params.get("set_code", [""])[0] or None
        category = params.get("category", [""])[0] or None
        subtype = params.get("subtype", [""])[0] or None
        status = params.get("status", [""])[0] or None

        conn = self._get_conn()
        init_db(conn)
        repo = SealedCollectionRepository(conn)
        entries = repo.list_all(set_code=set_code, category=category, subtype=subtype, status=status)

        # Attach image URLs
        for entry in entries:
            tcg_id = entry.get("tcgplayer_product_id")
            if tcg_id:
                entry["image_url"] = f"https://tcgplayer-cdn.tcgplayer.com/product/{tcg_id}_200w.jpg"
            else:
                entry["image_url"] = None

        conn.close()
        self._send_json(entries)

    def _api_sealed_collection_stats(self):
        """Get sealed collection statistics."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        init_db(conn)
        repo = SealedCollectionRepository(conn)
        stats = repo.stats()
        conn.close()
        self._send_json(stats)

    def _api_sealed_collection_add(self, data: dict):
        """Add a sealed product to the collection."""
        from mtg_collector.db.models import (
            SealedCollectionEntry,
            SealedCollectionRepository,
            SealedProductRepository,
        )
        from mtg_collector.db.schema import init_db

        uuid = data.get("sealed_product_uuid")
        if not uuid:
            self._send_json({"error": "sealed_product_uuid required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)

            # Verify the product exists
            product_repo = SealedProductRepository(conn)
            product = product_repo.get(uuid)
            if not product:
                self._send_json({"error": f"Sealed product '{uuid}' not found"}, 404)
                return

            entry = SealedCollectionEntry(
                id=None,
                sealed_product_uuid=uuid,
                quantity=data.get("quantity", 1),
                condition=data.get("condition", "Near Mint"),
                purchase_price=data.get("purchase_price"),
                purchase_date=data.get("purchase_date"),
                source=data.get("source"),
                seller_name=data.get("seller_name"),
                notes=data.get("notes"),
                status=data.get("status", "owned"),
            )

            repo = SealedCollectionRepository(conn)
            new_id = repo.add(entry)
            conn.commit()

            # Fetch back for response
            created = repo.get(new_id)
        finally:
            conn.close()

        image_url = None
        if product.tcgplayer_product_id:
            image_url = f"https://tcgplayer-cdn.tcgplayer.com/product/{product.tcgplayer_product_id}_200w.jpg"

        self._send_json({
            "id": created.id,
            "sealed_product_uuid": created.sealed_product_uuid,
            "product_name": product.name,
            "set_code": product.set_code,
            "category": product.category,
            "quantity": created.quantity,
            "condition": created.condition,
            "purchase_price": created.purchase_price,
            "purchase_date": created.purchase_date,
            "source": created.source,
            "seller_name": created.seller_name,
            "notes": created.notes,
            "status": created.status,
            "added_at": created.added_at,
            "image_url": image_url,
        })

    def _api_sealed_collection_update(self, entry_id: int, data: dict):
        """Update a sealed collection entry."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = SealedCollectionRepository(conn)

            entry = repo.get(entry_id)
            if not entry:
                self._send_json({"error": "Not found"}, 404)
                return

            # Apply updates from request body
            if "quantity" in data:
                entry.quantity = data["quantity"]
            if "condition" in data:
                entry.condition = data["condition"]
            if "purchase_price" in data:
                entry.purchase_price = data["purchase_price"]
            if "purchase_date" in data:
                entry.purchase_date = data["purchase_date"]
            if "source" in data:
                entry.source = data["source"]
            if "seller_name" in data:
                entry.seller_name = data["seller_name"]
            if "notes" in data:
                entry.notes = data["notes"]

            repo.update(entry)
            conn.commit()
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_sealed_collection_dispose(self, entry_id: int, data: dict):
        """Transition a sealed collection entry's status."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        new_status = data.get("new_status")
        if not new_status:
            self._send_json({"error": "new_status required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = SealedCollectionRepository(conn)

            qty = data.get("quantity")
            if qty is not None:
                qty = int(qty)
            repo.dispose(
                entry_id, new_status,
                sale_price=data.get("sale_price"),
                quantity=qty,
            )
            conn.commit()
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
            return
        finally:
            conn.close()
        self._send_json({"ok": True})

    def _api_sealed_collection_bulk_dispose(self, data: dict):
        """Bulk-transition sealed collection entries' status."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        ids = data.get("ids", [])
        if not ids:
            self._send_json({"error": "ids array required"}, 400)
            return
        new_status = data.get("new_status")
        if not new_status:
            self._send_json({"error": "new_status required"}, 400)
            return

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = SealedCollectionRepository(conn)
            result = repo.bulk_dispose(ids, new_status, sale_price=data.get("sale_price"))
            conn.commit()
        finally:
            conn.close()
        self._send_json({
            "disposed": len(result["disposed"]),
            "skipped": len(result["skipped"]),
            "disposed_ids": result["disposed"],
            "skipped_ids": result["skipped"],
        })

    def _api_sealed_collection_delete(self, entry_id: int):
        """Delete a sealed collection entry."""
        from mtg_collector.db.models import SealedCollectionRepository
        from mtg_collector.db.schema import init_db

        conn = self._get_conn()
        try:
            init_db(conn)
            repo = SealedCollectionRepository(conn)
            deleted = repo.delete(entry_id)
            conn.commit()
        finally:
            conn.close()
        if deleted:
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _api_sealed_fetch_prices(self):
        """Trigger TCGCSV sealed price fetch."""
        from mtg_collector.cli.data_cmd import fetch_sealed_prices

        # Don't pass conn — fetch_sealed_prices writes to shared tables
        # (tcgplayer_groups, sealed_prices) which need a direct connection
        # to the shared DB, not the ATTACHed main DB where they're views.
        result = fetch_sealed_prices(self.db_path)
        self._send_json({"ok": True, **(result or {})})

    def _api_sealed_from_tcgplayer(self, data: dict):
        """Look up a sealed product by TCGPlayer product ID or URL."""
        from mtg_collector.db.models import SealedProductRepository
        from mtg_collector.db.schema import init_db

        raw = data.get("product_id") or data.get("url") or ""
        # Extract numeric product ID from URL or raw input
        # URL format: https://www.tcgplayer.com/product/529964/...
        import re
        match = re.search(r"(?:product/)?(\d+)", str(raw))
        if not match:
            self._send_json({"error": "Could not extract product ID"}, 400)
            return

        tcg_id = match.group(1)

        conn = self._get_conn()
        init_db(conn)
        repo = SealedProductRepository(conn)
        product = repo.get_by_tcgplayer_id(tcg_id)

        if not product:
            conn.close()
            self._send_json({"error": f"No sealed product with TCGPlayer ID {tcg_id}"}, 404)
            return

        image_url = None
        if product.tcgplayer_product_id:
            image_url = f"https://tcgplayer-cdn.tcgplayer.com/product/{product.tcgplayer_product_id}_200w.jpg"

        set_name = None
        row = conn.execute("SELECT set_name FROM sets WHERE set_code = ?", (product.set_code,)).fetchone()
        if row:
            set_name = row["set_name"]
        conn.close()

        self._send_json({
            "uuid": product.uuid,
            "name": product.name,
            "set_code": product.set_code,
            "set_name": set_name,
            "category": product.category,
            "subtype": product.subtype,
            "tcgplayer_product_id": product.tcgplayer_product_id,
            "card_count": product.card_count,
            "release_date": product.release_date,
            "image_url": image_url,
            "purchase_url_tcgplayer": product.purchase_url_tcgplayer,
            "purchase_url_cardkingdom": product.purchase_url_cardkingdom,
        })

    def _send_json(self, obj, status=200):
        self._respond(json.dumps(obj).encode(), "application/json", CACHE_API,
                      status=status)

    def log_message(self, format, *args):
        # Quieter logging — just method and path
        sys.stderr.write(f"{args[0]}\n")


def register(subparsers):
    """Register the crack-pack-server subcommand."""
    parser = subparsers.add_parser(
        "crack-pack-server",
        help="Start the crack-a-pack web UI",
        description="Start a local web server for the crack-a-pack visual UI.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to serve on (default: 8080)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to collection SQLite database (default: ~/.mtgc/collection.sqlite)",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="Serve over HTTPS with a self-signed certificate (enables camera on mobile)",
    )
    parser.set_defaults(func=run)


def _resolve_external_tls_paths():
    """Resolve an operator-supplied certificate pair from the environment.

    Returns ``(cert_path, key_path)`` when both ``MTGC_TLS_CERT`` and
    ``MTGC_TLS_KEY`` are set, or ``None`` when neither is (the zero-config
    self-signed default). Raises when exactly one is set, or when either points
    at something that is not a readable file — a deployer who believes they are
    serving a trusted certificate must never be silently downgraded to the
    self-signed one.
    """
    cert = os.environ.get("MTGC_TLS_CERT", "").strip()
    key = os.environ.get("MTGC_TLS_KEY", "").strip()

    if not cert and not key:
        return None

    if not cert or not key:
        set_var, unset_var = ("MTGC_TLS_KEY", "MTGC_TLS_CERT") if not cert else ("MTGC_TLS_CERT", "MTGC_TLS_KEY")
        raise ValueError(
            f"{set_var} is set but {unset_var} is not. "
            "Set both to serve an externally-provided certificate, or neither to auto-generate a self-signed one."
        )

    paths = {"MTGC_TLS_CERT": Path(cert), "MTGC_TLS_KEY": Path(key)}
    for var, path in paths.items():
        if not path.is_file():
            raise ValueError(f"{var}={path} is not a readable file.")
        with open(path, "rb"):
            pass

    return paths["MTGC_TLS_CERT"], paths["MTGC_TLS_KEY"]


def _generate_self_signed(cert_file, key_file):
    """Write a self-signed certificate/key pair to the given paths."""
    import socket
    import subprocess

    print("Generating self-signed certificate...")
    san = "DNS:localhost,IP:127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        san += f",IP:{local_ip}"
    except Exception:
        pass
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_file), "-out", str(cert_file),
            "-days", "3650", "-nodes",
            "-subj", "/CN=mtgc-local",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
    )


def _build_tls_context(cert_dir):
    """Build the server's SSL context.

    Uses the externally-provided certificate when ``MTGC_TLS_CERT`` /
    ``MTGC_TLS_KEY`` are set; otherwise falls back to the auto-generated
    self-signed pair under ``cert_dir``.
    """
    import ssl

    external = _resolve_external_tls_paths()
    if external is not None:
        cert_file, key_file = external
        print(f"[startup] Using externally-provided certificate: {cert_file}", flush=True)
    else:
        cert_file = cert_dir / "server.pem"
        key_file = cert_dir / "server-key.pem"
        if not cert_file.exists() or not key_file.exists():
            _generate_self_signed(cert_file, key_file)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_file), str(key_file))
    return ctx


def run(args):
    """Run the crack-pack-server command."""
    db_path = get_db_path(getattr(args, "db", None))

    global _ingest_executor, _background_db_path, _shared_db_path
    _shared_db_path = os.environ.get("MTGC_SHARED_DB")
    if _shared_db_path:
        print(f"[startup] Shared reference DB: {_shared_db_path}", flush=True)
    # Presence of MTGC_HTTP_PORT is the switch for the second, plain-HTTP listener.
    # A non-integer value raises out of int() and the process exits non-zero.
    _http_port_env = os.environ.get("MTGC_HTTP_PORT")
    http_port = int(_http_port_env) if _http_port_env is not None else None
    _background_db_path = db_path
    _ingest_executor = ThreadPoolExecutor(max_workers=4)
    _recover_pending_images(db_path)

    # Auto-import MTGJSON data if tables are empty but AllPrintings.json exists
    _conn = sqlite3.connect(db_path)
    _has_data = _conn.execute("SELECT COUNT(*) FROM mtgjson_booster_configs").fetchone()[0]
    _conn.close()
    if not _has_data:
        from mtg_collector.cli.data_cmd import get_allprintings_path, import_mtgjson

        ap = get_allprintings_path()
        if ap.exists():
            print("[startup] MTGJSON tables empty — auto-importing from AllPrintings.json ...", flush=True)
            import_mtgjson(db_path)
        else:
            print("[startup] WARNING: MTGJSON tables empty and AllPrintings.json not found.", flush=True)
            print("[startup] Crack-a-Pack set search will not work. Run: mtg data fetch", flush=True)

    gen = PackGenerator(db_path)

    static_dir = Path(__file__).resolve().parent.parent / "static"
    handler = partial(CrackPackHandler, gen, static_dir, db_path)

    server = ThreadingHTTPServer(("", args.port), handler)
    plain_server = ThreadingHTTPServer(("", http_port), handler) if http_port is not None else None

    if args.https:
        cert_dir = Path(os.environ.get("MTGC_HOME", Path.home() / ".mtgc"))
        ctx = _build_tls_context(cert_dir)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        server.socket.settimeout(10)
        scheme = "https"
    else:
        scheme = "http"

    print(f"Server running at {scheme}://localhost:{args.port}")
    print(f"Crack-a-Pack: {scheme}://localhost:{args.port}/crack")
    print(f"Explore Sheets: {scheme}://localhost:{args.port}/sheets")
    print(f"Collection: {scheme}://localhost:{args.port}/collection")
    print(f"Upload: {scheme}://localhost:{args.port}/upload")
    print(f"Recent: {scheme}://localhost:{args.port}/recent")
    print(f"Disambiguate: {scheme}://localhost:{args.port}/disambiguate")
    print(f"Ingestor (Manual ID): {scheme}://localhost:{args.port}/ingestor-ids")
    print(f"Ingestor (Orders): {scheme}://localhost:{args.port}/ingestor-order")
    if plain_server is not None:
        print(f"Plain HTTP listener: http://localhost:{http_port}")
    print("Press Ctrl+C to stop.")

    if plain_server is not None:
        threading.Thread(target=plain_server.serve_forever, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        _ingest_executor.shutdown(wait=False)
        server.shutdown()
        if plain_server is not None:
            plain_server.shutdown()
