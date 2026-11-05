# Repository governance and validation

This public HACS package adopts Tier 2 of the [solarssk playbook](https://github.com/solarssk/playbook/blob/main/docs/tiers.md) before enabling physical hardware control. The integration provides native movement controls using explicitly configured measured bounds. No official Home Assistant quality-scale award, HACS default-catalog acceptance, or earned OpenSSF rating is claimed.

CodeQL uses GitHub default setup. OpenSSF Scorecard runs in report-only mode; its result is not a certification.

Required checks after bootstrap: Quality, Tests, Hassfest, Dependency audit, Secret scan, Lint workflows (actionlint, zizmor), and Documentation impact. The names are recorded in `.github/required-checks.json` and tested against the real workflow job names. HACS validation is monitored separately because it also queries external branding/catalog services. The maintainer merges pull requests. Required review count is zero while there is one maintainer. Force pushes and branch deletion on main are blocked.

Dependency audit checks the generated `.github/audit-direct.txt`: independent tools, the lockfile resolver, and the connector version supplied by the tested Home Assistant. It does not certify the pinned Home Assistant release or all of its transitive dependencies. The test plugin owns HA/pytest versions. Bluetooth/USB packages are generated from that HA distribution’s manifests; CI checks the installed versions. The complete test graph, audit tools and resolver are installed from `.github/locks/*.txt` with `--require-hashes`. A freshness check regenerates locks while preserving existing transitive pins; a changed source input cannot silently use an old lock. Dependabot updates only independent tooling; generated files and the HA stack are maintained together.

Codecov and Sonar receive the successful test job’s coverage/JUnit artifacts through a separate advisory job. Automatic Analysis is disabled for the Sonar project; CI-based analysis uses sonar-project.properties. Tokens are exposed only to their upload steps, not to tests. Fork PRs and Dependabot runs skip the secret-bearing job. External upload failures do not change the Tests job result and these checks are not required merge gates. CI runs are the evidence for passing checks; workflow files alone are not results.

## Known boundaries

HACS and hassfest wrappers are SHA-pinned, but their upstream container references are mutable. Hash locks cover Python distribution archives; Linux pyric is the only explicit exception to wheels-only installation. Its archive hash is checked, its build backend is installed from a separate hashed lock, and build isolation/downloads are disabled. The retired plugin's mock-open exception is removed. All other package installation requires wheels. These controls improve artifact integrity and reproducibility without claiming hermetic builds.

CodeQL, Scorecard and external GitHub App checks are advisory until deliberately made required. HACS validation is not a hardware test. No PR is merged automatically. Old Dependabot branches must be updated only after the CI foundation PR is merged, so they are checked with the new policy.

Coverage measures shipped integration code, with root-relative paths so Codecov and Sonar resolve the same files. Tests and CI helper scripts are not classified as shipped integration code in Sonar. CodeQL still analyzes Python source including CI helpers.

CodeRabbit automatic and incremental reviews are disabled by .coderabbit.yaml after that file is merged into the default branch. Reviews remain available on explicit maintainer request. Documentation checks parse NUL-delimited paths and include deleted rename sources.

Main uses the active `LINAK main protection` repository ruleset, which is visible to read-only repository users and Scorecard without an additional secret. Its source is `.github/rulesets/main.json`; the maintainer verifies the live ruleset and GitHub's effective rules with `python scripts/check_github_settings.py`. The checker also validates classic protection during a pre-migration state. PR CI never receives an admin token.

The ruleset targets only the default branch, has no bypass actors, requires the seven checks from `.github/required-checks.json` from GitHub Actions with strict up-to-date checks, requires pull requests while keeping approvals at zero, dismisses stale reviews, and preserves signed commits, linear history, conversation resolution, deletion blocking and force-push blocking. Code-owner and last-push approvals remain disabled. The migration added and verified this active ruleset before removing classic protection, so the two systems were enforced together during the transition. GitHub layers active rulesets and classic branch protection; it reports effective branch rules through the read-only rules endpoint.

The minimum and simulated-test target is HA 2026.11.0, matching the built-in Marketplace and local integration/Marketplace brand routes. The official `pytest-homeassistant[bluetooth]==2026.11.0` owns HA, pytest and pytest-asyncio, replacing the retired custom-component plugin. The independent lock resolver and the HA-owned uv copy both use 0.13.6, above the advisory's first patched version 0.13.4 (GHSA-hq85-5cpj-mr62). Do not override an HA-owned pin independently; upgrade its compatible test plugin and regenerate all locks together. `hacs.json` declares the minimum for releases, not a universal runtime rejection of older manual/default-branch installs.

Coverage reporting is no longer a transitive dependency of the official test plugin. `requirements-tools.txt` owns `pytest-cov` explicitly so the existing CI coverage/JUnit command and advisory uploads remain intact. The plugin still controls pytest itself; this reporting tool does not add a competing version pin.

The pure protocol decoders have a bounded Atheris fuzz target in `fuzz/fuzz_protocol.py`, run by the required Tests job. Scorecard recognizes the Atheris integration, but this does not enroll the repository in OSS-Fuzz or guarantee a particular Scorecard result.

## Tier 2 assessment

Tests, type checks, CodeQL default setup (Python, weekly), workflow lint, dependency audit, secret scanning, signed protected main, documentation-impact checks, contribution/PR templates and report-only Scorecard are already configured. Live branch protection and CodeQL settings were checked during this assessment. Standard `type:` labels and the 0.1.0 milestone exist. The maintainer remains the merger; review count zero is deliberate for a solo-maintained repository.

No container image is published, so container scanning and image SBOM requirements do not apply. Display a latest-release badge or claim a release exists only when a published GitHub Release provides that evidence. The first external release needs a versioned GitHub Release with installation/upgrade actions and associated milestone work. The reusable playbook verification workflow is optional; this repository checks its own HA-specific gates and settings.

## Release preparation and publication

The 0.1.0 changelog section describes the first public version. Preparing it sets the component manifest and the matching changelog section; it does not create a tag, GitHub Release, catalog listing or completed hardware acceptance. The [roadmap gates](roadmap.md#evidence-and-release-gates) and [H1–H12 matrix](hardware-results.md#hardware-acceptance-matrix) retain their outstanding requirements. Choosing to end an experiment does not pass or remove them.

| Source | Responsibility |
| --- | --- |
| `custom_components/ha_linak/manifest.json` | Installed integration version |
| `CHANGELOG.md` | Matching version section and the single English-only public release body, starting with the first public version; internal alpha history remains in Git |
| `hacs.json` and the four product READMEs | Minimum HA version, installation/upgrade actions and product limitations, not a second integration-version field |
| GitHub milestone | Live release planning, not publication evidence |
| Git tag and GitHub Release | Published source/version only after a separate maintainer action |
| `.github/workflows/release-artifact.yml` | Builds and attests the integration ZIP; uploads assets only to an existing Release when explicitly dispatched with publication enabled |
| HA test inputs, component pins, smoke targets and locks | Independently owned dependency/compatibility versions, not integration release numbers |

Follow the [changelog standard](../CONTRIBUTING.md#changelog-and-release-notes) when preparing the body. Do not copy the development commit history into it, add a speculative release date or relabel historical alpha evidence as 0.1.0 testing.

Publication remains a separate maintainer decision. Dispatch the release artifact workflow on the exact tag with publication disabled to build and attest without changing a GitHub Release. To attach assets, first create the release and then explicitly dispatch the workflow on that tag with publication enabled. It verifies the tag, existing release, signer workflow and provenance before uploading the integration ZIP, checksum and `.intoto.jsonl` bundle. It never creates or pushes a tag or creates a Release. Use the [release integrity guide](release-integrity.md) to verify the downloaded archive. GitHub-generated source archives are not covered by this attestation.

Before publication, inspect the final revision's existing checks, installation/upgrade instructions, known limitations and remaining roadmap gates. Local macOS metadata checks do not replace Linux installed-package/container validation, and no-radio CI does not replace physical acceptance. Verify the installed released artifact separately before claiming that delivery is validated. Do not close the target milestone until Dependabot's next target has been selected and updated as described in CONTRIBUTING.md.

## Agent workflow and PR metadata

AGENTS.md is the single instruction source and CLAUDE.md imports it. It provides task startup, a read-first map, validation and explicit PR handoff requirements. CONTRIBUTING.md owns the runnable local checks; the PR template makes the handoff visible to reviewers. Do not duplicate these rules into independent tool files.

Every PR requires one supported type label, an open target release milestone and a maintainer assignee. This is the repository's explicit policy, using playbook label conventions; it is not a universal Tier 2 requirement. Area/priority labels remain optional. Query the active milestone on GitHub instead of keeping a version in agent instructions.

The existing required Documentation impact job runs check_pr_metadata.py in addition to check_pr_docs.py, with read-only contents/pull-request permissions and the same check name. It reads current metadata through the GitHub API so out-of-order label, milestone and assignee events cannot validate an older event snapshot. Metadata edits trigger a new run. The job is skipped once the pull request is no longer open, because a rerun after a squash merge cannot diff the deleted head and would only report a false failure; every open pull request still runs it. No admin token, automatic metadata mutation or pull_request_target checkout is introduced. The metadata validator accepts an event payload in CI and can read a live PR through --pr for maintainer handoff verification. Its passing result is a snapshot; agents must still verify live fields/current head before handoff. The maintainer remains the only merger.

## Label taxonomy

Keep one compact taxonomy, with exactly one type per PR:

| Label | Use |
| --- | --- |
| `type: bug` | Fix incorrect behavior |
| `type: feature` | Add user-facing behavior |
| `type: chore` | Maintain tooling, CI or dependencies |
| `type: docs` | Change documentation or translations |
| `dependencies` | Supplement the type for dependency updates |
| `security` | Supplement the type for security corrections |

Do not keep parallel bug/documentation/enhancement aliases, language/ecosystem labels or one-off blocking labels. Dependabot supplies type: chore, dependencies, the maintainer assignee and the numeric target milestone explicitly for both ecosystems. The metadata gate remains read-only and enforces the same policy for bot and human PRs. Update all configured milestone numbers before closing the current release milestone; existing PRs need a separate live-field check. Before retiring a label, inspect all its issue/PR associations and migrate any useful classification first. Removing an obsolete status label also removes it from historical items; that must be deliberate.

## Startup and version compatibility gates

The existing required `Tests` job includes the supported-version full-process cold-boot/restart smoke. No required check name or live protection setting changes. `HA preview smoke` runs the separately pinned preview as an advisory compatibility signal. These complement the hash-locked in-process HA/pytest suite rather than replacing it. Both use official images pinned by digest and isolated temporary configurations; see [local reproduction and boundaries](../CONTRIBUTING.md#isolated-ha-startup-smoke).

Both targets currently pin stable 2026.11.0 at the official GHCR index digest `sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e`. There is no newer preview at this update; the advisory job deliberately repeats stable rather than presenting the older 2026.11 beta as forward validation. Upgrade that target when a newer preview is available. The required supported smoke remains unchanged in strength.

A successful no-radio startup confirms loading, expected setup retry, real core startup, platform imports and shutdown. It does not confirm a connected desk, UI rendering, firmware permissions or physical Stop. An image version mismatch, dependency/setup failure, recovery mode, import exception or unexpected ERROR log fails the smoke. A preview failure is visible with saved logs but does not block a supported-version fix or claim preview support.
