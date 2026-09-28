"""Foundry references with bounded lexical binding, not control-flow inference."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import FoundArtifact
from tree_sitter import Node

from maid_validator_solidity._parse import _name, _parameters, _text, _visibility

_CONTAINERS = {"contract_declaration", "library_declaration", "interface_declaration"}
_SCOPES = {"function_body", "block_statement", "for_statement", "catch_clause"}


def _collect_behavioral(root: Node, source: bytes) -> list[FoundArtifact]:
    types = _type_names(root, source)
    artifacts: list[FoundArtifact] = []
    for contract in root.named_children:
        if contract.type not in _CONTAINERS:
            continue
        body = contract.child_by_field_name("body")
        if body is None:
            continue
        functions = [
            node for node in body.named_children if node.type == "function_definition"
        ]
        tests = [node for node in functions if _is_test(node, source)]
        if not tests:
            continue
        owner = _name(contract, source)
        contract_types = types | _type_names(body, source, owner)
        fields: dict[str, str | None] = {"this": owner}
        for member in body.named_children:
            if member.type == "state_variable_declaration":
                fields[_name(member, source)] = _declared_owner(
                    member, source, contract_types
                )
            elif member.type in {"function_definition", "modifier_definition"}:
                fields[_name(member, source)] = None
        for member in body.named_children:
            if member.type == "state_variable_declaration":
                value = member.child_by_field_name("value")
                if value:
                    _visit(value, source, dict(fields), contract_types, artifacts)
        for function in functions:
            name = _name(function, source)
            if function not in tests and not (
                name == "setUp"
                and _visibility(function, source) in {"public", "external"}
            ):
                continue
            if function in tests:
                artifacts.append(
                    _reference(ArtifactKind.TEST_FUNCTION, name, owner, function)
                )
            bindings = dict(fields)
            inputs, outputs = _parameters(function)
            for param in inputs + outputs:
                if _name(param, source):
                    bindings[_name(param, source)] = _declared_owner(
                        param, source, contract_types
                    )
            function_body = function.child_by_field_name("body")
            if function_body:
                _visit(function_body, source, bindings, contract_types, artifacts)
    # Preserve source order while discarding exact duplicates at the same location.
    return list(dict.fromkeys(artifacts))


def _type_names(root: Node, source: bytes, owner: str | None = None) -> dict[str, str]:
    names = {}
    for node in root.named_children:
        if node.type in _CONTAINERS | {
            "struct_declaration",
            "enum_declaration",
            "user_defined_type_definition",
        }:
            name = _name(node, source)
            names[name] = f"{owner}.{name}" if owner else name
        elif node.type == "import_directive":
            children = node.children
            for index, child in enumerate(children):
                if node.field_name_for_child(index) != "import_name":
                    continue
                original = _text(child, source)
                local = original
                if (
                    index + 2 < len(children)
                    and node.field_name_for_child(index + 2) == "alias"
                ):
                    local = _text(children[index + 2], source)
                names[local] = original
    return names


def _declared_owner(node: Node, source: bytes, types: dict[str, str]) -> str | None:
    type_node = node.child_by_field_name("type")
    if type_node is None:
        return None
    # Arrays/mappings/function pointers are not instances of their element types.
    children = type_node.named_children
    if len(children) != 1 or children[0].type != "user_defined_type":
        return None
    if any(child.type in {"[", "]"} for child in type_node.children):
        return None
    spelling = _text(children[0], source)
    head, separator, tail = spelling.partition(".")
    return types.get(head, head) + (separator + tail if separator else "")


def _is_test(node: Node, source: bytes) -> bool:
    name = _name(node, source)
    return (
        name.startswith(("test", "invariant"))
        and _visibility(node, source) in {"public", "external"}
        and node.child_by_field_name("body") is not None
    )


def _unwrap(node: Node | None) -> Node | None:
    while node is not None and node.type in {"expression", "parenthesized_expression"}:
        if len(node.named_children) != 1:
            break
        node = node.named_children[0]
    return node


def _receiver(
    node: Node | None,
    source: bytes,
    bindings: dict[str, str | None],
    types: dict[str, str],
) -> str | None:
    node = _unwrap(node)
    if node is None:
        return None
    if node.type == "identifier":
        name = _text(node, source)
        return bindings[name] if name in bindings else types.get(name)
    if node.type == "call_expression":
        callee = _unwrap(node.child_by_field_name("function"))
        if callee is not None and callee.type == "struct_expression":
            callee = _unwrap(callee.child_by_field_name("type"))
        if callee is not None and callee.type == "identifier":
            name = _text(callee, source)
            # A local value/function shadows an imported type even if unresolved.
            if name not in bindings and name in types:
                return types[name]
        if callee is not None and callee.type == "new_expression":
            return _new_owner(callee, source, types)
    return None


def _new_owner(node: Node, source: bytes, types: dict[str, str]) -> str | None:
    type_node = node.child_by_field_name("name")
    if type_node is None or any(
        child.type in {"[", "]"} for child in type_node.children
    ):
        return None
    if not any(child.type == "user_defined_type" for child in type_node.named_children):
        return None
    spelling = _text(type_node, source)
    head, separator, tail = spelling.partition(".")
    return types.get(head, head) + (separator + tail if separator else "")


def _reference(
    kind: ArtifactKind, name: str, owner: str | None, node: Node
) -> FoundArtifact:
    return FoundArtifact(
        kind,
        name,
        of=owner,
        line=node.start_point.row + 1,
        column=node.start_point.column + 1,
    )


def _visit(
    node: Node,
    source: bytes,
    bindings: dict[str, str | None],
    types: dict[str, str],
    artifacts: list[FoundArtifact],
) -> None:
    if node.type in _SCOPES:
        bindings = dict(bindings)
    if node.type in {"variable_declaration", "parameter"}:
        if _name(node, source):
            bindings[_name(node, source)] = _declared_owner(node, source, types)
        return
    if node.type == "try_statement":
        attempt = node.child_by_field_name("attempt")
        if attempt:
            _visit(attempt, source, bindings, types, artifacts)
        success_bindings = dict(bindings)
        for child in node.named_children:
            if child.type == "parameter":
                _visit(child, source, success_bindings, types, artifacts)
        body = node.child_by_field_name("body")
        if body:
            _visit(body, source, success_bindings, types, artifacts)
        for child in node.named_children:
            if child.type == "catch_clause":
                _visit(child, source, bindings, types, artifacts)
        return
    if node.type in {"type_name", "comment", "string_literal", "assembly_statement"}:
        return
    if node.type == "call_expression":
        _call(node, source, bindings, types, artifacts)
        return
    if node.type == "member_expression":
        owner = _receiver(node.child_by_field_name("object"), source, bindings, types)
        name = _text(node.child_by_field_name("property"), source)
        if owner and name:
            artifacts.append(_reference(ArtifactKind.ATTRIBUTE, name, owner, node))
    for child in node.named_children:
        _visit(child, source, bindings, types, artifacts)


def _call(
    node: Node,
    source: bytes,
    bindings: dict[str, str | None],
    types: dict[str, str],
    artifacts: list[FoundArtifact],
) -> None:
    callee = _unwrap(node.child_by_field_name("function"))
    # Solidity represents call options such as target.pay{value: n} as a struct
    # expression. Traverse their values while preserving the underlying callee.
    if callee is not None and callee.type == "struct_expression":
        for field in callee.named_children:
            if field.type == "struct_field_assignment":
                _visit(field, source, bindings, types, artifacts)
        callee = _unwrap(callee.child_by_field_name("type"))
    if callee is not None:
        if callee.type == "member_expression":
            receiver = callee.child_by_field_name("object")
            owner = _receiver(receiver, source, bindings, types)
            name = _text(callee.child_by_field_name("property"), source)
            if owner and name:
                artifacts.append(_reference(ArtifactKind.METHOD, name, owner, callee))
                direct = _unwrap(receiver)
                if direct is not None and direct.type == "identifier":
                    label = _text(direct, source)
                    if label not in bindings and label in types:
                        artifacts.append(
                            _reference(ArtifactKind.CLASS, owner, None, direct)
                        )
            if receiver:
                _visit(receiver, source, bindings, types, artifacts)
        elif callee.type == "new_expression":
            owner = _new_owner(callee, source, types)
            if owner:
                artifacts.extend(
                    [
                        _reference(ArtifactKind.CLASS, owner, None, callee),
                        _reference(ArtifactKind.METHOD, "constructor", owner, callee),
                    ]
                )
        elif callee.type == "identifier":
            name = _text(callee, source)
            if name not in bindings and name in types:
                # This can be an imported free function or a cast. A function
                # identity cannot stand in for a class/interface declaration.
                artifacts.append(
                    _reference(ArtifactKind.FUNCTION, types[name], None, callee)
                )
    for child in node.named_children:
        if child.type == "call_argument":
            _visit(child, source, bindings, types, artifacts)
