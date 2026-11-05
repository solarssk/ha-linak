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

HACS validation and hassfest check packaging; they do not prove physical hardware behavior. Only HA 2026.10.4 is currently validated. Movement uses native slider/button controls with simulated tests and a bounded hardware observation; complete target arrival and physical Stop accuracy remain pending. Protected client activation and confirmed height-reference calibration writes are implemented. Activation/offset readback and one reconnect were observed on one DPG1C; this does not establish permanent client readiness or power-cycle persistence. Reminder profile selection preserves intervals and unrelated flags and requires an already active client. Hardware evidence covers Off/Profile 3 at status 1; profiles 1/2 and inactive-client acceptance remain unverified. Profile 1 sitting-duration editing shares that transaction, with a typed 1–60-minute product policy and an explicit standard-55-minute button. Hardware evidence covers only 50/55 in inactive profile 1, not the full input range, countdown timing or persistence. Other panel-setting writes are not implemented.

## Isolated HA startup smoke

CI also cold-boots and restarts a real HA Core process with minimal configuration in an official container image with this component copied into a fresh configuration. The supported-version smoke runs inside the required Tests job; the pinned preview job is advisory and does not expand the supported HA range. Images and expected versions are recorded in `.github/ha-smoke-targets.json`, with immutable digests. Update the supported target together with the HA test plugin, HACS minimum and generated component requirements; upgrade the preview deliberately.

To reproduce with Docker:

```sh
python3 scripts/run_ha_smoke.py --target supported --output /tmp/ha-linak-smoke
python3 scripts/run_ha_smoke.py --target preview --output /tmp/ha-linak-preview
```

The helper creates and removes its own internal Docker network and temporary configuration. The container runs with the invoking user ID so persisted files remain removable on Linux. It does not mount host D-Bus, Bluetooth devices or production config, expose ports, use privileged mode or permit external network egress. The test uses real bootstrap, config-entry restoration and platform imports, without pytest fixtures or a fake BLE transport. It requires HA to reach running with exactly one synthetic LINAK entry in the expected unavailable-device setup-retry state, and rejects unexpected ERROR logs, recovery mode or broken imports. Both process runs shut down before their container is removed. Reports also record pre-bootstrap and shutdown failures; cleanup attempts network removal even if container removal stalls. The Tests and preview job deadlines allow image download, both phases and cleanup, with extra room for dependency installation in Tests.

This is a startup/dependency check without a desk, not a working BLE connection or hardware acceptance result. HA entity setup with simulated device feedback remains covered by pytest; pairing, proxy behavior, physical movement and stopping need the hardware acceptance matrix. Reports explicitly mark `readings_validated` false. CI retains only synthetic reports and logs for seven days; it never uploads the configuration directory.

## Markdown source format

Do not use em dashes. Use periods, commas or colons. Write each prose paragraph on one source line and let the editor, GitHub or HACS wrap it visually. Keep a list item's prose on one line too; nested lists and multi-paragraph items retain their Markdown structure. Do not wrap prose to a fixed column width. Preserve paragraph separators, headings, tables, code fences, HTML layouts, image/badge blocks, GitHub alert marker lines and intentional hard line breaks. Keep consecutive CHANGELOG.md bullets compact, without blank lines between them.

## Technical documentation structure

Organize public documentation around a reader's task, following the separation of procedures, reference and explanation described by [Diátaxis](https://diataxis.fr/). Use the [document responsibility map](docs/README.md#document-responsibilities) as the content plan: it identifies each page's audience, purpose and information owner. Do not introduce another page without a distinct reader need.

| Content | Structure | Home |
| --- | --- | --- |
| Procedure | Prerequisites, ordered actions, expected results and recovery | Control guide, diagnostic manual or standalone experiment |
| Reference | Defined terms, tables of formats/states/constraints and precise limits | Protocol, settings, movement and connection references |
| Explanation | Component/lifecycle diagram, rationale, alternatives and consequences | Architecture and library comparison |
| Investigation/evidence | Question, method, observation, conclusion, uncertainty and next discriminating test | Investigation guide and hardware evidence register |
| Work chronology | Private attempts, temporary access details and next-agent instructions | Ignored local handoff; public release history belongs in CHANGELOG.md |

Integrate a finding into the section that owns the behavior. Rewrite obsolete conclusions and link to evidence instead of appending dated follow-ups. Preserve source revisions and environment metadata where they support reproducibility, but do not use dates or alpha versions as the manual's navigation. Separate implemented behavior, candidate semantics, simulated validation and physical observations.

Use Markdown tables for comparisons and fields, numbered lists for procedures and fenced Mermaid diagrams for meaningful control flow, sequence or ownership. Use charts only for measured quantitative comparisons; do not invent data to fill a visualization. Add a short explanation and outcome/limit beside each visual. Keep diagrams to one question and preserve equivalent technical details in text/tables for readers whose renderer lacks Mermaid. Product HACS Markdown has separate constraints in docs/hacs-presentation.md.

Before handing off documentation, follow one reader path from the index, check internal links/anchors, verify code/command names against the implementation and remove contradictory status claims. Keep one source of truth per fact. The [writing review checklist](https://github.com/vercel-labs/writing-guidelines/blob/main/command.md) helps with voice and readability; repository Markdown conventions take precedence over framework-specific front matter, MDX or frontend requirements.

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

Before opening a PR, read [AGENTS.md](AGENTS.md), use the PR template and inspect GitHub's open release milestones. Every PR needs exactly one supported `type:` label (`bug`, `feature`, `chore` or `docs`), its open target release milestone and a responsible maintainer assignee. Currently the maintainer is @solarssk. Keep priority/area labels optional for this small project. These are real GitHub fields, not substitutes in a PR checklist. Dependabot PRs follow the same policy. `.github/dependabot.yml` sets labels, assignee and the numeric target milestone for both ecosystems using [native Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference). Before closing a release milestone, create or select the next open release milestone and update `milestone` in every ecosystem entry. Use its GitHub number, not its version title. Existing PRs still need their live fields checked; configuration changes do not repair previously opened PRs.

Open PRs with those fields supplied together, for example after choosing the actual target version from `gh api repos/solarssk/ha-linak/milestones`:

```sh
gh pr create --base main --title 'chore: describe the change' --body-file /tmp/pr-body.md --label 'type: chore' --milestone '<target-version>' --assignee solarssk
python scripts/check_pr_metadata.py --pr <number>
gh pr checks <number>
```

The required Documentation impact check also validates the type, open milestone and assignee. It reruns when these fields change and reads their current values through the GitHub API rather than a potentially stale event payload. It has read-only permissions, executes on pull_request and never modifies PR metadata. Missing or closed release milestones must be resolved by the maintainer rather than fabricated by an agent.

Run `scripts.check_pr_docs.validate` against the final body and actual changed-file list before opening a PR; the required `## Documentation impact` section must be present. Read back the current head checks after publishing. Report pending checks as pending; handoff does not mean merge-ready. Follow failures through their fixed head, and verify main after a maintainer merge. See AGENTS.md for the complete start-to-handoff sequence.
