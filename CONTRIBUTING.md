# Contributing

Use Python 3.14.2 or newer in an isolated environment. CI targets Ubuntu 24.04/Linux x86_64. Install its exact environment with `python -m pip install --require-hashes -r .github/locks/test.txt`. On macOS, install `requirements-dev.txt` instead; Linux locks and installed-package checks are validated in CI. Run:

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

HACS validation and hassfest check packaging; they do not prove physical hardware behavior. Only HA 2026.10.2 is currently validated. Movement and setting writes are not implemented.

## Updating dependencies

`requirements-tools.txt` is the source for independent tools. `pytest-homeassistant-custom-component` in `requirements-dev.txt` owns the HA/pytest stack. Never add separate pytest or pytest-asyncio pins. `.github/ha-requirements.txt` is generated from the installed HA Bluetooth/USB manifests, not independently upgraded.

After a tools update, install uv from `.github/locks/uv.txt` with `--require-hashes` and run `python scripts/update_locks.py`. Commit regenerated locks in the same PR. To intentionally update transitive pins, remove only the relevant lock and regenerate it in a reviewed PR; freshness checking itself does not upgrade existing pins.

After a HA test-plugin upgrade, install the new plugin and its component requirements, update `hacs.json`, regenerate with `python scripts/check_dependencies.py --update`, and regenerate all locks. Installed checks must pass on Linux. On macOS use `--metadata-only` to regenerate files; that skips installed-platform validation and is not a substitute for Linux CI.

The locker version is owned by `.github/requirements-locker.txt` and is upgraded deliberately together with its lock and audit scope. Generated lock and component files are excluded from independent Dependabot changes. All locks target Python 3.14.2 and Linux glibc 2.39; do not use them as macOS or runtime HA dependency files.
