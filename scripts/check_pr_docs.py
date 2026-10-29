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


def changed_files(base: str, head: str, cwd: Path | None = None) -> list[str]:
    base, head = normalize_sha(base), normalize_sha(head)
    output = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            "--end-of-options",
            f"{base}...{head}",
            "--",
        ],
        cwd=cwd,
    )
    return [os.fsdecode(value) for value in output.split(b"\0") if value]


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    files = changed_files(pr["base"]["sha"], pr["head"]["sha"])
    validate(pr.get("body") or "", pr["user"]["login"], files)
    print("Documentation impact declaration matches the change")


if __name__ == "__main__":
    main()
