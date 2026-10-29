"""Maintainer-run check of source gate names against live GitHub protection."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def validate(protection: dict, expected: set[str]) -> None:
    checks = protection["required_status_checks"]
    if not checks["strict"] or set(checks["contexts"]) != expected:
        raise ValueError("Required checks differ from .github/required-checks.json")
    if any(check["app_id"] != 15368 for check in checks["checks"]):
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


def main() -> None:
    # Requires the maintainer's existing admin-scoped gh login. Never grant admin
    # credentials to PR CI just to read these settings; no tokens are printed.
    protection = json.loads(
        subprocess.check_output(
            ["gh", "api", "repos/solarssk/ha-linak/branches/main/protection"], text=True
        )
    )
    expected = set(json.loads((ROOT / ".github/required-checks.json").read_text()))
    validate(protection, expected)
    print("Live branch protection matches source and required safety settings")


if __name__ == "__main__":
    main()
