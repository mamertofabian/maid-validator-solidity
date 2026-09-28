"""Public MAID Runner plugin; all collection is source-local and offline."""

from __future__ import annotations

from pathlib import Path

from maid_runner.validators.base import BaseValidator, CollectionResult

from maid_validator_solidity._behavioral import _collect_behavioral
from maid_validator_solidity._implementation import _collect_implementation
from maid_validator_solidity._parse import _parse
from maid_validator_solidity._types import _types_match


class SolidityValidator(BaseValidator):
    """Collect Solidity declarations and Foundry references with tree-sitter."""

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".sol",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        encoded, root, errors = _parse(source)
        artifacts = (
            [] if errors or root is None else _collect_implementation(root, encoded)
        )
        return CollectionResult(artifacts, "solidity", str(file_path), errors)

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        encoded, root, errors = _parse(source)
        artifacts = [] if errors or root is None else _collect_behavioral(root, encoded)
        return CollectionResult(artifacts, "solidity", str(file_path), errors)

    def types_match(
        self,
        manifest_type: str | None,
        implementation_type: str | None,
    ) -> bool:
        return _types_match(manifest_type, implementation_type)
