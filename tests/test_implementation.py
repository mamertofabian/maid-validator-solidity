"""Public contract for Solidity declaration collection."""

from pathlib import Path

import pytest
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import BaseValidator, CollectionResult


def _collect(source):
    from maid_validator_solidity.validator import SolidityValidator

    result = SolidityValidator().collect_implementation_artifacts(source, "Api.sol")
    assert isinstance(result, CollectionResult)
    assert result.language == "solidity"
    assert result.file_path == "Api.sol"
    assert not result.errors
    return result.artifacts


def test_plugin_supports_only_solidity_extension():
    from maid_validator_solidity.validator import SolidityValidator

    validator = SolidityValidator()
    assert isinstance(validator, BaseValidator)
    assert SolidityValidator.supported_extensions() == (".sol",)
    assert validator.can_validate(Path("test/Vault.t.sol"))
    assert not validator.can_validate("Vault.cs")


def test_contract_interface_library_and_inheritance_are_collected():
    artifacts = _collect("""
        interface IVault { function withdraw(uint amount) external; }
        abstract contract Base {}
        contract Vault is Base, IVault {
            function withdraw(uint amount) external override {}
        }
        library Math { function double(uint x) internal pure returns (uint) { return x * 2; } }
    """)
    identities = {(a.kind, a.name, a.of) for a in artifacts}
    assert (ArtifactKind.INTERFACE, "IVault", None) in identities
    assert (ArtifactKind.CLASS, "Base", None) in identities
    assert (ArtifactKind.CLASS, "Vault", None) in identities
    assert (ArtifactKind.CLASS, "Math", None) in identities
    assert (ArtifactKind.METHOD, "double", "Math") in identities
    assert next(a for a in artifacts if a.name == "Vault").bases == ("Base", "IVault")


def test_callable_arguments_returns_visibility_and_raw_type_spelling():
    artifacts = _collect("""
        contract Vault {
            function deposit(uint amount, bytes calldata memo) external payable
                returns (uint256 shares, address receiver) { return (amount, msg.sender); }
            function hidden() private {}
            function internalHelper() internal {}
            function publicHelper() public {}
        }
    """)
    method = next(a for a in artifacts if a.name == "deposit")
    assert method.kind == ArtifactKind.METHOD and method.of == "Vault"
    assert [(arg.name, arg.type) for arg in method.args] == [
        ("amount", "uint"),
        ("memo", "bytes calldata"),
    ]
    assert method.returns == "(uint256, address)"
    assert method.signature == "deposit(uint256,bytes)"
    assert method.line is not None and method.line > 0
    assert {a.name for a in artifacts} == {"Vault", "deposit", "publicHelper"}


def test_overloads_have_distinct_definition_signatures():
    artifacts = _collect("""
        contract Vault {
            function get(uint key) external pure returns (uint) { return key; }
            function get(address key) external pure returns (address) { return key; }
        }
    """)
    overloads = [a for a in artifacts if a.name == "get"]
    assert {a.signature for a in overloads} == {"get(uint256)", "get(address)"}
    assert len({a.contract_key() for a in overloads}) == 2


def test_constructor_receive_fallback_and_free_function_have_stable_names():
    artifacts = _collect("""
        function twice(uint x) pure returns (uint) { return x * 2; }
        contract Vault {
            constructor(address owner) {}
            receive() external payable {}
            fallback() external payable {}
        }
    """)
    callables = {
        (a.kind, a.name, a.of): a
        for a in artifacts
        if a.kind in {ArtifactKind.FUNCTION, ArtifactKind.METHOD}
    }
    assert set(callables) == {
        (ArtifactKind.FUNCTION, "twice", None),
        (ArtifactKind.METHOD, "constructor", "Vault"),
        (ArtifactKind.METHOD, "receive", "Vault"),
        (ArtifactKind.METHOD, "fallback", "Vault"),
    }
    assert callables[(ArtifactKind.METHOD, "receive", "Vault")].returns == "void"
    assert callables[(ArtifactKind.METHOD, "receive", "Vault")].args == ()


def test_state_variables_and_nested_struct_fields_keep_types_and_owners():
    artifacts = _collect("""
        contract Vault {
            uint256 public immutable limit;
            mapping(address => uint256) public balances;
            uint private secret;
            struct Position { uint128 shares; address owner; }
            enum Status { Open, Closed }
        }
        type Price is uint128;
    """)
    by_key = {(a.kind, a.name, a.of): a for a in artifacts}
    assert (
        by_key[(ArtifactKind.ATTRIBUTE, "limit", "Vault")].type_annotation == "uint256"
    )
    assert (
        by_key[(ArtifactKind.ATTRIBUTE, "balances", "Vault")].type_annotation
        == "mapping(address => uint256)"
    )
    assert (ArtifactKind.CLASS, "Vault.Position", None) in by_key
    assert (
        by_key[(ArtifactKind.ATTRIBUTE, "shares", "Vault.Position")].type_annotation
        == "uint128"
    )
    assert (ArtifactKind.ENUM, "Vault.Status", None) in by_key
    assert by_key[(ArtifactKind.TYPE, "Price", None)].type_annotation == "uint128"
    assert not any(a.name == "secret" for a in artifacts)


def test_typed_fallback_keeps_return_parameters_out_of_its_inputs():
    artifacts = _collect("""
        contract Vault {
            fallback(bytes calldata input) external returns (bytes memory output) {
                return input;
            }
        }
        """)
    fallback = next(a for a in artifacts if a.name == "fallback")
    assert [(arg.name, arg.type) for arg in fallback.args] == [
        ("input", "bytes calldata")
    ]
    assert fallback.returns == "bytes memory"
    assert fallback.signature == "fallback(bytes)"


def test_events_errors_and_modifiers_do_not_masquerade_as_callable_artifacts():
    artifacts = _collect("""
        contract Vault {
            event Paid(address indexed who, uint amount);
            error Unauthorized();
            modifier guarded() { _; }
            function deposit() external guarded {}
        }
    """)
    assert {a.name for a in artifacts} == {"Vault", "deposit"}


@pytest.mark.parametrize(
    "source", ["", "  \n", "// only a comment\n", "pragma solidity ^0.8.26;"]
)
def test_empty_and_metadata_only_sources_have_no_artifacts(source):
    assert _collect(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "contract {",
        "contract Vault { function pay( }",
        "contract Vault { uint public ; }",
    ],
)
def test_malformed_source_fails_without_partial_artifacts(source):
    from maid_validator_solidity.validator import SolidityValidator

    result = SolidityValidator().collect_implementation_artifacts(source, "Broken.sol")
    assert result.errors
    assert result.artifacts == []


def test_unicode_comments_do_not_corrupt_names_or_locations():
    artifacts = _collect("// เงิน 💰\ncontract Vault { function pay() external {} }")
    method = next(a for a in artifacts if a.name == "pay")
    assert method.of == "Vault" and method.line == 2


def test_private_names_are_excluded_from_snapshots():
    from maid_validator_solidity.validator import SolidityValidator

    validator = SolidityValidator()
    assert validator.generate_snapshot("contract _Hidden {}", "Hidden.sol") == []
    snapshot = validator.generate_snapshot(
        "contract Vault { function deposit(uint n) external {} }", "Vault.sol"
    )
    assert any(a["name"] == "Vault" for a in snapshot)
    method = next(a for a in snapshot if a["name"] == "deposit")
    assert method["signature"] == "deposit(uint256)"


def test_collection_is_deterministic_and_independent_between_calls():
    from maid_validator_solidity.validator import SolidityValidator

    validator = SolidityValidator()
    first = validator.collect_implementation_artifacts("contract Vault {}", "Vault.sol")
    validator.collect_implementation_artifacts("contract Other {}", "Other.sol")
    assert (
        validator.collect_implementation_artifacts("contract Vault {}", "Vault.sol")
        == first
    )


def test_nested_private_names_and_their_fields_are_excluded_from_snapshots():
    from maid_validator_solidity.validator import SolidityValidator

    snapshot = SolidityValidator().generate_snapshot(
        "contract Vault { struct _Hidden { uint amount; } enum _State { Open, Closed } }",
        "Vault.sol",
    )
    assert snapshot == [{"kind": "class", "name": "Vault"}]
