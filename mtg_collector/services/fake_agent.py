"""Fake agent for testing — returns hardcoded responses keyed by image MD5.

Drop-in replacement for run_agent() in services/agent.py. Activated by
setting MTGC_FAKE_AGENT=1 in the environment.
"""

import hashlib
from pathlib import Path

RESPONSES = {
    "d6e51a55cb0d624587ae3ea8ddb6d360": {  # Brimstone Mage
        "cards": [
            {
                "name": "Brimstone Mage",
                "set_code": "roe",
                "collector_number": "137",
                "fragment_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "notes": "Original printing from Rise of the Eldrazi",
                "type": "Creature \u2014 Human Shaman",
                "artist": "Volkan Baga",
            },
            {
                "name": "Brimstone Mage",
                "set_code": "plst",
                "collector_number": "ROE-137",
                "fragment_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "notes": "Reprint from The List",
                "type": "Creature \u2014 Human Shaman",
                "artist": "Volkan Baga",
            },
        ],
        "trace": [
            "[AGENT] Starting with 11 OCR fragments (max_calls=13, model=claude-haiku-4-5-20251001)",
            "[AGENT/haiku] I'll identify this card by searching the database with the information from the OCR fragments.",
            '[TOOL CALL/haiku] query_local_db: {"sql": "SELECT c.oracle_id, c.name, c.type_line, c.mana_cost, c.oracle_text, p.printing_id, p.set_code, p.collector_number, p.rarity, s.set_name, s.released_at FROM cards c LEFT JOIN printings p ON c.oracle_id = p.oracle_id LEFT JOIN sets s ON p.set_code = s.set_code WHERE c.name = \'Brimstone Mage\' ORDER BY s.released_at DESC"}',
            "[TOOL RESULT] query_local_db: 81dcb85e-d61f-430b-9540-5a3bb1378d5a | Brimstone Mage | ...",
            "[AGENT/haiku] The card is **Brimstone Mage**. There are two printings in the database.",
            "[FINAL] Tool calls used: 1/13",
            "[FINAL] Requesting structured output...",
        ],
        "usage": {
            "haiku": {"input": 10432, "output": 561},
            "sonnet": {"input": 0, "output": 0},
            "opus": {"input": 0, "output": 0},
            "cache_read": 0,
            "cache_creation": 0,
        },
    },
}


def run_agent(
    image_path: str,
    ocr_fragments: list[dict],
    max_calls: int | None = None,
    status_callback=None,
    trace_out: list[str] | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Return a hardcoded agent response for the given image.

    Raises ValueError if no response is registered for the image's MD5.
    """
    md5 = hashlib.md5(Path(image_path).read_bytes()).hexdigest()
    data = RESPONSES.get(md5)
    if data is None:
        raise ValueError(f"No fake agent data for MD5={md5}")

    trace = list(data["trace"])
    if trace_out is not None:
        trace_out.extend(trace)
    if status_callback:
        status_callback("Fake agent: cached response")

    return data["cards"], trace, data["usage"]
