"""MAID Runner's public conformance kit is the plugin acceptance bar."""

import pytest
from maid_runner.core.types import ArtifactKind
from maid_runner.testing.validator_conformance import (
    ConformanceArtifactSample,
    ConformanceFixtures,
    make_conformance_suite,
)

_FIXTURES = ConformanceFixtures(
    extension=".sol",
    artifact_samples={
        ArtifactKind.CLASS.value: ConformanceArtifactSample(
            "contract Vault {}", "Vault"
        ),
        ArtifactKind.FUNCTION.value: ConformanceArtifactSample(
            "function double(uint n) pure returns (uint) { return n * 2; }",
            "double",
        ),
        ArtifactKind.METHOD.value: ConformanceArtifactSample(
            "contract Vault { function deposit() external {} }", "deposit", "Vault"
        ),
        ArtifactKind.ATTRIBUTE.value: ConformanceArtifactSample(
            "contract Vault { uint public total; }", "total", "Vault"
        ),
        ArtifactKind.INTERFACE.value: ConformanceArtifactSample(
            "interface IVault { function deposit() external; }", "IVault"
        ),
        ArtifactKind.ENUM.value: ConformanceArtifactSample(
            "enum Status { Open, Closed }", "Status"
        ),
        ArtifactKind.TYPE.value: ConformanceArtifactSample(
            "type Price is uint128;", "Price"
        ),
    },
    private_artifact_source="contract _Hidden {}",
    behavioral_target_kind="method",
    behavioral_target_name="deposit",
    behavioral_target_of="Vault",
    behavioral_correct_source='import {Vault} from "./Vault.sol"; contract VaultTest { function testDeposit() public { Vault target; target.deposit(); } }',
    behavioral_wrong_identity_source='import {Other} from "./Other.sol"; contract OtherTest { function testDeposit() public { Other target; target.deposit(); } }',
    unparseable_source="contract {",
    empty_source="",
)


def assert_conformance_case(name, *args):
    """Execute the public conformance kit assertions after pytest collection."""
    from maid_validator_solidity import SolidityValidator

    suite = make_conformance_suite(SolidityValidator, _FIXTURES)()
    getattr(suite, name)(*args)


@pytest.mark.parametrize("kind,sample", _FIXTURES.artifact_samples.items())
def test_conformance_collects_declared_implementation_artifact(kind, sample):
    assert_conformance_case(
        "test_collects_declared_implementation_artifact", kind, sample
    )


@pytest.mark.parametrize("kind,sample", _FIXTURES.artifact_samples.items())
def test_conformance_declared_artifact_identity_fields_are_exact(kind, sample):
    assert_conformance_case(
        "test_declared_artifact_identity_fields_are_exact", kind, sample
    )


@pytest.mark.parametrize("kind,sample", _FIXTURES.artifact_samples.items())
def test_conformance_collecting_same_sample_is_deterministic(kind, sample):
    assert_conformance_case(
        "test_collecting_same_sample_is_deterministic", kind, sample
    )


def test_conformance_private_artifacts_stay_out_of_snapshot():
    assert_conformance_case("test_private_artifacts_stay_private_and_out_of_snapshot")


def test_conformance_behavioral_sample_references_declared_target():
    assert_conformance_case("test_behavioral_sample_references_declared_target")


def test_conformance_wrong_identity_does_not_match_target():
    assert_conformance_case(
        "test_wrong_identity_behavioral_sample_does_not_match_target"
    )


def test_conformance_unparseable_source_reports_errors_without_artifacts():
    assert_conformance_case("test_unparseable_source_reports_errors_without_artifacts")


def test_conformance_empty_source_returns_no_artifacts_or_errors():
    assert_conformance_case("test_empty_source_returns_no_artifacts_or_errors")
