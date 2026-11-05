"""Release archives contain only the installable integration and are reproducible."""

from pathlib import Path
import zipfile

import pytest

from scripts.build_release_artifact import build_release_artifact


def _package_root(root: Path) -> None:
    component = root / "custom_components/ha_linak"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text('{"version":"0.1.0"}\n')
    (component / "protocol.py").write_text("value = 1\n")
    (component / "__pycache__").mkdir()
    (component / "__pycache__/ignored.pyc").write_bytes(b"compiled")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n")
    (root / "README.md").write_text("not part of the integration archive\n")


def test_release_archive_is_reproducible_and_contains_installable_paths(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root)
    first, first_checksum = build_release_artifact(
        tmp_path / "first",
        root=root,
        tag="v0.1.0",
        source_date_epoch=1_767_000_000,
    )
    second, _ = build_release_artifact(
        tmp_path / "second",
        root=root,
        tag="v0.1.0",
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


def test_release_archive_rejects_a_tag_for_a_different_version(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    _package_root(root)

    with pytest.raises(ValueError, match="does not match version"):
        build_release_artifact(
            tmp_path / "output",
            root=root,
            tag="v0.2.0",
            source_date_epoch=1_767_000_000,
        )
