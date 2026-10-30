"""Validate PR handoff metadata from a GitHub event or a live PR, read-only."""

import argparse
import json
import os
from pathlib import Path
import subprocess

TYPE_LABELS = {"type: bug", "type: feature", "type: chore", "type: docs"}


def validate(pr: dict) -> None:
    labels = {item["name"] for item in pr.get("labels", [])}
    types = {name for name in labels if name.startswith("type:")}
    if len(types) != 1 or not types <= TYPE_LABELS:
        raise ValueError("Set exactly one supported type: label on the PR")
    milestone = pr.get("milestone")
    if not milestone or milestone.get("state") != "open":
        raise ValueError("Assign the PR to its open target release milestone")
    if not pr.get("assignees"):
        raise ValueError("Assign a maintainer responsible for the PR")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="Read live metadata for this PR number")
    args = parser.parse_args()
    if args.pr is not None:
        if args.pr <= 0:
            parser.error("PR number must be positive")
        pr = json.loads(
            subprocess.check_output(
                ["gh", "api", f"repos/solarssk/ha-linak/pulls/{args.pr}"], text=True
            )
        )
    else:
        pr = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())[
            "pull_request"
        ]
    validate(pr)
    print("PR type, open release milestone and assignee are set")


if __name__ == "__main__":
    main()
