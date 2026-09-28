# maid-validator-solidity

Solidity (`.sol`) language validator for MAID Runner, backed by
[`tree-sitter-solidity`](https://github.com/JoranHonig/tree-sitter-solidity).
This separate Python package uses the same `maid_runner.validators` entry-point
mechanism as `maid-validator-csharp`. Version 0.1.0 is local and not published.

Collection reads supplied source without invoking a compiler, downloading
dependencies, or reading generated build artifacts. Tests can therefore refer to
contracts and methods that have not been implemented yet.

## Install locally

Install the plugin in the **same Python environment** as the MAID executable.
For a project managed with uv:

```sh
uv add --dev /path/to/maid-validator-solidity
uv run maid validators
```

For an isolated MAID tool installation:

```sh
uv tool install --with /path/to/maid-validator-solidity 'maid-runner>=2.24,<3'
maid validators
```

The registry lists `SolidityValidator`, extension `.sol`, and status `active`.
Development within this directory uses `uv sync` and `uv run maid validators`.

## Supported declarations

| Solidity construct | MAID artifact |
| --- | --- |
| Contract, abstract contract, library | `class`, including declared bases |
| Interface | `interface` |
| Struct | `class`, with `attribute` fields |
| Enum | `enum` |
| User-defined value type | `type`, with its underlying primitive type |
| Public state variable | `attribute`, with its declared type |
| Public/external contract function | `method` |
| Non-private library function, including internal functions | `method` |
| Constructor, receive, fallback | `method`, named `constructor`, `receive`, `fallback` |
| Free function | `function` |

Nested types use names such as `Vault.Position`; their fields have
`of: Vault.Position`. Callable artifacts retain argument names, raw types and
data locations. Return types are `void`, a single declared type, or a parenthesized
list such as `(uint256, address)`.

Definition signatures such as `deposit(uint256,bytes)` normalize `uint`, `int`,
and `byte`, and omit data locations. They distinguish source overload definitions;
they are not ABI selectors or compiler-resolved identities. Type comparison
normalizes these aliases and whitespace, but preserves widths, array dimensions,
custom names, data locations, and `address payable`.

## Foundry reference collection

The behavioral collector recognizes public/external `test*` and `invariant*`
methods, including `testFuzz*`. It also reads `setUp` and state initializers when
the same contract declares tests. It collects constructor uses, named import
aliases, direct library calls, and method calls on explicitly typed receivers.
Bindings are isolated by contract, method, and lexical block, including primitive
variables that shadow imported names. Imports alone, comments, string literals,
and uninvoked helper bodies do not establish method coverage.

Behavioral references deliberately have no overload signature. A manifest asking
for exact overload coverage will need compiler evidence that this version does
not provide. Use representative callable declarations (omit `signature`) when
appropriate; snapshots include definition signatures, so review them before using
them as behavioral contracts.

Malformed syntax returns a `CollectionResult` with errors and no artifacts.
The parser does not establish semantic validity or prove runtime execution;
continue running Foundry and security checks such as Slither.

## Limits and Runner integration

MAID Runner 2.27.6 recognizes neither Foundry's `*.t.sol` filenames as behavioral
test files nor `forge test` as a supported test runner. This package supplies
language collection, snapshots, and plugin discovery. Full Foundry manifest
validation needs separate Runner integration; installing the plugin alone does
not remove that prerequisite.

Version 0.1 does not model event, custom-error, or modifier artifacts. It does not
resolve inherited fields from other files, `using for` bindings, generated getter
calls back to state-variable artifacts, namespace/wildcard imports, array-element
receivers, arbitrary helper call graphs, or Hardhat JavaScript test bindings.
Same-file free-function calls are not yet collected as behavioral references.
Unresolved uses can consequently leave a manifest artifact without behavioral
coverage. Cross-file names and imports have source-local identity only; no compiler
or whole-project import resolver is used.

## Development

```sh
uv sync
uv run python -m pytest tests/ -q
uv run ruff check src/ tests/
uv run black --check src/ tests/
uv run maid validate
uv run maid test
uv build
```

The tests include MAID Runner's public conformance kit. The active implementation
contract is [solidity-validator-plugin.manifest.yaml](manifests/solidity-validator-plugin.manifest.yaml).
Changes follow MAID's plan, red evidence, lock, implementation, review, and Outcome
workflow. Commits and publishing require explicit approval.

## Repository MAID tooling

Repo-local Claude and Codex skills, guidance, and hooks are installed. Use
`uv run maid init --check` to check the installed payload. For each coding task,
run `uv run maid assess --since <baseline>` and the verify command it recommends.
Git and Claude hooks invoke `scripts/maid`, which runs `uv run --locked maid`
from the repository root so the Solidity plugin is available without manual
environment activation. The pre-commit configuration runs MAID's pre-commit
profile; this machine's existing Git hook dispatcher already invokes it. On a
fresh machine, install pre-commit (for example, `uv tool install pre-commit`) and
run `pre-commit install` when no existing dispatcher is configured.
