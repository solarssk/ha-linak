"""Regression checks for dependency ownership, CI gates and documentation policy."""

import json
from pathlib import Path
import re
import yaml
import pytest
from scripts.check_pr_docs import validate

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_owns_pytest_stack_and_generated_pins_are_excluded():
    source = (ROOT / "requirements-dev.txt").read_text()
    assert "pytest-homeassistant-custom-component==" in source
    assert not re.search(
        r"^(homeassistant|pytest|pytest-asyncio|serialx|bleak-retry-connector)==",
        source,
        re.MULTILINE,
    )
    policy = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    pip = next(
        update for update in policy["updates"] if update["package-ecosystem"] == "pip"
    )
    assert ".github/locks/**" in pip["exclude-paths"]
    assert ".github/ha-requirements.txt" in pip["exclude-paths"]
    assert pip["cooldown"]["default-days"] >= 7
    assert any(
        item["dependency-name"] == "pytest-homeassistant-custom-component"
        for item in pip["ignore"]
    )


def test_required_checks_are_real_jobs_and_workflows_are_least_privileged():
    names = set()
    for file in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.safe_load(file.read_text())
        assert "concurrency" in workflow
        assert "permissions" in workflow
        triggers = workflow.get("on", workflow.get(True, {}))
        assert "pull_request_target" not in triggers
        for job in workflow["jobs"].values():
            names.add(job.get("name"))
            for step in job.get("steps", []):
                if "uses" in step:
                    assert re.search(r"@[a-f0-9]{40}$", step["uses"]), step
                    if step["uses"].startswith("actions/checkout@"):
                        assert step["with"]["persist-credentials"] is False
    required = set(json.loads((ROOT / ".github/required-checks.json").read_text()))
    assert required <= names
    assert "Lint workflows (actionlint, zizmor)" in required
    assert "Documentation impact" in required


def test_each_python_install_uses_a_hash_locked_input():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    commands = [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]
    installs = [command for command in commands if "pip install" in command]
    assert len(installs) == 6
    assert all("--require-hashes -r .github/locks/" in command for command in installs)
    assert all("--only-binary :all:" in command for command in installs)
    exceptions = [command for command in installs if "--no-binary" in command]
    assert len(exceptions) == 2
    assert all(
        "--no-binary mock-open,pyric --no-build-isolation" in command
        for command in exceptions
    )
    assert any("update_locks.py --check" in command for command in commands)
    assert any("check_dependencies.py" in command for command in commands)


@pytest.mark.parametrize(
    "body,author,files",
    [
        (
            "## Documentation impact\nUpdated installation docs.",
            "maintainer",
            ["custom_components/ha_linak/client.py", "README.md", "CHANGELOG.md"],
        ),
        ("", "dependabot[bot]", ["requirements-tools.txt"]),
    ],
)
def test_documentation_policy_accepts_reviewable_changes(body, author, files):
    validate(body, author, files)


@pytest.mark.parametrize(
    "body,author,files",
    [
        ("", "maintainer", ["requirements-tools.txt"]),
        (
            "## Documentation impact\nNo changes.",
            "maintainer",
            ["custom_components/ha_linak/client.py"],
        ),
        ("", "dependabot[bot]", ["custom_components/ha_linak/client.py"]),
    ],
)
def test_documentation_policy_rejects_missing_evidence(body, author, files):
    with pytest.raises(ValueError):
        validate(body, author, files)


def test_generated_dependency_files_match_installed_ha_metadata():
    from scripts.check_dependencies import expected_audit, expected_components

    components = expected_components()
    assert (ROOT / ".github/ha-requirements.txt").read_text() == components
    assert (ROOT / ".github/audit-direct.txt").read_text() == expected_audit(components)


def test_installed_component_version_drift_is_rejected(monkeypatch):
    from scripts import check_dependencies as policy
    from packaging.requirements import Requirement

    original = policy.metadata.version
    versions = {
        Requirement(line).name: str(Requirement(line).specifier).removeprefix("==")
        for line in policy.expected_components().splitlines()
        if line and not line.startswith("#")
    }
    versions["serialx"] = "1.15.0"
    monkeypatch.setattr(
        policy.metadata,
        "version",
        lambda name: versions[name] if name in versions else original(name),
    )
    with pytest.raises(ValueError, match="serialx"):
        policy.validate_installed()


@pytest.mark.parametrize(
    "value", ["--output=evil", "0" * 39, "0" * 41, "-" + "1" * 39, "g" * 40]
)
def test_git_revision_parser_rejects_non_object_ids(value):
    from scripts.check_pr_docs import normalize_sha

    with pytest.raises(ValueError):
        normalize_sha(value)


def test_git_revision_parser_normalizes_to_option_free_hex():
    from scripts.check_pr_docs import normalize_sha

    assert normalize_sha("a" * 40) == "a" * 40
    assert normalize_sha("0" * 32 + "DEADBEEF") == "0" * 32 + "deadbeef"


def test_empty_documentation_section_cannot_borrow_next_section():
    with pytest.raises(ValueError):
        validate(
            "## Documentation impact\n\n## Validation\nTests passed.",
            "maintainer",
            ["README.md"],
        )


def test_coverage_uploads_are_isolated_and_advisory():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["coverage-signals"]
    assert job["needs"] == "tests"
    assert "dependabot[bot]" in job["if"]
    assert "head.repo.full_name == github.repository" in job["if"]
    required = json.loads((ROOT / ".github/required-checks.json").read_text())
    assert job["name"] not in required
    for name, value in workflow["jobs"].items():
        if name != "coverage-signals":
            assert "secrets." not in str(value)
    uploads = [step for step in job["steps"] if "secrets." in str(step)]
    assert len(uploads) == 3
    assert all("!= ''" in step["if"] for step in uploads)


def test_sonar_classifies_shipped_code_and_tests_and_accepts_relative_reports():
    properties = (ROOT / "sonar-project.properties").read_text()
    assert "sonar.sources=custom_components/ha_linak" in properties
    assert "sonar.tests=tests" in properties
    assert "sonar.python.coverage.reportPaths=coverage.xml" in properties
    assert "sonar.organization=recmedia" in properties
    assert "relative_files = true" in (ROOT / "pyproject.toml").read_text()
