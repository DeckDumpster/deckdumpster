"""Transforms tokenized search queries into AST nodes.

Uses a recursive descent parser over the token stream to handle
operator precedence: OR < AND (implicit) < NOT < atoms.
"""

from __future__ import annotations

from .ast_nodes import (
    AndNode,
    ComparisonNode,
    ExactNameNode,
    NameSearchNode,
    NotNode,
    OrNode,
)
from .grammar import SearchError
from .keywords import KEYWORD_ALIASES


def build_ast(tokens: list[tuple[str, str, str, int]]):
    """Build an AST from a token list using recursive descent parsing."""
    parser = _Parser(tokens)
    result = parser.parse_or()

    if parser.pos < len(parser.tokens):
        tok = parser.tokens[parser.pos]
        raise SearchError(f"Unexpected token: {tok[1]}", position=tok[3])

    return result


class _Parser:
    """Recursive descent parser over the token stream."""

    def __init__(self, tokens: list[tuple[str, str, str, int]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str, str, int] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> tuple[str, str, str, int]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse_or(self):
        """Parse OR expressions (lowest precedence)."""
        left = self.parse_and()

        while self._is_or():
            self.advance()  # consume 'or'
            right = self.parse_and()
            if isinstance(left, OrNode):
                left.children.append(right)
            else:
                left = OrNode(children=[left, right])

        return left

    def _is_or(self) -> bool:
        """Check if current token is the OR keyword."""
        tok = self.peek()
        return tok is not None and tok[0] == "WORD" and tok[1].lower() == "or"

    def _is_and(self) -> bool:
        """Check if current token is the AND keyword (a no-op connector)."""
        tok = self.peek()
        return tok is not None and tok[0] == "WORD" and tok[1].lower() == "and"

    def parse_and(self):
        """Parse AND expressions (implicit by adjacency, or explicit `and` keyword)."""
        children = [self.parse_atom()]

        while self.peek() is not None and not self._is_or() and self.peek()[0] != "RPAREN":
            # Skip explicit `and` connectors — adjacency already implies AND.
            if self._is_and():
                self.advance()
                continue
            children.append(self.parse_atom())

        if len(children) == 1:
            return children[0]
        return AndNode(children=children)

    def parse_atom(self):
        """Parse a single atom: negation, grouped expr, exact name, keyword expr, or bare word."""
        tok = self.peek()
        if tok is None:
            raise SearchError("Unexpected end of query")

        # NEGATE token from tokenizer (handles -keyword:val, -(group), -word)
        if tok[0] == "NEGATE":
            self.advance()  # consume the -
            child = self.parse_atom()
            return NotNode(child=child)

        # Grouped expression
        if tok[0] == "LPAREN":
            self.advance()  # consume (
            inner = self.parse_or()
            rparen = self.peek()
            if rparen is None or rparen[0] != "RPAREN":
                raise SearchError("Missing closing parenthesis", position=tok[3])
            self.advance()  # consume )
            return inner

        # Exact name
        if tok[0] == "EXACT_NAME":
            self.advance()
            return ExactNameNode(name=tok[1])

        # Keyword expression
        if tok[0] == "KEYWORD_EXPR":
            self.advance()
            keyword_raw = tok[1]
            op = tok[2]
            # Next token should be VALUE
            val_tok = self.peek()
            if val_tok is None or val_tok[0] != "VALUE":
                raise SearchError(f"Expected value after {keyword_raw}{op}", position=tok[3])
            self.advance()
            keyword = _resolve_keyword(keyword_raw, tok[3])
            return ComparisonNode(keyword=keyword, operator=op, value=val_tok[1])

        # Bare word
        if tok[0] == "WORD":
            self.advance()
            return NameSearchNode(term=tok[1])

        # VALUE token appearing without a keyword -- treat as bare word
        if tok[0] == "VALUE":
            self.advance()
            return NameSearchNode(term=tok[1])

        raise SearchError(f"Unexpected token: {tok[1]}", position=tok[3])


def _resolve_keyword(raw: str, position: int) -> str:
    """Resolve a keyword alias to its canonical name. Raises SearchError if unknown."""
    lower = raw.lower()
    canonical = KEYWORD_ALIASES.get(lower)
    if canonical is None:
        raise SearchError(f"Unknown keyword: '{raw}'", position=position)
    return canonical
