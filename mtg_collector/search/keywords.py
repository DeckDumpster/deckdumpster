"""Keyword alias registry, color maps, rarity ordering for the search engine."""

# Maps all Scryfall keyword prefixes to canonical internal names
KEYWORD_ALIASES = {
    # Colors
    "c": "color",
    "color": "color",
    "colours": "color",
    "id": "color_identity",
    "identity": "color_identity",
    "ci": "color_identity",
    # Types
    "t": "type",
    "type": "type",
    # Text
    "o": "oracle",
    "oracle": "oracle",
    "fo": "fulloracle",
    "fulloracle": "fulloracle",
    # Mana
    "m": "mana",
    "mana": "mana",
    "mv": "mana_value",
    "manavalue": "mana_value",
    "cmc": "mana_value",
    # Stats
    "pow": "power",
    "power": "power",
    "tou": "toughness",
    "tough": "toughness",
    "toughness": "toughness",
    "pt": "powtou",
    "powtou": "powtou",
    "loy": "loyalty",
    "loyalty": "loyalty",
    # Rarity
    "r": "rarity",
    "rarity": "rarity",
    # Set/edition
    "s": "set",
    "set": "set",
    "e": "set",
    "edition": "set",
    "b": "block",
    "block": "block",
    "st": "set_type",
    "cn": "collector_number",
    "number": "collector_number",
    # People/text
    "a": "artist",
    "artist": "artist",
    "ft": "flavor",
    "flavor": "flavor",
    "wm": "watermark",
    "watermark": "watermark",
    # Keywords/abilities
    "kw": "keyword",
    "keyword": "keyword",
    # Format legality
    "f": "format",
    "format": "format",
    "banned": "banned",
    "restricted": "restricted",
    # Flags
    "is": "is_flag",
    "not": "not_flag",
    "has": "has_flag",
    # Mana production
    "produces": "produces",
    # Dates
    "year": "year",
    "date": "date",
    # Display modifiers (extracted, not compiled to SQL)
    "order": "order",
    "direction": "direction",
    "unique": "unique",
}

# Color values: single chars, full names, guild/shard/wedge names -> color letter strings
COLOR_MAP = {
    # Single chars
    "w": "W",
    "u": "U",
    "b": "B",
    "r": "R",
    "g": "G",
    "c": "C",
    "m": "M",
    # Full names
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
    "colorless": "C",
    "multicolor": "M",
    # Guilds (2-color)
    "azorius": "WU",
    "dimir": "UB",
    "rakdos": "BR",
    "gruul": "RG",
    "selesnya": "WG",
    "orzhov": "WB",
    "izzet": "UR",
    "golgari": "BG",
    "boros": "WR",
    "simic": "UG",
    # Shards (3-color)
    "bant": "WUG",
    "esper": "WUB",
    "grixis": "UBR",
    "jund": "BRG",
    "naya": "WRG",
    # Wedges (3-color)
    "abzan": "WBG",
    "jeskai": "WUR",
    "sultai": "UBG",
    "mardu": "WBR",
    "temur": "URG",
    # Colleges
    "silverquill": "WB",
    "prismari": "UR",
    "witherbloom": "BG",
    "lorehold": "WR",
    "quandrix": "UG",
    # 4-color
    "chaos": "UBRG",
    "aggression": "WBRG",
    "altruism": "WURG",
    "growth": "WUBG",
    "artifice": "WUBR",
}

# Rarity ordering for comparison operators
RARITY_ORDER = {
    "common": 0,
    "c": 0,
    "uncommon": 1,
    "u": 1,
    "rare": 2,
    "r": 2,
    "mythic": 3,
    "m": 3,
    "special": 4,
    "s": 4,
    "bonus": 5,
}

# Rarity aliases for = matching
RARITY_ALIASES = {
    "c": "common",
    "u": "uncommon",
    "r": "rare",
    "m": "mythic",
    "s": "special",
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "mythic": "mythic",
    "special": "special",
    "bonus": "bonus",
}
