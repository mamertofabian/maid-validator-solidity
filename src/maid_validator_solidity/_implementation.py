"""Collect declarations from Solidity's syntax tree."""

from __future__ import annotations

from maid_runner.core.types import ArgSpec, ArtifactKind
from maid_runner.validators.base import FoundArtifact
from tree_sitter import Node

from maid_validator_solidity._parse import (
    _name,
    _parameter_type,
    _parameters,
    _text,
    _visibility,
)
from maid_validator_solidity._types import _signature_type

_CONTAINERS = {"contract_declaration", "interface_declaration", "library_declaration"}
_CALLABLES = {
    "function_definition",
    "constructor_definition",
    "fallback_receive_definition",
}


def _collect_implementation(root: Node, source: bytes) -> list[FoundArtifact]:
    artifacts: list[FoundArtifact] = []
    for node in root.named_children:
        _declaration(node, source, artifacts)
    return artifacts


def _declaration(
    node: Node,
    source: bytes,
    artifacts: list[FoundArtifact],
    owner: str | None = None,
    container: str = "",
) -> None:
    name = _name(node, source)
    # Qualifying a nested type would hide its leading underscore from MAID's
    # name-based privacy rule. Omit that private subtree before qualification.
    if (
        owner
        and name.startswith("_")
        and node.type
        in {
            "struct_declaration",
            "enum_declaration",
            "user_defined_type_definition",
        }
    ):
        return
    qualified = f"{owner}.{name}" if owner else name
    location = {"line": node.start_point.row + 1, "column": node.start_point.column + 1}
    if node.type in _CONTAINERS:
        kind = (
            ArtifactKind.INTERFACE
            if node.type == "interface_declaration"
            else ArtifactKind.CLASS
        )
        bases = tuple(
            _text(child.child_by_field_name("ancestor"), source)
            for child in node.named_children
            if child.type == "inheritance_specifier"
        )
        artifacts.append(FoundArtifact(kind, qualified, bases=bases, **location))
        body = node.child_by_field_name("body")
        if body:
            for child in body.named_children:
                _declaration(child, source, artifacts, qualified, node.type)
    elif node.type == "struct_declaration":
        artifacts.append(FoundArtifact(ArtifactKind.CLASS, qualified, **location))
        body = node.child_by_field_name("body")
        if body:
            for child in body.named_children:
                _declaration(child, source, artifacts, qualified, node.type)
    elif node.type == "enum_declaration":
        artifacts.append(FoundArtifact(ArtifactKind.ENUM, qualified, **location))
    elif node.type == "user_defined_type_definition":
        underlying = next(
            (child for child in node.named_children if child.type == "primitive_type"),
            None,
        )
        artifacts.append(
            FoundArtifact(
                ArtifactKind.TYPE,
                qualified,
                type_annotation=_text(underlying, source),
                **location,
            )
        )
    elif node.type in {"state_variable_declaration", "struct_member"}:
        if (
            node.type == "state_variable_declaration"
            and _visibility(node, source) != "public"
        ):
            return
        artifacts.append(
            FoundArtifact(
                ArtifactKind.ATTRIBUTE,
                name,
                of=owner,
                type_annotation=_parameter_type(node, source),
                **location,
            )
        )
    elif node.type in _CALLABLES:
        special = node.type != "function_definition"
        visibility = _visibility(node, source)
        if not special and owner:
            visible = visibility in {"public", "external"}
            visible |= container == "library_declaration" and visibility != "private"
            visible |= container == "interface_declaration"
            if not visible:
                return
        if node.type == "constructor_definition":
            name = "constructor"
        elif node.type == "fallback_receive_definition":
            name = node.children[0].type
        parameters, return_parameters = _parameters(node)
        args = tuple(
            ArgSpec(name=_name(param, source), type=_parameter_type(param, source))
            for param in parameters
        )
        returns = [_parameter_type(param, source) for param in return_parameters]
        return_type = (
            "void"
            if not returns
            else returns[0] if len(returns) == 1 else f"({', '.join(returns)})"
        )
        signature = (
            f"{name}({','.join(_signature_type(arg.type or '') for arg in args)})"
        )
        artifacts.append(
            FoundArtifact(
                ArtifactKind.METHOD if owner else ArtifactKind.FUNCTION,
                name,
                of=owner,
                args=args,
                returns=return_type,
                signature=signature,
                **location,
            )
        )
