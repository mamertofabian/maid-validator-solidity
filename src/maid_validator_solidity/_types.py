"""Conservative lexical Solidity type comparison; no semantic alias guessing."""

from __future__ import annotations

import re

_ALIASES = {"uint": "uint256", "int": "int256", "byte": "bytes1"}
_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|[0-9]+|=>|[^\s]")
_LOCATIONS = frozenset({"memory", "storage", "calldata"})


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_ALIASES.get(token, token) for token in _TOKEN.findall(value))


def _types_match(manifest_type: str | None, implementation_type: str | None) -> bool:
    if manifest_type is None:
        return True
    if implementation_type is None:
        return False
    return _tokens(manifest_type) == _tokens(implementation_type)


def _signature_type(value: str) -> str:
    tokens = [token for token in _tokens(value) if token not in _LOCATIONS]
    result = ""
    previous = ""
    for token in tokens:
        if previous and previous[-1].isalnum() and token[0].isalnum():
            result += " "
        result += token
        previous = token
    return result
