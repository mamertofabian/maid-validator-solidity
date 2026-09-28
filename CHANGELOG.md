# Changelog

## 0.1.0 — Unreleased

- Register `.sol` support through MAID Runner's external validator entry point.
- Collect Solidity declarations with tree-sitter-solidity, including internal
  library methods, nested types, and source overload signatures.
- Collect Foundry test references with lexical receiver bindings and conservative
  unsigned call identities.
- Add type comparison, parser error reporting, public conformance tests, and
  installation documentation with explicit Foundry integration limits.
