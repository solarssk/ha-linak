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
    assert manifest["requirements"] == ["bleak-retry-connector>=4.7.1"]
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
    checks = json.loads((ROOT / ".github/required-checks.json").read_text())
    assert len(checks) == len(set(checks))
    assert "Lint workflows (actionlint, zizmor)" in checks
    print("Repository metadata and translation parity passed")


if __name__ == "__main__":
    main()
