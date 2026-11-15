"""Release archives contain only the installable integration and are reproducible."""

import json
from pathlib import Path
import zipfile

import pytest

from scripts.build_release_artifact import build_release_artifact


def _package_root(root: Path, version: str = "0.1.0") -> None:
    component = root / "custom_components/ha_linak"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text(json.dumps({"version": version}) + "\n")
    (component / "protocol.py").write_text("value = 1\n")
    (component / "__pycache__").mkdir()
    (component / "__pycache__/ignored.pyc").write_bytes(b"compiled")
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## {version}\n")
    (root / "README.md").write_text("not part of the integration archive\n")


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0-beta.1", "0.2.0-rc.1"])
def test_release_archive_is_reproducible_and_contains_installable_paths(
    tmp_path, version
):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root, version)
    first, first_checksum = build_release_artifact(
        tmp_path / "first",
        root=root,
        tag=f"v{version}",
        source_date_epoch=1_767_000_000,
    )
    second, _ = build_release_artifact(
        tmp_path / "second",
        root=root,
        tag=f"v{version}",
        source_date_epoch=1_767_000_000,
    )

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == [
            "custom_components/ha_linak/manifest.json",
            "custom_components/ha_linak/protocol.py",
        ]
    assert first_checksum.read_text().endswith("  ha_linak.zip\n")


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("0.1.0", "v0.2.0"),
        ("0.2.0-beta.1", "v0.2.0"),
        ("0.2.0-beta.1", "v0.2.0-beta.2"),
        ("0.2.0-rc.1", "v0.2.0-beta.1"),
    ],
)
def test_release_archive_rejects_a_tag_for_a_different_version(tmp_path, version, tag):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root, version)

    with pytest.raises(ValueError, match="does not match version"):
        build_release_artifact(
            tmp_path / "output",
            root=root,
            tag=tag,
            source_date_epoch=1_767_000_000,
        )


@pytest.mark.parametrize(
    "version",
    [
        "0.2.0-beta.0",
        "0.2.0-beta.01",
        "0.2.0-rc",
        "0.2.0-beta.1+dirty",
        "0.2.0-dev.1",
        "v0.2.0-beta.1",
    ],
)
def test_release_archive_rejects_invalid_prerelease_versions(tmp_path, version):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root, version)
    with pytest.raises(ValueError, match="Integration manifest must contain"):
        build_release_artifact(
            tmp_path / "output", root=root, source_date_epoch=1_767_000_000
        )


def test_prerelease_requires_its_own_changelog_section(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root, "0.2.0-beta.1")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 0.2.0\n")
    with pytest.raises(ValueError, match="no section for integration version"):
        build_release_artifact(
            tmp_path / "output",
            root=root,
            tag="v0.2.0-beta.1",
            source_date_epoch=1_767_000_000,
        )
