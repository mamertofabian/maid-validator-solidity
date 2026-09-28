"""Tree-sitter adapter shared by the two collection modes."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from functools import lru_cache

import tree_sitter_solidity
from tree_sitter import Language, Node, Parser


@lru_cache(maxsize=1)
def _language() -> Language:
    # The Solidity grammar currently exposes a legacy integer language pointer.
    # Only suppress that binding compatibility warning, not parsing diagnostics.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", "int argument support is deprecated", DeprecationWarning
        )
        return Language(tree_sitter_solidity.language())


def _parse(source: str) -> tuple[bytes, Node | None, list[str]]:
    try:
        encoded = source.encode("utf-8")
    except UnicodeEncodeError as exc:
        return b"", None, [f"Invalid UTF-8 source: {exc}"]
    root = Parser(_language()).parse(encoded).root_node
    errors = []
    if root.has_error:
        for node in _walk(root):
            if node.is_error or node.is_missing:
                row, column = node.start_point
                errors.append(
                    f"Solidity syntax error at {row + 1}:{column + 1}"
                    f" ({'missing ' if node.is_missing else ''}{node.type})"
                )
        if not errors:
            errors.append("Solidity syntax error")
    return encoded, root, errors


def _walk(node: Node) -> Iterator[Node]:
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _name(node: Node, source: bytes) -> str:
    return _text(node.child_by_field_name("name"), source)


def _visibility(node: Node, source: bytes) -> str:
    return next(
        (
            _text(child, source)
            for child in node.named_children
            if child.type == "visibility"
        ),
        "",
    )


def _parameter_type(node: Node, source: bytes) -> str:
    declared = _text(node.child_by_field_name("type"), source)
    location = _text(node.child_by_field_name("location"), source)
    return f"{declared} {location}" if location else declared


def _parameters(node: Node) -> tuple[list[Node], list[Node]]:
    """Separate inputs and outputs, including the grammar's flat fallback form."""
    inputs: list[Node] = []
    outputs: list[Node] = []
    in_returns = False
    for child in node.children:
        if child.type == "returns":
            in_returns = True
        elif child.type == "parameter":
            (outputs if in_returns else inputs).append(child)
        elif child.type == "return_type_definition":
            outputs.extend(p for p in child.named_children if p.type == "parameter")
    return inputs, outputs
