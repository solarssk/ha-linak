# Contributing

Use Python 3.14.2 or newer in an isolated environment. CI targets Ubuntu 24.04/Linux x86_64. Install the build backend with `python -m pip install --only-binary :all: --require-hashes -r .github/locks/build.txt`, then the exact environment with `python -m pip install --only-binary :all: --no-binary mock-open,pyric --no-build-isolation --require-hashes -r .github/locks/test.txt`. The two explicit source exceptions come from the HA test stack and Linux Bluetooth support; their builds cannot download unpinned build dependencies. On macOS, install `requirements-dev.txt` instead; Linux locks and installed-package checks are validated in CI. Run:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy custom_components/ha_linak
python scripts/check_repository.py
python scripts/check_dependencies.py
python scripts/update_locks.py --check
actionlint
```

Tests run against real Home Assistant with simulated Bluetooth and no network sockets. Do not connect a real desk in CI. Captures shared in issues must remove names, addresses, location and identifiers.

Use Conventional Commit titles and scoped branches. Update English/Polish docs and translation keys together. In a pull request describe the behavior, verification and Documentation impact. The maintainer merges after required checks pass; reviews are not mandatory while there is one maintainer.

HACS validation and hassfest check packaging; they do not prove physical hardware behavior. Only HA 2026.10.4 is currently validated. Movement and setting writes are not implemented.

## Markdown source format

Write each prose paragraph on one source line and let the editor, GitHub or HACS wrap it visually. Keep a list item's prose on one line too; nested lists and multi-paragraph items retain their Markdown structure. Do not wrap prose to a fixed column width. Preserve paragraph separators, headings, tables, code fences, HTML layouts, image/badge blocks, GitHub alert marker lines and intentional hard line breaks. Keep consecutive CHANGELOG.md bullets compact, without blank lines between them.

## Updating dependencies

`requirements-tools.txt` is the source for independent tools. `pytest-homeassistant-custom-component` in `requirements-dev.txt` owns the HA/pytest stack. Never add separate pytest or pytest-asyncio pins. `.github/ha-requirements.txt` is generated from the installed HA Bluetooth/USB manifests, not independently upgraded.

After a tools update, install uv from `.github/locks/uv.txt` with `--require-hashes` and run `python scripts/update_locks.py`. Commit regenerated locks in the same PR. To intentionally update transitive pins, remove only the relevant lock and regenerate it in a reviewed PR; freshness checking itself does not upgrade existing pins.

After a HA test-plugin upgrade, install the new plugin and its component requirements, update `hacs.json`, regenerate with `python scripts/check_dependencies.py --update`, and regenerate all locks. Installed checks must pass on Linux. On macOS use `--metadata-only` to regenerate files; that skips installed-platform validation and is not a substitute for Linux CI.

The locker version is owned by `.github/requirements-locker.txt` and is upgraded deliberately together with its lock and audit scope. Generated lock and component files are excluded from independent Dependabot changes. All locks target Python 3.14.2 and Linux glibc 2.39; do not use them as macOS or runtime HA dependency files.

## Coverage signals

Tests produce coverage.xml and junit.xml; a separate job uploads them to Codecov/Sonar only on trusted runs with the corresponding repository secrets. Keep Sonar Automatic Analysis disabled. The properties file classifies integration code and tests separately and matches the verified recmedia organization. CI helpers remain covered by CodeQL and regression tests. These external signals are advisory during the alpha.

## Review and repository settings

CodeRabbit reviews run on explicit maintainer request; automatic and incremental reviews are disabled. Run `python scripts/check_github_settings.py` with an existing administrative gh login to compare live main protection with .github/required-checks.json. This is a maintainer check, not a reason to expose admin credentials to CI.

## PR metadata and handoff

Before opening a PR, read [AGENTS.md](AGENTS.md), use the PR template and inspect GitHub's open release milestones. Every PR needs exactly one supported `type:` label (`bug`, `feature`, `chore` or `docs`), its open target release milestone and a responsible maintainer assignee. Currently the maintainer is @solarssk. Keep priority/area labels optional for this small project. These are real GitHub fields, not substitutes in a PR checklist. Dependabot PRs follow the same policy.

Open PRs with those fields supplied together, for example after choosing the actual target version from `gh api repos/solarssk/ha-linak/milestones`:

```sh
gh pr create --base main --title 'chore: describe the change' --body-file /tmp/pr-body.md --label 'type: chore' --milestone '<target-version>' --assignee solarssk
python scripts/check_pr_metadata.py --pr <number>
gh pr checks <number>
```

The required Documentation impact check also validates the type, open milestone and assignee. It reruns when these fields change. It has read-only permissions, executes on pull_request and never modifies PR metadata. Missing or closed release milestones must be resolved by the maintainer rather than fabricated by an agent.

Run `scripts.check_pr_docs.validate` against the final body and actual changed-file list before opening a PR; the required `## Documentation impact` section must be present. Read back the current head checks after publishing. Report pending checks as pending; handoff does not mean merge-ready. Follow failures through their fixed head, and verify main after a maintainer merge. See AGENTS.md for the complete start-to-handoff sequence.
