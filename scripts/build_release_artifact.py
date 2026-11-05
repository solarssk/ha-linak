"""Build a reproducible Home Assistant integration archive for a release."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATH = Path("custom_components/ha_linak")
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
TAG_PATTERN = re.compile(r"v(?P<version>\d+\.\d+\.\d+)")
SKIPPED_NAMES = {"__pycache__", ".DS_Store"}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}


def _commit_timestamp(root: Path) -> int:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def _zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    timestamp = max(epoch, 315532800)
    date = datetime.fromtimestamp(timestamp, timezone.utc)
    return (date.year, date.month, date.day, date.hour, date.minute, date.second & ~1)


def _component_files(component: Path) -> list[Path]:
    files = []
    for path in sorted(component.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Integration package contains a symlink: {path}")
        if not path.is_file():
            continue
        if any(part in SKIPPED_NAMES for part in path.relative_to(component).parts):
            continue
        if path.suffix in SKIPPED_SUFFIXES:
            continue
        files.append(path)
    if not files:
        raise ValueError("Integration package is empty")
    return files


def build_release_artifact(
    output_dir: Path,
    *,
    root: Path = ROOT,
    tag: str | None = None,
    source_date_epoch: int | None = None,
) -> tuple[Path, Path]:
    component = root / COMPONENT_PATH
    manifest = json.loads((component / "manifest.json").read_text())
    version = manifest.get("version")
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("Integration manifest must contain a stable x.y.z version")
    changelog = (root / "CHANGELOG.md").read_text()
    if re.search(rf"^## {re.escape(version)}$", changelog, re.MULTILINE) is None:
        raise ValueError(
            f"CHANGELOG.md has no section for integration version {version}"
        )
    if tag is not None:
        match = TAG_PATTERN.fullmatch(tag)
        if match is None or match.group("version") != version:
            raise ValueError(f"Release tag {tag!r} does not match version {version}")

    timestamp = (
        source_date_epoch if source_date_epoch is not None else _commit_timestamp(root)
    )
    date_time = _zip_timestamp(timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / "ha_linak.zip"
    checksum_path = output_dir / "ha_linak.zip.sha256"
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in _component_files(component):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{digest}  {archive_path.name}\n")
    return archive_path, checksum_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag")
    args = parser.parse_args()
    archive, checksum = build_release_artifact(
        args.output_dir,
        tag=args.tag,
    )
    print(f"Built {archive} and {checksum}")


if __name__ == "__main__":
    main()
