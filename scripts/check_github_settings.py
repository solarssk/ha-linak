"""Maintainer-run check of source gates against live GitHub protection."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "solarssk/ha-linak"
RULESET_PATH = ROOT / ".github/rulesets/main.json"


def validate(protection: dict, expected: set[str]) -> None:
    checks = protection["required_status_checks"]
    if not checks["strict"] or set(checks["contexts"]) != expected:
        raise ValueError("Required checks differ from .github/required-checks.json")
    if {
        check["context"]: check["app_id"] for check in checks["checks"]
    } != dict.fromkeys(expected, 15368):
        raise ValueError("Required checks must be bound to GitHub Actions")
    for name in (
        "required_signatures",
        "enforce_admins",
        "required_linear_history",
        "required_conversation_resolution",
    ):
        if not protection[name]["enabled"]:
            raise ValueError(f"Missing branch protection: {name}")
    for name in ("allow_force_pushes", "allow_deletions"):
        if protection[name]["enabled"]:
            raise ValueError(f"Unsafe branch protection: {name}")
    reviews = protection.get("required_pull_request_reviews")
    if reviews is None:
        raise ValueError("Classic protection must require pull requests")
    if (
        reviews["required_approving_review_count"] != 0
        or not reviews["dismiss_stale_reviews"]
        or reviews["require_code_owner_reviews"]
        or reviews["require_last_push_approval"]
    ):
        raise ValueError("Classic pull request policy differs from repository policy")


def validate_ruleset(
    ruleset: dict, effective_rules: list[dict], expected: set[str], source: dict
) -> None:
    if ruleset["enforcement"] != "active" or ruleset["target"] != "branch":
        raise ValueError("Main branch ruleset must be active and target branches")
    if (
        ruleset.get("source_type") != "Repository"
        or ruleset.get("source") != REPOSITORY
    ):
        raise ValueError("Main branch ruleset must belong to this repository")
    if ruleset["conditions"] != source["conditions"]:
        raise ValueError("Main branch ruleset does not target only the default branch")
    if ruleset.get("bypass_actors") != []:
        raise ValueError("Main branch ruleset must not allow bypass actors")

    source_rules = {rule["type"]: rule for rule in source["rules"]}
    live_rules = {rule["type"]: rule for rule in ruleset["rules"]}
    if len(live_rules) != len(ruleset["rules"]):
        raise ValueError("Main branch ruleset contains duplicate rule types")
    expected_types = set(source_rules)
    if set(live_rules) != expected_types:
        raise ValueError("Ruleset rule types differ from its source configuration")

    for rule_type in expected_types - {
        "pull_request",
        "required_status_checks",
    }:
        if live_rules[rule_type] != source_rules[rule_type]:
            raise ValueError(f"Ruleset rule differs from source: {rule_type}")

    status_parameters = live_rules["required_status_checks"]["parameters"]
    statuses = {
        (status["context"], status["integration_id"])
        for status in status_parameters["required_status_checks"]
    }
    if statuses != {(context, 15368) for context in expected}:
        raise ValueError("Ruleset checks differ from .github/required-checks.json")
    if status_parameters["strict_required_status_checks_policy"] is not True:
        raise ValueError("Ruleset status checks must require an up-to-date branch")
    if status_parameters.get("do_not_enforce_on_create", False):
        raise ValueError("Ruleset checks must apply when the default branch is created")

    review_parameters = live_rules["pull_request"]["parameters"]
    expected_reviews = source_rules["pull_request"]["parameters"]
    if any(
        review_parameters.get(key) != value for key, value in expected_reviews.items()
    ):
        raise ValueError("Ruleset pull request policy differs from its source")
    if review_parameters.get("required_reviewers"):
        raise ValueError("Ruleset must not require designated reviewers")

    own_effective_rules = [
        rule
        for rule in effective_rules
        if rule.get("ruleset_id") == ruleset["id"]
        and rule.get("ruleset_source") == REPOSITORY
    ]
    own_types = {rule["type"] for rule in own_effective_rules}
    if own_types != expected_types:
        raise ValueError("The configured ruleset is not fully effective on main")

    effective_by_type: dict[str, list[dict]] = {}
    for rule in effective_rules:
        effective_by_type.setdefault(rule["type"], []).append(rule)
    missing = expected_types - effective_by_type.keys()
    if missing:
        raise ValueError(
            "Active rules do not apply to main: " + ", ".join(sorted(missing))
        )

    effective_statuses = {
        (status["context"], status.get("integration_id"))
        for rule in effective_by_type["required_status_checks"]
        for status in rule.get("parameters", {}).get("required_status_checks", [])
    }
    if not {(context, 15368) for context in expected} <= effective_statuses:
        raise ValueError("Effective main rules do not include every required check")
    if not any(
        rule.get("parameters", {}).get("strict_required_status_checks_policy") is True
        for rule in effective_by_type["required_status_checks"]
    ):
        raise ValueError("Effective main rules do not require up-to-date checks")
    effective_reviews = effective_by_type["pull_request"]
    if not any(
        rule.get("parameters", {}).get("required_approving_review_count") == 0
        and rule.get("parameters", {}).get("dismiss_stale_reviews_on_push") is True
        and rule.get("parameters", {}).get("required_review_thread_resolution") is True
        for rule in effective_reviews
    ):
        raise ValueError("Effective main rules do not preserve the pull request policy")


def _gh_json(endpoint: str) -> dict | list:
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def main() -> None:
    # Requires the maintainer's existing gh login. Never grant admin credentials to
    # PR CI just to read these settings; no tokens are printed.
    expected = set(json.loads((ROOT / ".github/required-checks.json").read_text()))
    source = json.loads(RULESET_PATH.read_text())
    rulesets = _gh_json(f"repos/{REPOSITORY}/rulesets?includes_parents=true")
    ruleset = next((item for item in rulesets if item["name"] == source["name"]), None)
    if ruleset is None:
        protection = _gh_json(f"repos/{REPOSITORY}/branches/main/protection")
        validate(protection, expected)
        print(
            "Live classic branch protection matches source and required safety settings"
        )
        return

    details = _gh_json(f"repos/{REPOSITORY}/rulesets/{ruleset['id']}")
    effective_rules = _gh_json(f"repos/{REPOSITORY}/rules/branches/main")
    validate_ruleset(details, effective_rules, expected, source)
    print(
        "Live main ruleset and effective rules match source and required safety settings"
    )


if __name__ == "__main__":
    main()
