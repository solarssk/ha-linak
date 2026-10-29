# Agent instructions

This is a native Home Assistant custom integration for LINAK desks, installed through HACS.
The initial DPG1C alpha reads data only. Keep BLE transport and protocol independent of entities.

## Repository standard

Follow https://github.com/solarssk/playbook.
Tier: 1 (personal hardware research alpha; reassess before supporting external installations or shipping movement controls).
Tests, type checks and HA/HACS validation are included beyond the tier baseline. No Home Assistant quality-scale award or OpenSSF rating is claimed.

- Code, commits and repository documentation are English; user-facing translations include Polish.
- Preserve centimeter heights, entity unique IDs and the ha_linak domain.
- No real BLE scans, hardware movement, credentials or private captures in automated tests.
- Request timeouts invalidate the BLE session; memory responses have no slot identity.
- User-visible changes require CHANGELOG.md and relevant README changes.
- Run pytest, ruff check/format, mypy, repository/dependency checks, lock freshness and actionlint before pushing. Linux installed-package validation is required in CI; macOS metadata-only checking is limited.
- Regenerate locks in the same PR as dependency input changes. The HA test plugin owns pytest/HA; generated component pins come from that HA distribution.
- Keep required workflow names in .github/required-checks.json and live protection consistent.
- After the initial bootstrap, use scoped branches and pull requests. Do not merge on the user's behalf.
- Do not publish real hardware movement support before supervised device tests.
