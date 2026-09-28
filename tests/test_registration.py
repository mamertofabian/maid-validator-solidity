"""Installed package discovery must work through MAID's public registry."""

from importlib.metadata import entry_points

from maid_runner.validators.registry import ValidatorRegistry


def test_distribution_entry_point_loads_the_public_validator():
    from maid_validator_solidity import SolidityValidator

    points = list(entry_points(group="maid_runner.validators", name="solidity"))
    assert len(points) == 1
    assert points[0].load() is SolidityValidator


def test_registry_discovers_solidity_and_retains_builtin_languages(monkeypatch):
    from maid_validator_solidity import SolidityValidator

    monkeypatch.delenv("MAID_DISABLE_VALIDATOR_PLUGINS", raising=False)
    registry = ValidatorRegistry.with_builtin_validators()
    assert isinstance(registry.get("Vault.sol"), SolidityValidator)
    assert registry.has_validator("example.py")
    records = [r for r in registry.validator_records() if ".sol" in r.extensions]
    assert len(records) == 1 and records[0].status == "active"
    assert not registry.plugin_diagnostics()
