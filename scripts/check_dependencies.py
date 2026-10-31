"""Keep component/audit pins derived from the installed Home Assistant test stack."""

import argparse
from importlib import metadata
import json
from pathlib import Path
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def expected_components() -> str:
    version = metadata.version("homeassistant")
    distribution = metadata.distribution("homeassistant")
    components = Path(distribution.locate_file("homeassistant/components"))
    requirements = []
    for component in ("bluetooth", "usb"):
        requirements.extend(
            json.loads((components / component / "manifest.json").read_text())[
                "requirements"
            ]
        )
    return (
        f"# Generated from Home Assistant {version} bluetooth/usb manifests.\n"
        "# Run python scripts/check_dependencies.py --update after upgrading the HA test plugin.\n"
        + "\n".join(sorted(requirements, key=str.lower))
        + "\n"
    )


def expected_audit(component_text: str) -> str:
    # HA controls these versions. Gate direct integration imports,
    # plus independently maintained tools; full HA transitive auditing is not claimed.
    direct = [
        line
        for line in component_text.splitlines()
        if line.startswith(
            ("bleak-retry-connector==", "bluetooth-data-tools==", "dbus-fast==")
        )
    ]
    return (
        "# Generated direct dependency audit scope; not the complete HA dependency graph.\n-r ../requirements-tools.txt\n-r requirements-locker.txt\n"
        + "\n".join(direct)
        + "\n"
    )


def require_installed(requirements: list[str], scope: str) -> None:
    for value in requirements:
        req = Requirement(value)
        if metadata.version(req.name) not in req.specifier:
            raise ValueError(f"Installed {req.name} differs from {scope}")


def validate_installed() -> None:
    plugin_requirements = [
        value
        for value in metadata.requires("pytest-homeassistant-custom-component") or []
        if Requirement(value).name in {"homeassistant", "pytest", "pytest-asyncio"}
    ]
    require_installed(plugin_requirements, "the HA test plugin")
    components = [
        value
        for value in expected_components().splitlines()
        if value and not value.startswith("#")
    ]
    require_installed(components, "the HA component manifest")
    minimum = json.loads((ROOT / "hacs.json").read_text())["homeassistant"]
    if metadata.version("homeassistant") != minimum:
        raise ValueError(
            "The tested HA version and HACS minimum must be upgraded together"
        )
    manifest = json.loads(
        (ROOT / "custom_components/ha_linak/manifest.json").read_text()
    )
    require_installed(manifest["requirements"], "the integration manifest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip installed platform-package checks when generating on macOS",
    )
    args = parser.parse_args()
    components = expected_components()
    expected = {
        ".github/ha-requirements.txt": components,
        ".github/audit-direct.txt": expected_audit(components),
    }
    for name, content in expected.items():
        path = ROOT / name
        if args.update:
            path.write_text(content)
        elif not path.exists() or path.read_text() != content:
            raise ValueError(f"{name} is stale; run check_dependencies.py --update")
    if not args.metadata_only:
        validate_installed()
    if args.metadata_only:
        print("Generated dependency files match; installed platform checks skipped")
    else:
        print("HA component pins, test stack, minimum version and audit scope match")


if __name__ == "__main__":
    main()
