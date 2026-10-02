# Changelog

## 0.1.0 — 2026-10-02

Prepared release candidate; publication is pending the release workflow.

- Register `.sol` support through MAID Runner's external validator entry point.
- Collect Solidity declarations with tree-sitter-solidity, including internal
  library methods, nested types, and source overload signatures.
- Collect Foundry test references with lexical receiver bindings and conservative
  unsigned call identities.
- Add type comparison, parser error reporting, public conformance tests, and
  installation documentation with explicit Foundry integration limits.
- Add the C# plugin's Python 3.10–3.14 CI and tag-triggered PyPI Trusted Publisher
  release route, pinned build tools, isolated wheel checks, and operator setup.
