"""Require a documentation decision without interpolating PR text into a shell."""

import json
import os
from pathlib import Path
import re
import subprocess


def validate(body: str, author: str, files: list[str]) -> None:
    dependency_paths = (
        "requirements-",
        ".github/locks/",
        ".github/workflows/",
        ".github/requirements-",
        ".github/ha-requirements",
        ".github/audit-direct",
    )
    if (
        author == "dependabot[bot]"
        and files
        and all(name.startswith(dependency_paths) for name in files)
    ):
        return
    section = re.search(
        r"^## Documentation impact\s*\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL
    )
    if (
        not section
        or not section[1].strip()
        or section[1].strip()
        == "State which docs/translations changed, or why none are affected."
    ):
        raise ValueError("Fill in the Documentation impact section")
    if any(name.startswith("custom_components/") for name in files):
        if "CHANGELOG.md" not in files:
            raise ValueError("Integration changes require a CHANGELOG.md entry")
        if not any(name.startswith(("README", "docs/")) for name in files):
            raise ValueError("Integration changes require documentation updates")


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    # Arguments are never interpreted as shell code. SHAs come from GitHub's event.
    files = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...{head}", "--"], text=True
    ).splitlines()
    validate(pr.get("body") or "", pr["user"]["login"], files)
    print("Documentation impact declaration matches the change")


if __name__ == "__main__":
    main()
