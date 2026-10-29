# Contributing

Install Python 3.14 and `requirements-dev.txt` in an isolated environment. Run:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy custom_components/ha_linak
python scripts/check_repository.py
actionlint
```

Tests run against real Home Assistant with simulated Bluetooth and no network sockets. Do not connect a real desk in CI. Captures shared in issues must remove names, addresses, location and identifiers.

Use Conventional Commit titles and scoped branches. Update English/Polish docs and translation keys together. In a pull request describe the behavior, verification and Documentation impact. The maintainer merges after required checks pass; reviews are not mandatory while there is one maintainer.

HACS validation and hassfest check packaging; they do not prove physical hardware behavior. Only HA 2026.10.2 is currently validated. Movement and setting writes are not implemented.
