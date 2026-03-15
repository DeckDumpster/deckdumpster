#!/usr/bin/env python3
"""Print sample SQL WHERE clauses for commander deck building categories.

Usage:
  commander-sample-queries.py --<category>
  commander-sample-queries.py --list

Categories match template roles (ramp, card-advantage, targeted-disruption,
mass-disruption, lands) and common commander sub-plan themes (sacrifice,
reanimation, tokens, counters, discard, etb, voltron, aristocrats, tribal).

Examples:
  commander-sample-queries.py --ramp
  commander-sample-queries.py --sacrifice
  commander-sample-queries.py --list
"""
import sys

CATEGORIES = {
    # --- Template roles ---
    "ramp": {
        "description": "Mana acceleration: rocks, dorks, land tutors, rituals",
        "queries": [
            # Mana rocks + dorks (Sol Ring, signets, Llanowar Elves, Birds of Paradise)
            ("Mana rocks and dorks",
             "(c.type_line LIKE '%Artifact%' OR c.type_line LIKE '%Creature%') AND c.oracle_text LIKE '%{T}:%Add%' AND c.cmc <= 4"),
            # Land ramp + rituals + burst mana
            ("Land ramp and rituals",
             "(c.oracle_text LIKE '%search your library for%land%onto the battlefield%' OR (c.oracle_text LIKE '%Add {%{%{%' AND c.type_line NOT LIKE '%Land%' AND c.cmc <= 2)) AND c.cmc <= 4"),
            # Cost reducers (Urza's Incubator, Herald's Horn) — narrowed to "you cast"
            ("Cost reducers",
             "c.oracle_text LIKE '%you cast cost%less%' AND c.cmc <= 4"),
            # Treasure generators + sacrifice for mana (Dockside, Smothering Tithe, Ashnod's Altar)
            ("Treasure and sacrifice-for-mana",
             "(c.oracle_text LIKE '%create%Treasure%' OR c.oracle_text LIKE '%Sacrifice a %:%Add%') AND c.cmc <= 4"),
        ],
    },
    "card-advantage": {
        "description": "Draw, selection, recursion, impulse draw",
        "queries": [
            # Draw spells, enchantments, cantrips (Sign in Blood, Phyrexian Arena, Opt)
            ("Draw spells and engines",
             "(c.oracle_text LIKE '%draw%card%' AND (c.type_line LIKE '%Sorcery%' OR c.type_line LIKE '%Instant%' OR c.type_line LIKE '%Enchantment%')) AND c.cmc <= 4"),
            # Creatures that draw (Beast Whisperer, Toski, Midnight Reaper)
            ("Creatures that draw",
             "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%draw%card%' AND c.cmc <= 5"),
            # Impulse draw + looting + equipment draw
            ("Impulse draw, looting, equipment draw",
             "(c.oracle_text LIKE '%exile%top%' AND c.oracle_text LIKE '%you may play%') OR (c.oracle_text LIKE '%draw%' AND c.oracle_text LIKE '%discard%' AND c.cmc <= 3) OR (c.type_line LIKE '%Equipment%' AND c.oracle_text LIKE '%draw%')"),
            # Surveil / scry
            ("Surveil and scry",
             "c.oracle_text LIKE '%surveil%' AND c.cmc <= 3"),
        ],
    },
    "targeted-disruption": {
        "description": "Single-target removal, exile, bounce, counters",
        "queries": [
            # Creature removal — destroy, exile, edict (StP, Go for the Throat, Diabolic Edict)
            ("Creature removal (destroy, exile, edict)",
             "(c.oracle_text LIKE '%destroy target%creature%' OR c.oracle_text LIKE '%exile target%creature%' OR c.oracle_text LIKE '%sacrifices a creature%') AND c.cmc <= 4"),
            # Flexible removal + artifact/enchantment removal (Chaos Warp, Beast Within, Naturalize)
            ("Permanent removal (any type)",
             "(c.oracle_text LIKE '%destroy target permanent%' OR c.oracle_text LIKE '%exile target%permanent%' OR c.oracle_text LIKE '%destroy target%artifact%' OR c.oracle_text LIKE '%destroy target%enchantment%') AND c.cmc <= 4"),
            # Burn removal — exclude lands (Lightning Bolt)
            ("Burn (damage to target)",
             "c.oracle_text LIKE '%deals%damage to%target%' AND c.type_line NOT LIKE '%Land%' AND c.cmc <= 3"),
            # Counterspells + bounce
            ("Counterspells and bounce",
             "(c.oracle_text LIKE '%counter target spell%' OR c.oracle_text LIKE '%return target%to%owner%hand%') AND c.cmc <= 3"),
        ],
    },
    "mass-disruption": {
        "description": "Board wipes, mass bounce, mass exile",
        "queries": [
            # Destroy/exile all creatures + damage-based wipes (Wrath, Damnation, Blasphemous Act)
            ("Board wipes (destroy, exile, damage)",
             "(c.oracle_text LIKE '%destroy all creature%' OR c.oracle_text LIKE '%damage to each creature%' OR c.oracle_text LIKE '%exile all creature%') AND c.cmc <= 9"),
            # -X/-X wipes + overload wipes (Toxic Deluge, Cyclonic Rift)
            ("Mass -X/-X and overload wipes",
             "c.oracle_text LIKE '%all creatures get -%' OR c.oracle_text LIKE '%each creature gets -%' OR (c.oracle_text LIKE '%Overload%' AND (c.oracle_text LIKE '%destroy%' OR c.oracle_text LIKE '%return%'))"),
            # Sacrifice-based wipes (Grave Pact, Dictate of Erebos)
            ("Opponents sacrifice when yours die",
             "c.oracle_text LIKE '%creature you control dies%' AND c.oracle_text LIKE '%sacrifices a creature%'"),
        ],
    },
    "lands": {
        "description": "Mana base: duals, utility lands, fetches",
        "queries": [
            # Dual lands + fetch lands (all nonbasic color-fixing)
            ("Duals and fetches",
             "c.type_line LIKE '%Land%' AND ((c.oracle_text LIKE '%Add {%' AND c.oracle_text LIKE '%or%{%') OR c.oracle_text LIKE '%Sacrifice this land%Search%')"),
            # Utility lands (non-mana abilities, long oracle text to exclude simple duals)
            ("Utility lands",
             "c.type_line LIKE '%Land%' AND c.oracle_text LIKE '%{T}%' AND LENGTH(c.oracle_text) > 120 AND c.cmc = 0"),
        ],
    },

    # --- Common sub-plan themes ---
    "sacrifice": {
        "description": "Sacrifice outlets, payoffs, and fodder",
        "queries": [
            # Free sacrifice outlets (Viscera Seer, Carrion Feeder)
            ("Free sacrifice outlets",
             "c.oracle_text LIKE '%Sacrifice a creature:%' AND c.cmc <= 3"),
            # Death payoffs (Blood Artist, Zulaport Cutthroat)
            ("Death triggers (when creature dies)",
             "c.oracle_text LIKE '%creature%dies%' AND c.oracle_text LIKE '%each opponent%' AND c.cmc <= 4"),
            # Opponents sacrifice (Grave Pact, Dictate of Erebos)
            ("Force opponents to sacrifice",
             "c.oracle_text LIKE '%each opponent sacrifices%'"),
            # Sacrifice fodder that replaces itself
            ("Dies → create token",
             "c.oracle_text LIKE '%When%dies%create%token%' AND c.cmc <= 3"),
            # Recursive creatures (Bloodghast, Reassembling Skeleton)
            ("Recursive creatures (return from graveyard)",
             "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%return%from your graveyard to the battlefield%' AND c.cmc <= 3"),
        ],
    },
    "reanimation": {
        "description": "Return creatures from graveyard to battlefield or hand",
        "queries": [
            # Reanimate to battlefield (Animate Dead, Reanimate, Victimize)
            ("Reanimate to battlefield",
             "c.oracle_text LIKE '%return target creature%from%graveyard to the battlefield%'"),
            # Reanimate to battlefield (put onto)
            ("Put creature from graveyard onto battlefield",
             "c.oracle_text LIKE '%creature card from%graveyard%onto the battlefield%'"),
            # Aura-based reanimation (Animate Dead, Dance of the Dead, Necromancy)
            ("Aura reanimation (enchant creature in graveyard)",
             "c.oracle_text LIKE '%enchant creature card in a graveyard%'"),
            # Mass reanimation (Living Death, Rise of the Dark Realms)
            ("Mass reanimation",
             "c.oracle_text LIKE '%return all creature%from%graveyard%' OR c.oracle_text LIKE '%each%creature card%graveyard%battlefield%'"),
            # Return to hand (Disentomb, Cadaver Imp)
            ("Return creature to hand",
             "c.oracle_text LIKE '%return target creature card from your graveyard to your hand%'"),
            # Self-recurring creatures
            ("Self-recurring creatures",
             "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%Return%from your graveyard%' AND c.oracle_text LIKE '%to the battlefield%'"),
            # Graveyard filling (Buried Alive, Entomb)
            ("Graveyard fillers (tutor to graveyard)",
             "c.oracle_text LIKE '%search your library%put%into%graveyard%'"),
        ],
    },
    "tokens": {
        "description": "Token generators, doublers, and anthem effects",
        "queries": [
            # Token generators (repeatable)
            ("Repeatable token generation",
             "c.oracle_text LIKE '%create%token%' AND c.oracle_text LIKE '%beginning of%' AND c.cmc <= 5"),
            # Token doublers (Anointed Procession, Parallel Lives)
            ("Token doublers",
             "c.oracle_text LIKE '%create%twice that many%' OR c.oracle_text LIKE '%creates twice%'"),
            # Mass token generation
            ("Mass token generation",
             "c.oracle_text LIKE '%create%token%' AND c.type_line LIKE '%Sorcery%' AND c.cmc <= 5"),
            # Anthems (pump all your creatures)
            ("Anthem effects (+X/+X to all)",
             "c.oracle_text LIKE '%creatures you control get +%'"),
            # Populate / copy tokens
            ("Copy or populate tokens",
             "c.oracle_text LIKE '%Populate%' OR c.oracle_text LIKE '%create a token that%s a copy%'"),
        ],
    },
    "counters": {
        "description": "+1/+1 counters, counter synergy, proliferate",
        "queries": [
            # +1/+1 counter placement
            ("Put +1/+1 counters",
             "c.oracle_text LIKE '%put%+1/+1 counter%' AND c.cmc <= 4"),
            # Enters with counters
            ("Enters with +1/+1 counters",
             "c.oracle_text LIKE '%enters%with%+1/+1 counter%' AND c.cmc <= 4"),
            # Counter doubling (Doubling Season, Hardened Scales)
            ("Counter doublers / extra counters",
             "c.oracle_text LIKE '%additional +1/+1 counter%' OR c.oracle_text LIKE '%twice that many%counter%'"),
            # Proliferate
            ("Proliferate",
             "c.oracle_text LIKE '%proliferate%'"),
            # Counter payoffs (when counters are placed)
            ("Counter payoffs",
             "c.oracle_text LIKE '%whenever%+1/+1 counter%' AND c.cmc <= 5"),
            # Counter manipulation (The Ozolith, moving/preserving counters)
            ("Counter manipulation (move, preserve)",
             "c.oracle_text LIKE '%move%counter%' AND c.oracle_text LIKE '%counter%on%'"),
        ],
    },
    "discard": {
        "description": "Discard enablers, madness, graveyard value",
        "queries": [
            # Discard enablers (your own hand)
            ("Discard enablers (you discard)",
             "c.oracle_text LIKE '%discard a card%' AND c.oracle_text NOT LIKE '%opponent%discard%' AND c.cmc <= 3"),
            # Madness cards (cast from discard)
            ("Madness cards",
             "c.oracle_text LIKE '%Madness%'"),
            # Discard payoffs (when you discard)
            ("Discard payoffs (whenever you discard)",
             "c.oracle_text LIKE '%whenever you discard%' OR c.oracle_text LIKE '%whenever%player%discards%'"),
            # Make opponents discard
            ("Force opponent discard",
             "c.oracle_text LIKE '%opponent%discard%' AND c.cmc <= 4"),
            # Graveyard value (cards that want to be in graveyard)
            ("Cards with graveyard value (flashback, unearth, escape)",
             "c.oracle_text LIKE '%Flashback%' OR c.oracle_text LIKE '%Unearth%' OR c.oracle_text LIKE '%Escape%'"),
        ],
    },
    "etb": {
        "description": "Enter-the-battlefield triggers and blink/flicker",
        "queries": [
            # ETB creatures (when enters)
            ("ETB creatures (MV 3 or less)",
             "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%When%enters%' AND c.cmc <= 3"),
            # ETB creatures (higher CMC, bigger effects)
            ("ETB creatures (MV 4-6)",
             "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%When%enters%' AND c.cmc BETWEEN 4 AND 6"),
            # Blink / flicker (Conjurer's Closet, Thassa)
            ("Blink / flicker effects",
             "c.oracle_text LIKE '%exile%then return%to the battlefield%' OR c.oracle_text LIKE '%exile%return%under%control%'"),
            # Panharmonicon effects
            ("ETB doublers",
             "c.oracle_text LIKE '%entering%causes a triggered ability%trigger%additional time%' OR c.oracle_text LIKE '%enter%trigger%additional%'"),
        ],
    },
    "voltron": {
        "description": "Equipment, auras, and commander damage support",
        "queries": [
            # Equipment
            ("Equipment (CMC 3 or less)",
             "c.type_line LIKE '%Equipment%' AND c.cmc <= 3"),
            # Powerful equipment
            ("Equipment (power boosting)",
             "c.type_line LIKE '%Equipment%' AND c.oracle_text LIKE '%+%/+%'"),
            # Auras that boost
            ("Auras (power boosting)",
             "c.type_line LIKE '%Aura%' AND c.oracle_text LIKE '%+%/+%' AND c.oracle_text LIKE '%Enchant creature%'"),
            # Protection / evasion
            ("Evasion (unblockable, trample, flying)",
             "c.oracle_text LIKE '%can''t be blocked%' OR (c.oracle_text LIKE '%Enchant creature%' AND c.oracle_text LIKE '%flying%')"),
            # Equipment tutors
            ("Equipment/aura tutors",
             "c.oracle_text LIKE '%search your library for%Equipment%' OR c.oracle_text LIKE '%search your library for%Aura%'"),
        ],
    },
    "tribal": {
        "description": "Tribal synergies (use with type filter)",
        "queries": [
            # Lord effects (other X get +1/+1)
            ("Lords (+1/+1 to creature type)",
             "c.oracle_text LIKE '%you control get +%' AND c.type_line LIKE '%Creature%'"),
            # Tribal cost reduction
            ("Tribal cost reduction",
             "c.oracle_text LIKE '%cost%less to cast%' AND c.type_line LIKE '%Creature%'"),
            # Tribal card draw
            ("Tribal card draw",
             "c.oracle_text LIKE '%Whenever%you control enters%draw%' OR c.oracle_text LIKE '%Whenever you cast a%spell%draw%'"),
            # Changelings (all creature types)
            ("Changelings",
             "c.oracle_text LIKE '%Changeling%' AND c.type_line LIKE '%Creature%'"),
        ],
    },
}

# --- Main ---
if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

arg = sys.argv[1].lstrip("-").lower()

if arg == "list":
    print("Available categories:\n")
    for name, info in CATEGORIES.items():
        print(f"  --{name:<25} {info['description']}")
    sys.exit(0)

if arg not in CATEGORIES:
    print(f"Unknown category: {arg}")
    print(f"Run with --list to see available categories.")
    sys.exit(1)

cat = CATEGORIES[arg]
print(f"=== {arg.replace('-', ' ').title()} ===")
print(f"{cat['description']}\n")

for label, query in cat["queries"]:
    print(f"  {label}:")
    print(f"    \"{query}\"\n")
