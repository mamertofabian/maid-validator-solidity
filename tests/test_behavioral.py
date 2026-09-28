"""Foundry references must identify evidence without guessing receiver types."""

import pytest
from maid_runner.core.types import ArtifactKind


def _collect(source):
    from maid_validator_solidity import SolidityValidator

    result = SolidityValidator().collect_behavioral_artifacts(
        source, "test/Vault.t.sol"
    )
    assert not result.errors
    assert result.language == "solidity"
    return result.artifacts


def _methods(artifacts):
    return {(a.name, a.of) for a in artifacts if a.kind == ArtifactKind.METHOD}


def test_foundry_tests_fuzz_tests_and_invariants_are_marked():
    artifacts = _collect("""
        contract VaultTest {
            function setUp() public {}
            function testDeposit() public {}
            function testFuzzDeposit(uint amount) public {}
            function invariantSupply() public view {}
            function helper() public {}
            function testInternalHelper() internal {}
        }
    """)
    assert {
        (a.name, a.of) for a in artifacts if a.kind == ArtifactKind.TEST_FUNCTION
    } == {
        ("testDeposit", "VaultTest"),
        ("testFuzzDeposit", "VaultTest"),
        ("invariantSupply", "VaultTest"),
    }


def test_explicit_receiver_types_and_constructor_calls_are_referenced():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            Vault vault;
            function setUp() public { vault = new Vault(); }
            function testDeposit() public { vault.deposit(1); }
        }
    """)
    assert any(
        a.kind == ArtifactKind.CLASS
        and a.name == "Vault"
        and a.reference_context != "import"
        for a in artifacts
    )
    assert ("constructor", "Vault") in _methods(artifacts)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("deposit", "vault") not in _methods(artifacts)
    assert all(a.signature is None for a in artifacts)


def test_library_import_alias_resolves_original_owner():
    artifacts = _collect("""
        import {CurveMath as M} from "../src/CurveMath.sol";
        contract MathTest {
            function testQuote() public { uint quote = M.buy(100, 5); assert(quote > 0); }
        }
    """)
    assert ("buy", "CurveMath") in _methods(artifacts)
    assert ("buy", "M") not in _methods(artifacts)


def test_parameter_and_cast_receivers_resolve_declared_owners():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            function testFuzzDeposit(Vault target, address addr) public {
                target.deposit(1);
                Vault(addr).withdraw(1);
            }
        }
    """)
    assert {("deposit", "Vault"), ("withdraw", "Vault")} <= _methods(artifacts)


def test_same_named_locals_do_not_leak_between_test_methods():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        import {Other} from "../src/Other.sol";
        contract VaultTest {
            function testOne() public { Vault target; target.deposit(1); }
            function testTwo() public { Other target; target.withdraw(1); }
        }
    """)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("withdraw", "Other") in _methods(artifacts)
    assert ("withdraw", "Vault") not in _methods(artifacts)
    assert ("deposit", "Other") not in _methods(artifacts)


def test_nearest_lexical_binding_wins_and_restores_outer_binding():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        import {Other} from "../src/Other.sol";
        contract VaultTest {
            Vault target;
            function testScopes() public {
                { Other target; target.withdraw(1); }
                target.deposit(1);
            }
        }
    """)
    assert ("withdraw", "Other") in _methods(artifacts)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("withdraw", "Vault") not in _methods(artifacts)
    assert ("deposit", "Other") not in _methods(artifacts)


def test_primitive_local_shadows_an_imported_library_alias():
    artifacts = _collect("""
        import {CurveMath as M} from "../src/CurveMath.sol";
        contract MathTest {
            function testAliasShadowing() public {
                uint quote = M.buy(100, 5);
                {
                    address M = address(1);
                    M.call("");
                }
                M.sell(quote, 5);
            }
        }
        """)
    assert ("buy", "CurveMath") in _methods(artifacts)
    assert ("sell", "CurveMath") in _methods(artifacts)
    assert ("call", "CurveMath") not in _methods(artifacts)
    assert ("call", "M") not in _methods(artifacts)


def test_receiver_fields_do_not_leak_between_contracts_in_one_file():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract FirstTest {
            Vault target;
            function testDeposit() public { target.deposit(1); }
        }
        contract SecondTest {
            function testWithdraw() public { target.withdraw(1); }
        }
        """)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("withdraw", "Vault") not in _methods(artifacts)
    assert not any(name == "withdraw" for name, _owner in _methods(artifacts))


def test_try_return_and_catch_parameters_shadow_imports_only_in_their_bodies():
    artifacts = _collect("""
        import {CurveMath as M} from "../src/CurveMath.sol";
        contract MathTest {
            Worker worker;
            function testTryScopes() public {
                try worker.run() returns (address M) { M.call(""); }
                catch (bytes memory M) { uint n = M.length; }
                M.buy(1);
            }
        }
        """)
    assert ("run", "Worker") in _methods(artifacts)
    assert ("buy", "CurveMath") in _methods(artifacts)
    assert ("call", "CurveMath") not in _methods(artifacts)
    assert not any(a.name == "length" and a.of == "CurveMath" for a in artifacts)


def test_try_return_bindings_do_not_leak_into_catch_bodies():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        import {Other} from "../src/Other.sol";
        contract VaultTest {
            Worker worker;
            Other target;
            function testTryScopes() public {
                try worker.run() returns (Vault target) { target.deposit(1); }
                catch { target.withdraw(1); }
            }
        }
        """)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("withdraw", "Other") in _methods(artifacts)
    assert ("deposit", "Other") not in _methods(artifacts)
    assert ("withdraw", "Vault") not in _methods(artifacts)


def test_unknown_receivers_and_uninvoked_helpers_do_not_supply_evidence():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            function helper() public { Vault target; target.withdraw(1); }
            function testNoEvidence() public { unknown.deposit(1); }
        }
    """)
    assert ("withdraw", "Vault") not in _methods(artifacts)
    assert not any(name == "deposit" for name, _owner in _methods(artifacts))


def test_named_returns_bind_receivers_and_shadow_imports_within_the_function():
    artifacts = _collect("""
        import {CurveMath as M} from "../src/CurveMath.sol";
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            function testReturn() public returns (address M, Vault target) {
                M.call("");
                target.deposit(1);
            }
            function testLibrary() public { M.buy(1); }
        }
        """)
    assert ("deposit", "Vault") in _methods(artifacts)
    assert ("buy", "CurveMath") in _methods(artifacts)
    assert ("call", "CurveMath") not in _methods(artifacts)


def test_nested_struct_receivers_match_qualified_declaration_owners():
    artifacts = _collect("""
        contract VaultTest {
            struct Position { uint shares; }
            function testPosition() public {
                Position memory p;
                p.shares = 1;
            }
        }
        contract OtherTest {
            struct Position { uint shares; }
            function testPosition() public {
                Position memory p;
                p.shares = 2;
            }
        }
        """)
    owners = {
        a.of
        for a in artifacts
        if a.kind == ArtifactKind.ATTRIBUTE and a.name == "shares"
    }
    assert owners == {"VaultTest.Position", "OtherTest.Position"}


def test_contract_local_types_shadow_imports_without_leaking_into_other_contracts():
    artifacts = _collect("""
        import {CurveMath as M} from "../src/CurveMath.sol";
        contract MathTest {
            enum M { First, Second }
            function testEnum() public { M choice = M.First; }
        }
        contract OtherTest {
            function testLibrary() public { M.buy(1); }
        }
        """)
    assert any(a.name == "First" and a.of == "MathTest.M" for a in artifacts)
    assert not any(a.name == "First" and a.of == "CurveMath" for a in artifacts)
    assert ("buy", "CurveMath") in _methods(artifacts)


@pytest.mark.parametrize(
    "options", ["", "{salt: bytes32(0)}", "{value: 1, salt: bytes32(0)}"]
)
def test_constructor_expression_receivers_support_call_options(options):
    artifacts = _collect(
        'import {Vault} from "../src/Vault.sol"; '
        "contract VaultTest { function testDeposit() public { "
        f"(new Vault{options}()).deposit(1);"
        " } }"
    )
    assert ("constructor", "Vault") in _methods(artifacts)
    assert ("deposit", "Vault") in _methods(artifacts)


def test_imports_comments_strings_and_type_declarations_are_not_method_evidence():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            function testNothing() public {
                Vault target;
                string memory text = "target.deposit(1)";
                // target.withdraw(1);
            }
        }
    """)
    assert not _methods(artifacts)
    assert not any(
        a.kind == ArtifactKind.CLASS
        and a.name == "Vault"
        and a.reference_context not in {"import", "type"}
        for a in artifacts
    )


def test_behavioral_overloads_remain_unsigned_even_with_literal_arguments():
    artifacts = _collect("""
        import {Vault} from "../src/Vault.sol";
        contract VaultTest {
            function testGet() public { Vault target; target.get(uint256(1)); }
        }
    """)
    calls = [a for a in artifacts if a.name == "get" and a.of == "Vault"]
    assert calls and all(a.signature is None for a in calls)


@pytest.mark.parametrize("source", ["", "// testDeposit()", "pragma solidity ^0.8.26;"])
def test_empty_behavioral_sources_have_no_references(source):
    assert _collect(source) == []


def test_malformed_test_source_returns_errors_without_partial_evidence():
    from maid_validator_solidity import SolidityValidator

    result = SolidityValidator().collect_behavioral_artifacts(
        "contract VaultTest { function testDeposit( {", "test/Vault.t.sol"
    )
    assert result.errors and result.artifacts == []
