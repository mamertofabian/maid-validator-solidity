# Releasing

This uses the same layout and release route as `maid-validator-csharp`:
`.github/workflows/ci.yml`, `.github/workflows/publish.yml`, pinned build tools,
and PyPI Trusted Publisher authentication. Do not add a PyPI API token to
repository secrets.

0.1.0 is a prepared release candidate, not yet published.

## One-time setup

Create the public GitHub repository and connect this checkout to
`https://github.com/mamertofabian/maid-validator-solidity`. Create the `pypi`
GitHub environment and restrict deployment branches to release tags (`v*`).
Apply the desired environment approval rules before the first release.

In the PyPI account's Publishing settings, add a pending publisher with:

- PyPI project name: `maid-validator-solidity`
- GitHub owner: `mamertofabian`
- GitHub repository: `maid-validator-solidity`
- Workflow filename: `publish.yml`
- Environment name: `pypi`

The first successful OIDC publication creates the PyPI project. For another
validator, change the package/repository name, entry-point key, validator class,
extension, grammar dependency, metadata URLs, smoke assertions, and these
publisher values. Keep the job names, file layout, permissions, and gates.

## Runner prerequisite

MAID Runner 2.24 is the plugin API floor for type comparison and callable
signatures. The package and locked development environment resolve published
Runner dependencies only; never tag with a local `[tool.uv.sources]` override.

Full Foundry validation additionally needs Runner 2.27.7: `.sol` discovery,
`*.t.sol` behavioral classification, and `forge test` support. The local 2.27.7
checkout was verified with `snider-launch`, but 2.27.7 is not yet published.
Release the plugin independently for collection/discovery if desired; to offer
a fully index-installable Foundry workflow, publish Runner 2.27.7 first.

## Release checklist

1. Start from clean, synchronized `main`. Confirm the version is absent on
   PyPI and its `v<version>` tag does not exist locally or remotely.
2. Set `project.version`, date the matching CHANGELOG.md entry, and refresh
   candidate status in README.md and this document after actual publication.
3. Keep dependencies index-only and validate the locked resolution:

   ```sh
   uv lock --check
   uv sync --locked
   uv run pytest -q
   uv run ruff check src/ tests/
   uv run black --check src/ tests/
   uv run maid validate
   uv run maid test
   uv run maid assess --since <baseline>
   # Run the exact verify command recommended by assess.
   ```

4. Build into a fresh temporary output directory, require one wheel and one
   sdist, and check/install the actual distributions:

   ```sh
   release_dir=$(mktemp -d)
   uv build --out-dir "$release_dir"
   uvx --from twine==7.0.0 twine check "$release_dir"/*
   uv venv --python 3.10 "$release_dir/smoke"
   uv pip install --python "$release_dir/smoke/bin/python" "$release_dir"/*.whl
   "$release_dir/smoke/bin/maid" validators --json
   ```

   Require active `SolidityValidator`, extension `.sol`, source
   `maid-validator-solidity <version>`. Test the wheel without development
   dependencies, including Python 3.10's conditional `tomli` dependency.
5. Complete MAID implementation review and capture Outcome. Obtain explicit
   approval for the release commit, then separate approval to push `main`.
   Wait for branch CI to pass before tagging.
6. Recheck tag/version/main and the Trusted Publisher/environment settings.
   Obtain separate explicit approval to create and push the annotated tag:

   ```sh
   git tag -a v0.1.0 -m "Release maid-validator-solidity 0.1.0"
   git push origin v0.1.0
   ```

The tag workflow tests Python 3.10–3.14, rejects development source overrides,
checks main ancestry and tag/version equality, builds/checks distributions,
installs the wheel in isolation, publishes through the `pypi` environment with
short-lived OIDC credentials, and attaches the same files to a GitHub Release.
Only the publish job has `id-token: write`; only the release job has
`contents: write`. Action references are pinned to commit SHAs.

## Post-release verification

Verify both PyPI and GitHub show the intended version and assets. Install from
the public index in a fresh environment:

```sh
uvx --from maid-validator-solidity maid validators --json
```

Require active `SolidityValidator` and `.sol`. Compare PyPI and GitHub artifact
hashes, confirm the tag is on remote `main`, and update candidate status only
after publication succeeds. If PyPI accepted a version but a later step failed,
complete only the missing step; never move the tag or retry an immutable version
blindly. A pending publisher and successful local build are preparation, not
publication.
