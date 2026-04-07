"""Scryfall-style search query parser for the MTG collection app.

Public API:
    parse_query(q: str) -> ASTNode  -- Parse a query string into an AST
    SearchError                     -- Raised on invalid queries

AST node types:
    AndNode, OrNode, NotNode, ComparisonNode, NameSearchNode, ExactNameNode
"""

from .ast_nodes import (
    AndNode,
    ASTNode,
    ComparisonNode,
    ExactNameNode,
    NameSearchNode,
    NotNode,
    OrNode,
)
from .compiler import CompiledQuery, compile_query, execute_search, explain
from .grammar import SearchError, parse_query

__all__ = [
    "parse_query",
    "compile_query",
    "execute_search",
    "explain",
    "SearchError",
    "CompiledQuery",
    "ASTNode",
    "AndNode",
    "OrNode",
    "NotNode",
    "ComparisonNode",
    "NameSearchNode",
    "ExactNameNode",
]
