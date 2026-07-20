"""Tokenizer and parser for Scryfall-style search queries.

Uses a hand-rolled regex tokenizer + recursive descent parser (in transformer.py)
because the grammar has context-sensitive aspects that make a pure CFG awkward:
- keyword detection depends on adjacency to operators (no space before : or =)
- `or` is a keyword between clauses but a bare word otherwise
- `-` prefix for negation must not conflict with hyphens in card names
"""

from __future__ import annotations

import re

# Pre-compiled regex for tokenization.
# Order matters: more specific patterns must come before more general ones.
# The NEGATE pattern handles `-` prefix before keyword/word patterns.
_TOKEN_PATTERNS = [
    ("LPAREN", re.compile(r"\(")),
    ("RPAREN", re.compile(r"\)")),
    ("EXACT_NAME", re.compile(r'!"([^"]*)"')),
    ("EXACT_NAME_UNQUOTED", re.compile(r"!(\S+)")),
    # Negated keyword with comparison op: -word(!=|<=|>=|<|>|=)
    ("NEG_KEYWORD_COMPARE", re.compile(r"-([a-zA-Z][a-zA-Z0-9_]*)(!=|<=|>=|<|>|=)")),
    # Negated keyword with colon: -word:
    ("NEG_KEYWORD_COLON", re.compile(r"-([a-zA-Z][a-zA-Z0-9_]*):")),
    # keyword with comparison op: word(!=|<=|>=|<|>|=)
    ("KEYWORD_COMPARE", re.compile(r"([a-zA-Z][a-zA-Z0-9_]*)(!=|<=|>=|<|>|=)")),
    # keyword with colon: word:
    ("KEYWORD_COLON", re.compile(r"([a-zA-Z][a-zA-Z0-9_]*):")),
    ("QUOTED_STRING", re.compile(r'"([^"]*)"')),
    # Negation prefix followed by a parenthesized group or word
    ("NEGATE", re.compile(r"-(?=[\(\"]|[a-zA-Z])")),
    # bare word: everything else up to whitespace or parens
    ("WORD", re.compile(r"[^\s\(\)]+")),
]


class SearchError(Exception):
    """Error during search query parsing."""

    def __init__(self, message: str, position: int = -1):
        super().__init__(message)
        self.position = position


def tokenize(query: str) -> list[tuple[str, str, str, int]]:
    """Tokenize a search query into (type, key_or_word, operator, value, position) tuples.

    Returns list of tuples: (token_type, raw_text, extra_data, position)
    """
    tokens = []
    pos = 0
    length = len(query)

    while pos < length:
        # Skip whitespace
        if query[pos].isspace():
            pos += 1
            continue

        matched = False
        for name, pattern in _TOKEN_PATTERNS:
            m = pattern.match(query, pos)
            if m:
                if name == "LPAREN":
                    tokens.append(("LPAREN", "(", "", pos))
                elif name == "RPAREN":
                    tokens.append(("RPAREN", ")", "", pos))
                elif name == "EXACT_NAME":
                    tokens.append(("EXACT_NAME", m.group(1), "", pos))
                elif name == "EXACT_NAME_UNQUOTED":
                    tokens.append(("EXACT_NAME", m.group(1), "", pos))
                elif name in ("NEG_KEYWORD_COMPARE", "NEG_KEYWORD_COLON"):
                    # Negated keyword: emit NEGATE + KEYWORD_EXPR + VALUE
                    tokens.append(("NEGATE", "-", "", pos))
                    keyword = m.group(1)
                    op = m.group(2) if name == "NEG_KEYWORD_COMPARE" else ":"
                    val_pos = m.end()
                    val, val_end, quoted = _read_value(query, val_pos)
                    op, val, val_pos = _fold_colon_operator(op, val, val_pos, quoted)
                    tokens.append(("KEYWORD_EXPR", keyword, op, pos + 1))
                    tokens.append(("VALUE", val, "", val_pos))
                    pos = val_end
                    matched = True
                    break
                elif name == "KEYWORD_COMPARE":
                    keyword = m.group(1)
                    op = m.group(2)
                    # Now read the value
                    val_pos = m.end()
                    val, val_end, _quoted = _read_value(query, val_pos)
                    tokens.append(("KEYWORD_EXPR", keyword, op, pos))
                    tokens.append(("VALUE", val, "", val_pos))
                    pos = val_end
                    matched = True
                    break
                elif name == "KEYWORD_COLON":
                    keyword = m.group(1)
                    # Now read the value
                    val_pos = m.end()
                    val, val_end, quoted = _read_value(query, val_pos)
                    op, val, val_pos = _fold_colon_operator(":", val, val_pos, quoted)
                    tokens.append(("KEYWORD_EXPR", keyword, op, pos))
                    tokens.append(("VALUE", val, "", val_pos))
                    pos = val_end
                    matched = True
                    break
                elif name == "NEGATE":
                    tokens.append(("NEGATE", "-", "", pos))
                elif name == "QUOTED_STRING":
                    # Bare quoted string (not after keyword) -- treat as name search
                    tokens.append(("WORD", m.group(1), "", pos))
                elif name == "WORD":
                    tokens.append(("WORD", m.group(0), "", pos))

                pos = m.end()
                matched = True
                break

        if not matched:
            raise SearchError(f"Unexpected character '{query[pos]}'", position=pos)

    return tokens


# Comparison operators that may follow a `:`, longest-first so that `>=`
# is preferred over `>` and `!=` over a bare `=`.
_COLON_FOLDABLE_OPS = ("!=", "<=", ">=", "<", ">", "=")


def _fold_colon_operator(
    op: str, val: str, val_pos: int, quoted: bool
) -> tuple[str, str, int]:
    """Fold a comparison operator written after a colon into the operator slot.

    Scryfall-style queries accept both ``mv>5`` and ``mv:>5``. The tokenizer
    matches ``mv:`` first, leaving ``>5`` as the value; without this fold the
    compiler receives operator ``:`` and the literal value ``">5"``, which is
    not a number and previously compiled to a match-nothing ``1=0`` clause.

    Only unquoted values are folded, so ``o:">"`` still searches for a literal
    ``>`` character.
    """
    if op != ":" or quoted:
        return (op, val, val_pos)

    for candidate in _COLON_FOLDABLE_OPS:
        if val.startswith(candidate):
            return (candidate, val[len(candidate) :], val_pos + len(candidate))

    return (op, val, val_pos)


def _read_value(query: str, pos: int) -> tuple[str, int, bool]:
    """Read a value starting at pos. Handles quoted strings and unquoted tokens.

    Returns ``(value, end_position, was_quoted)``.
    """
    if pos >= len(query):
        return ("", pos, False)

    if query[pos] == '"':
        # Quoted value
        end = query.find('"', pos + 1)
        if end == -1:
            raise SearchError("Unterminated quoted string", position=pos)
        return (query[pos + 1 : end], end + 1, True)
    else:
        # Unquoted value: read until whitespace or ) or end
        end = pos
        while end < len(query) and query[end] not in (" ", "\t", "\n", "\r", ")"):
            end += 1
        return (query[pos:end], end, False)


def parse_query(query: str):
    """Parse a Scryfall-style search query string into an AST.

    Returns an ASTNode.
    """
    from .transformer import build_ast

    query = query.strip()
    if not query:
        raise SearchError("Empty search query")

    try:
        tokens = tokenize(query)
    except SearchError:
        raise

    try:
        return build_ast(tokens)
    except SearchError:
        raise
