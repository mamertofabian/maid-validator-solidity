"""Release contract shared with the C# plugin's GitHub/OIDC route."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 matrix
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )


def _build_step(name: str) -> dict:
    return next(
        s
        for s in _workflow("publish.yml")["jobs"]["build"]["steps"]
        if s.get("name") == name
    )


def _python_script(step: dict) -> str:
    return step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


def test_package_metadata_uses_replicable_published_dependencies() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = config["project"]
    assert project["name"] == "maid-validator-solidity"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.10"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert "maid-runner>=2.24,<3" in project["dependencies"]
    assert "tree-sitter>=0.25,<0.26" in project["dependencies"]
    assert "sources" not in config.get("tool", {}).get("uv", {})
    assert config["build-system"]["requires"] == [
        "setuptools==83.0.0",
        "wheel==0.47.0",
    ]
    assert project["entry-points"]["maid_runner.validators"] == {
        "solidity": "maid_validator_solidity:SolidityValidator"
    }
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        assert f"Programming Language :: Python :: {version}" in project["classifiers"]
    base = "https://github.com/mamertofabian/maid-validator-solidity"
    assert project["urls"]["Repository"] == base
    assert project["urls"]["Issues"] == base + "/issues"
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    runner = next(p for p in lock["package"] if p["name"] == "maid-runner")
    assert runner["source"] == {"registry": "https://pypi.org/simple"}


def test_ci_and_release_test_every_supported_python_with_locked_gates() -> None:
    for name in ("ci.yml", "publish.yml"):
        workflow = _workflow(name)
        job = workflow["jobs"]["test"]
        assert job["strategy"]["matrix"]["python-version"] == [
            "3.10",
            "3.11",
            "3.12",
            "3.13",
            "3.14",
        ]
        scripts = "\n".join(step.get("run", "") for step in job["steps"])
        for command in (
            "uv sync --locked",
            "uv run pytest -q",
            "uv run ruff check src/ tests/",
            "uv run black --check src/ tests/",
            "uv run maid validate",
            "uv run maid test",
        ):
            assert command in scripts
        assert workflow["permissions"] == {"contents": "read"}
        for current in workflow["jobs"].values():
            for step in current["steps"]:
                if "uses" in step:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
                if step.get("uses", "").startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] == "false"


def test_publish_orders_verified_artifacts_before_oidc_and_github_release() -> None:
    workflow = _workflow("publish.yml")
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    jobs = workflow["jobs"]
    assert jobs["build"]["needs"] == "test"
    assert jobs["publish"]["needs"] == "build"
    assert jobs["github-release"]["needs"] == "publish"
    assert jobs["publish"]["permissions"] == {"id-token": "write"}
    assert jobs["publish"]["environment"]["name"] == "pypi"
    assert jobs["publish"]["environment"]["url"] == (
        "https://pypi.org/p/maid-validator-solidity"
    )
    assert any(
        s.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
        for s in jobs["publish"]["steps"]
    )
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    steps = jobs["build"]["steps"]
    scripts = "\n".join(s.get("run", "") for s in steps)
    for evidence in (
        "merge-base --is-ancestor",
        "origin/main",
        "uv build",
        "twine==7.0.0",
        "twine check",
        "uv venv",
        "uv pip install",
        "maid validators --json",
        "SolidityValidator",
        '".sol"',
        '"active"',
        "maid-validator-solidity ",
    ):
        assert evidence in scripts
    assert "CSharpValidator" not in scripts
    assert "cancel-in-progress" in workflow["concurrency"]
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    text = (ROOT / ".github/workflows/publish.yml").read_text()
    assert "TWINE_PASSWORD" not in text
    assert "PYPI_API_TOKEN" not in text
    assert "[tool.uv.sources]" in text
    assert (
        _build_step("Build wheel and source distribution")["run"].strip() == "uv build"
    )
    assert _build_step("Check distribution metadata")["run"].strip() == (
        "uvx --from twine==7.0.0 twine check dist/*"
    )
    smoke = _build_step("Verify installed wheel and validator discovery")["run"]
    assert "uv pip install --python .release-smoke/bin/python dist/*.whl" in smoke
    assert (
        ".release-smoke/bin/maid validators --json > .release-smoke/validators.json"
        in smoke
    )
    assert ".release-smoke/bin/python - <<'PY'" in smoke
    upload = next(
        s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"] == {
        "name": "python-package-distributions",
        "path": "dist/",
        "if-no-files-found": "error",
    }
    for job in ("publish", "github-release"):
        download = next(
            s
            for s in jobs[job]["steps"]
            if s.get("uses", "").startswith("actions/download-artifact@")
        )
        assert download["with"] == {
            "name": "python-package-distributions",
            "path": "dist/",
        }


@pytest.mark.parametrize("tag, accepted", [("v0.1.0", True), ("v9.9.9", False)])
def test_publish_version_guard_accepts_only_matching_tag(
    tag: str, accepted: bool
) -> None:
    step = _build_step("Verify tag matches project.version")
    assert step["env"] == {"RELEASE_TAG": "${{ github.ref_name }}"}
    script = _python_script(step)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "RELEASE_TAG": tag},
        check=False,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is accepted
    if not accepted:
        assert "does not match project.version" in result.stderr


@pytest.mark.parametrize("on_main", [True, False])
def test_publish_ancestry_guard_rejects_unmerged_history(
    tmp_path: Path, on_main: bool
) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Release fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.test",
        "GIT_COMMITTER_NAME": "Release fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.test",
    }

    def git(*args: str, input: str | None = None) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            env=env,
            input=input,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--initial-branch=main")
    tree = git("mktree", input="")
    base = git("commit-tree", tree, input="base\n")
    main = git("commit-tree", tree, "-p", base, input="main\n")
    sibling = git("commit-tree", tree, "-p", base, input="unmerged\n")
    git("update-ref", "refs/heads/main", main)
    git("remote", "add", "origin", str(tmp_path))
    result = subprocess.run(
        ["bash", "-e", "-c", _build_step("Verify tagged commit is on main")["run"]],
        cwd=tmp_path,
        env={**env, "GITHUB_SHA": base if on_main else sibling},
        check=False,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is on_main


@pytest.mark.parametrize(
    "state", ["active", "inactive", "missing", "wrong-extension", "wrong-name"]
)
def test_installed_wheel_guard_rejects_missing_or_broken_plugin(
    tmp_path: Path, state: str
) -> None:
    import json

    row = {
        "name": "SolidityValidator",
        "extensions": [".sol"],
        "source": "maid-validator-solidity 0.1.0",
        "status": "active",
    }
    if state == "inactive":
        row["status"] = "inactive"
    if state == "wrong-extension":
        row["extensions"] = [".cs"]
    if state == "wrong-name":
        row["name"] = "CSharpValidator"
    smoke = tmp_path / ".release-smoke"
    smoke.mkdir()
    (smoke / "validators.json").write_text(
        json.dumps({"validators": [] if state == "missing" else [row]})
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _python_script(
                _build_step("Verify installed wheel and validator discovery")
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is (state == "active")


def test_operator_docs_have_exact_solidity_setup_and_foundry_prerequisites() -> None:
    releasing = (ROOT / "RELEASING.md").read_text()
    for value in (
        "PyPI Trusted Publisher",
        "maid-validator-solidity",
        "mamertofabian",
        "publish.yml",
        "pypi",
        "v0.1.0",
        "uv run pytest -q",
        "twine check",
        "2.24",
        "2.27.7",
        "not yet published",
    ):
        assert value in releasing
    assert "maid-validator-csharp" in releasing
    for label, value in (
        ("PyPI project name", "maid-validator-solidity"),
        ("GitHub owner", "mamertofabian"),
        ("GitHub repository", "maid-validator-solidity"),
        ("Workflow filename", "publish.yml"),
        ("Environment name", "pypi"),
    ):
        assert f"- {label}: `{value}`" in releasing
    assert "0.1.0 is published on PyPI and GitHub." in releasing
    readme = (ROOT / "README.md").read_text()
    assert "prepared release candidate" not in readme
    assert "publication is pending" not in readme.lower()
    assert "RELEASING.md" in readme
    assert "CHANGELOG.md" in readme
    assert "2.27.7" in readme
    assert "## 0.1.0 — 2026-10-02" in (ROOT / "CHANGELOG.md").read_text()
