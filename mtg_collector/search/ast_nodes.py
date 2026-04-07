"""AST node definitions for the search query parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class AndNode:
    """Implicit AND of multiple criteria."""

    children: list  # list of ASTNode


@dataclass
class OrNode:
    """Explicit OR between clauses."""

    children: list  # list of ASTNode


@dataclass
class NotNode:
    """Negation (- prefix)."""

    child: object  # ASTNode


@dataclass
class ComparisonNode:
    """A keyword:operator:value triple like c:r, mv>=3, t:creature."""

    keyword: str  # canonical keyword name (after alias resolution)
    operator: str  # ':', '=', '!=', '<', '>', '<=', '>='
    value: str  # the value string (quotes stripped)


@dataclass
class NameSearchNode:
    """Bare word(s) for implicit name search."""

    term: str


@dataclass
class ExactNameNode:
    """!"Lightning Bolt" exact name match."""

    name: str


ASTNode = Union[AndNode, OrNode, NotNode, ComparisonNode, NameSearchNode, ExactNameNode]
