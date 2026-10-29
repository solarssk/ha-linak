"""Require a documentation decision without interpolating PR text into a shell."""

import json
import os
from pathlib import Path
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
    section = []
    in_section = False
    for line in body.splitlines():
        if line.strip() == "## Documentation impact":
            in_section = True
        elif in_section and line.startswith("## "):
            break
        elif in_section:
            section.append(line)
    content = "\n".join(section).strip()
    if (
        not content
        or content == "State which docs/translations changed, or why none are affected."
    ):
        raise ValueError("Fill in the Documentation impact section")
    if any(name.startswith("custom_components/") for name in files):
        if "CHANGELOG.md" not in files:
            raise ValueError("Integration changes require a CHANGELOG.md entry")
        if not any(name.startswith(("README", "docs/")) for name in files):
            raise ValueError("Integration changes require documentation updates")


def normalize_sha(value: str) -> str:
    if len(value) != 40:
        raise ValueError("Expected a 40-character Git object ID")
    number = int(value, 16)
    if number < 0:
        raise ValueError("Expected a nonnegative Git object ID")
    return f"{number:040x}"


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    base, head = normalize_sha(pr["base"]["sha"]), normalize_sha(pr["head"]["sha"])
    # Arguments are never interpreted as shell code. SHAs come from GitHub's event.
    files = subprocess.check_output(
        ["git", "diff", "--name-only", "--end-of-options", f"{base}...{head}", "--"],
        text=True,
    ).splitlines()
    validate(pr.get("body") or "", pr["user"]["login"], files)
    print("Documentation impact declaration matches the change")


if __name__ == "__main__":
    main()
