# Repository governance and validation

This personal hardware-research alpha follows Tier 1 of the [solarssk playbook](https://github.com/solarssk/playbook), with extra real-HA tests, type checking and packaging validation. Reassess before external installations depend on it or hardware movement is shipped. No official Home Assistant quality-scale award, HACS default-catalog acceptance, or earned OpenSSF rating is claimed.

CodeQL uses GitHub default setup. OpenSSF Scorecard runs in report-only mode; its result is not a certification.

Required checks after bootstrap: Quality, Tests, Hassfest, Dependency audit, Secret scan, Lint workflows (actionlint, zizmor), and Documentation impact. The names are recorded in `.github/required-checks.json` and tested against the real workflow job names. HACS validation is monitored separately because it also queries external branding/catalog services. The maintainer merges pull requests. Required review count is zero while there is one maintainer. Force pushes and branch deletion on main are blocked.

Dependency audit checks the generated `.github/audit-direct.txt`: independent tools, the lockfile resolver, and the connector version supplied by the tested Home Assistant. It does not certify the pinned Home Assistant release or all of its transitive dependencies. The test plugin owns HA/pytest versions. Bluetooth/USB packages are generated from that HA distribution’s manifests; CI checks the installed versions. The complete test graph, audit tools and resolver are installed from `.github/locks/*.txt` with `--require-hashes`. A freshness check regenerates locks while preserving existing transitive pins; a changed source input cannot silently use an old lock. Dependabot updates only independent tooling; generated files and the HA stack are maintained together.

Codecov and Sonar receive the successful test job’s coverage/JUnit artifacts through a separate advisory job. Automatic Analysis is disabled for the Sonar project; CI-based analysis uses sonar-project.properties. Tokens are exposed only to their upload steps, not to tests. Fork PRs and Dependabot runs skip the secret-bearing job. External upload failures do not change the Tests job result and these checks are not required merge gates. CI runs are the evidence for passing checks; workflow files alone are not results.

## Known boundaries

HACS and hassfest wrappers are SHA-pinned, but their upstream container references are mutable. Hash locks cover Python distribution archives; the source-only mock-open and Linux pyric packages are explicit exceptions to wheels-only installation. Their archive hashes are checked, their build backend is installed from a separate hashed lock, and build isolation/downloads are disabled. All other package installation requires wheels. These controls improve artifact integrity and reproducibility without claiming hermetic builds.

CodeQL, Scorecard and external GitHub App checks are advisory until deliberately made required. HACS validation is not a hardware test. No PR is merged automatically. Old Dependabot branches must be updated only after the CI foundation PR is merged, so they are checked with the new policy.

Coverage measures shipped integration code, with root-relative paths so Codecov and Sonar resolve the same files. Tests and CI helper scripts are not classified as shipped integration code in Sonar. CodeQL still analyzes Python source including CI helpers.

CodeRabbit automatic and incremental reviews are disabled by .coderabbit.yaml after that file is merged into the default branch. Reviews remain available on explicit maintainer request. Documentation checks parse NUL-delimited paths and include deleted rename sources.

To verify source/live protection consistency, the maintainer runs `python scripts/check_github_settings.py` using their existing administrative gh login. PR CI never receives an admin token.

The minimum/tested HA version is 2026.10.4 because HA 2026.10.2 pinned vulnerable uv 0.12.23. The independent lock resolver and the HA-owned uv copy now both use 0.13.5, above the advisory’s first patched version 0.13.4 (GHSA-hq85-5cpj-mr62). Do not override an HA-owned pin independently; upgrade its compatible test plugin and regenerate all locks together.
