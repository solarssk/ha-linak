"""Check publishing metadata, translations and version documentation."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/ha_linak"


def keys(value, prefix=""):
    result = set()
    for key, child in value.items():
        result.add(prefix + key)
        if isinstance(child, dict):
            result.update(keys(child, prefix + key + "."))
    return result


def main():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["domain"] == "ha_linak"
    assert list(manifest) == ["domain", "name"] + sorted(
        set(manifest) - {"domain", "name"}
    )
    assert manifest["requirements"] == [
        "bleak-retry-connector>=4.7.1",
        "dbus-fast>=5.0.22",
    ]
    assert manifest["codeowners"] == ["@solarssk"]
    assert manifest["documentation"] == "https://github.com/solarssk/ha-linak"
    assert manifest["issue_tracker"] == manifest["documentation"] + "/issues"
    assert re.search(
        r"^## " + re.escape(manifest["version"]) + r"(?:\s|$)",
        (ROOT / "CHANGELOG.md").read_text(),
        re.MULTILINE,
    )
    assert (COMPONENT / "brand/icon.png").is_file()
    english = json.loads((COMPONENT / "strings.json").read_text())
    for file in (COMPONENT / "translations").glob("*.json"):
        assert keys(json.loads(file.read_text())) == keys(english), file
    assert len(list((ROOT / "custom_components").iterdir())) == 1
    for name in ("README.md", "README.pl.md"):
        text = (ROOT / name).read_text()
        assert not re.search(r"<(?:picture|source|table|details|p|h1)\b", text, re.I), (
            name
        )
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" not in target and not target.startswith("#"):
                assert (ROOT / target.split("#")[0]).exists(), (name, target)
    for name in ("README.md", "README.pl.md"):
        github_readme = ROOT / ".github" / name
        text = github_readme.read_text()
        assert "<picture>" in text, github_readme
        assert 'align="center"' in text, github_readme
        assert 'rowspan="5"' in text
        assert 'rowspan="3"' in text, github_readme
        targets = re.findall(r'\]\(([^)]+)\)|(?:href|src|srcset)="([^"]+)"', text)
        for target in targets:
            value = next(value for value in target if value)
            if "://" not in value and not value.startswith("#"):
                assert (github_readme.parent / value.split("#")[0]).exists(), (
                    name,
                    value,
                )
    checks = json.loads((ROOT / ".github/required-checks.json").read_text())
    assert len(checks) == len(set(checks))
    assert "Lint workflows (actionlint, zizmor)" in checks
    print("Repository metadata and translation parity passed")


if __name__ == "__main__":
    main()
