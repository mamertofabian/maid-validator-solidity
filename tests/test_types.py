"""Solidity comparison normalizes only language-defined aliases."""

import pytest


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("uint", "uint256"),
        ("int", "int256"),
        ("byte", "bytes1"),
        ("uint[]", "uint256[]"),
        ("mapping(address => uint)", "mapping(address=>uint256)"),
        ("uint calldata", "uint256 calldata"),
        ("(uint, address)", "(uint256,address)"),
    ],
)
def test_equivalent_solidity_types_match_symmetrically(left, right):
    from maid_validator_solidity import SolidityValidator

    validator = SolidityValidator()
    assert validator.types_match(left, right)
    assert validator.types_match(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("uint128", "uint256"),
        ("uint256", "int256"),
        ("address", "address payable"),
        ("bytes", "bytes32"),
        ("uint[2]", "uint[3]"),
        ("uint[]", "uint[2]"),
        ("bytes memory", "bytes calldata"),
        ("TokenA", "TokenB"),
        ("A.Position", "B.Position"),
        ("uintValue", "uint256Value"),
    ],
)
def test_distinct_solidity_types_do_not_match(left, right):
    from maid_validator_solidity import SolidityValidator

    assert not SolidityValidator().types_match(left, right)
