# 🤝 Help improve LINAK

**English** · [Polski](CONTRIBUTING.pl.md)

You can help by reporting a problem, suggesting an improvement or pointing out confusing instructions. You don't need to write code.

## Where to start

Choose the kind of help you'd like to give:

| I want to… | Start here |
| --- | --- |
| 🐛 Report something that doesn't work | [Report a bug](#-report-a-bug) |
| 💡 Suggest a feature or clearer instructions | [Share an idea](#-share-an-idea) |
| 🧪 Help test a desk panel | [Test with your desk](#-test-with-your-desk) |
| 🛠️ Change the code or documentation | [Prepare a contribution](#-prepare-a-contribution) |

## 🐛 Report a bug

Tell us what happened in your own words. A screenshot can help; you don't need to diagnose the cause.

1. Check the [bug-report and debug-log guide](docs/diagnostics.md#prepare-a-bug-report) and [existing issues](https://github.com/solarssk/ha-linak/issues) for the same problem.
2. Open a [bug report](https://github.com/solarssk/ha-linak/issues/new?template=bug.yml).
3. Describe what you expected, what happened instead and the steps that led to it.

The form also asks for a few details:

| Detail | What to include |
| --- | --- |
| Versions | Your Home Assistant and LINAK integration versions |
| Desk | Panel model, if you know it |
| Connection | A Bluetooth adapter or proxy, if you know which one |
| Timeline and recovery | Time with timezone, action, first error, whether readings returned by themselves and how long you waited |
| Diagnostics and log | Reviewed LINAK diagnostic JSON and a narrow debug interval, collected with [these steps](docs/diagnostics.md#collect-a-narrow-debug-log) |

Write “not sure” if you can't find a detail. You can add it later if the maintainer needs it.

Prefer help writing? The optional [AI-assisted report instructions](docs/diagnostics.md#prepare-a-report-with-ai) turn your observations into a draft for review. Reporting does not require AI or log attachments.

### Before sharing

🔒 **Before sharing:** hide device names, Bluetooth addresses, room/location details and credentials in screenshots and logs. Report a suspected security vulnerability through [private vulnerability reporting](https://github.com/solarssk/ha-linak/security/advisories/new), not a public issue.

⚠️ **Keep the desk safe:** don't repeat an unexpected movement just to record it. Describe what you already observed.

## 💡 Share an idea

Open an [issue](https://github.com/solarssk/ha-linak/issues/new) and describe the task you'd like to do. Explain what gets in the way today and what would help.

Unclear wording, missing instructions and translation corrections are useful contributions too. You can suggest a sentence without setting up a development environment.

## 🧪 Test with your desk

Start with the [device support and tester guide](docs/device-support.md). It explains which panel details help and what compatibility is known.

Agree on any hardware experiment with the maintainer before starting. Initial movement tests need someone at the desk and a way to stop it. Software tests passing is not proof that physical movement or stopping is safe.

## 🛠️ Prepare a contribution

Read [AGENTS.md](AGENTS.md) before changing files. It lists the relevant references for each kind of change.

Keep your contribution focused:

- Use a scoped branch and a [Conventional Commit](https://www.conventionalcommits.org/) title, such as `fix: explain a connection error`.
- Update English and Polish documentation or translation keys together.
- Describe the problem, resulting behavior and validation in the [PR template](.github/PULL_REQUEST_TEMPLATE.md).
- Keep user instructions about what to do and expect. Put protocol details and research evidence in the technical references.

The expandable sections below are for developers and maintainers. You don't need them to report a bug or suggest an improvement.

<details>
<summary>🧰 Set up development and run checks</summary>

## Development environment

Use **Python 3.14.2 or newer** in an isolated environment. CI runs on Ubuntu 24.04/Linux x86_64.

On Linux, install the pinned build backend and test environment:

```sh
python -m pip install --only-binary :all: --require-hashes -r .github/locks/build.txt
python -m pip install --only-binary :all: --no-binary pyric --no-build-isolation --require-hashes -r .github/locks/test.txt
```

The `pyric` source exception comes from Linux Bluetooth support. Its build cannot download unpinned build dependencies. The retired test plugin's `mock-open` dependency and exception are no longer needed.

On macOS, install the development requirements instead:

```sh
python -m pip install -r requirements-dev.txt
```

### Run the full validation block

Run these checks after your final patch and before pushing:

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

On macOS, replace only the dependency check with:

```sh
python scripts/check_dependencies.py --metadata-only
```

That checks generated metadata, not installed Linux packages. Linux locks and installed-package validation still belong to CI; report this distinction in your PR.

Tests use real Home Assistant with simulated Bluetooth and no network sockets. Never connect a real desk in automated tests.

On Linux x86_64, run the coverage-guided protocol fuzzer with `python fuzz/fuzz_protocol.py --duration-seconds 30`. It uses Atheris against the pure response decoders, with synthetic framing seeds and no Home Assistant, Bluetooth, network or movement. The run is bounded to 300 seconds; CI runs it for 30 seconds in the required Tests job. Atheris 3.1.0 currently publishes a Python 3.14 Linux x86_64 wheel only, so the normal macOS development environment skips this optional tool.

## Isolated HA startup smoke

CI also cold-boots and restarts Home Assistant in an official container, without a desk. This checks startup and dependencies, not Bluetooth communication or hardware behavior.

| Check | Role |
| --- | --- |
| Supported-version smoke | Part of the required Tests job |
| Pinned preview smoke | Advisory; temporarily repeats stable 2026.11.0 because no newer preview exists; does not validate a future HA version |
| Target definitions | `.github/ha-smoke-targets.json`, including immutable image digests |

Update the supported target together with the HA test plugin, HACS minimum and generated component requirements. Upgrade the preview deliberately.

To reproduce with Docker:

```sh
python3 scripts/run_ha_smoke.py --target supported --output /tmp/ha-linak-smoke
python3 scripts/run_ha_smoke.py --target preview --output /tmp/ha-linak-preview
```

The helper's isolation and expected results are:

- Create and remove an internal Docker network and temporary configuration.
- Run as the invoking user so persisted files remain removable on Linux.
- Do not mount host D-Bus, Bluetooth devices or production configuration.
- Do not expose ports, use privileged mode or permit external network egress.
- Use real bootstrap, config-entry restoration and platform imports, without pytest fixtures or a fake BLE transport.
- Require HA to reach running with exactly one synthetic LINAK entry in the expected unavailable-device setup-retry state.
- Reject unexpected ERROR logs, recovery mode and broken imports.
- Shut down both HA runs before removing their containers.

Reports include pre-bootstrap and shutdown failures. Cleanup attempts network removal even if container removal stalls. Job deadlines allow image download, both phases and cleanup, plus dependency installation in Tests.

CI retains only synthetic reports and logs for seven days, never the configuration directory. Reports mark `readings_validated` false. Entity behavior with simulated feedback remains covered by pytest; pairing, proxies, movement and stopping need the [hardware acceptance matrix](docs/hardware-results.md#hardware-acceptance-matrix).

### State validation limits honestly

HACS validation and hassfest check packaging, not physical behavior. The simulated test stack targets HA 2026.11.0. Linux installed-package and cold-boot/restart results require CI evidence; the documented macOS checks do not replace them. Earlier hardware observations retain their recorded HA versions.

| Feature | Evidence | Still unverified |
| --- | --- | --- |
| Movement and Stop | Simulated tests and a bounded hardware observation | Complete target arrival and physical Stop accuracy |
| Client activation and height calibration | Protected setters; activation/reference readback and one reconnect on one DPG1C | Permanent readiness and power-cycle persistence |
| Reminder profile | Preserved intervals/flags; Off/Profile 3 at client status 1 | Profiles 1/2 and inactive-client acceptance |
| Sitting/standing times, profiles 1–3 | Six protected 1–60-minute inputs and profile 1 standard-55-minute button; hardware observation at 50/55 sitting minutes in inactive profile 1 | Other five fields, full input range, countdown and persistence; input bounds are product policy, not firmware or medical limits |
| Stored Inch/Metric preference | Protected transaction without wake/movement; readback and one reconnect | Physical CM/MM share the known BLE state; immediate stationary OLED redraw is unconfirmed |
| Other panel-setting writes | Not implemented | A verified command contract is required |

Use the [hardware evidence register](docs/hardware-results.md) for the full methods and limits.

</details>

<details>
<summary>📝 Write and organize documentation</summary>

## Markdown source format

Keep Markdown readable in both source and rendered form:

- Write each prose paragraph on one source line. Let the reader's editor or browser wrap it.
- Keep each list item's prose on one source line too. Preserve nested-list and multi-paragraph structure where needed.
- Use periods, commas or colons instead of em dashes.
- Preserve paragraph separators, headings, tables, code fences, HTML layouts, image/badge blocks, GitHub alerts and intentional hard line breaks.
- Keep consecutive `CHANGELOG.md` bullets together, without blank lines between them.

## Technical documentation structure

Write for the reader's task. Follow [Diátaxis](https://diataxis.fr/) and the [document responsibility map](docs/README.md#document-responsibilities); add a page only for a distinct reader need.

| Content | Include | Home |
| --- | --- | --- |
| Procedure | Prerequisites, actions, expected results and recovery | Control guide, diagnostic manual or standalone experiment |
| Reference | Terms, formats, states, constraints and precise limits | Protocol, settings, movement and connection references |
| Explanation | Boundaries, rationale, alternatives and consequences | Architecture and library comparison |
| Investigation/evidence | Question, method, observation, conclusion, uncertainty and next test | Investigation guide and hardware evidence register |
| Work chronology | Private attempts, temporary access details and next-agent instructions | Ignored local handoff; public release history goes in `CHANGELOG.md` |

When updating a document:

- Update the section that owns the behavior instead of appending dated discoveries or version follow-ups.
- Replace obsolete conclusions while preserving uncertainty, source revisions and environment details needed for reproduction.
- Keep implemented behavior, protocol candidates, simulated validation and physical observations distinct.
- Use tables for comparisons and fields, numbered lists for procedures and Mermaid for state, sequence or ownership.
- Use charts only for measured quantities. Don't invent data for a visualization.
- Give each diagram one purpose, explain its outcome/limit and keep equivalent technical details in text or tables.
- Keep dates and alpha versions out of the manual's navigation.
- Follow [HACS presentation constraints](docs/hacs-presentation.md) for product READMEs.

Before handing off, follow one reader path from the [index](docs/README.md), check links/anchors, verify names and commands against the implementation, and remove contradictory claims. Keep one source of truth per fact.

Keep each owner guide in one language. Put Polish guidance in a separate `.pl.md` file with reciprocal language links at the top. Do not insert Polish paragraphs into English procedures or switch back to English after a Polish subsection. Label links to English-only technical references explicitly in the Polish guide. Repository-wide policies such as SECURITY.md may keep complete English and Polish sections under separate level-two language headings, without alternating between them.

The [writing review checklist](https://github.com/vercel-labs/writing-guidelines/blob/main/command.md) can help with clarity. Repository Markdown conventions take precedence over framework-specific front matter, MDX and frontend requirements.

### Changelog and release notes

`CHANGELOG.md` is the source for the public GitHub Release body, not a commit log. Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [GitLab's user-facing entry guidance](https://docs.gitlab.com/development/changelog/): explain what changes for the user and why it matters. Group related changes, omit internal refactors and CI housekeeping without user impact, and avoid unsupported reliability or safety claims.

Keep `## Unreleased` at the top and plain version headings such as `## 0.1.0` below it so anchors remain predictable. Start each version with one or two sentences about the outcome. Include only nonempty sections, in this order:

| Heading | Content |
| --- | --- |
| `### ⚠️ Before you update` | Requirements, migration, breaking changes and required actions; always first when applicable |
| `### ✨ New` | New user-facing capabilities |
| `### 🔧 Improvements` | Changes to an existing user experience |
| `### 🐛 Fixes` | Corrected visible behavior |
| `### 🔒 Security` | Actual product-security impact, not routine tooling maintenance |
| `### 📌 Known limitations` | Material remaining gaps, uncertainty and links to the owning reference |

Deprecations and removals must be explicit in Before you update or clearly named separate sections when needed. Use one emoji per section heading, never instead of its text and not in every bullet. Emoji are this repository's visual convention, not a requirement of the cited guides. Write short, concrete bullets, with no slogans, raw logs, commit SHAs or test chronology. Link detailed evidence rather than copying the investigation into release notes.

Write the public changelog and GitHub Release body in English only, without a duplicated Polish block. This exception applies only to release notes: product READMEs and bilingual public documentation retain English/Polish content, and HA strings remain aligned in both languages. Technical references retain their documented English-language structure. The first public release describes the available product, requirements and material current limitations, not fixes relative to internal alphas. Later releases describe changes since the previous public release. Unpublished alpha history and internal problem chronology stay in Git, not in the public changelog or a separate public archive. Do not invent a publication date; preparation must be marked unpublished until the maintainer actually publishes.

There is no release workflow or extractor in this repository. For manual publication, use the complete English version section between its `## VERSION` heading and the next level-two heading, including limitations, without copying Unreleased. Resolve repository-relative documentation links against the actual release tag when copying the body to GitHub. Remove the preparation-only unpublished notices only as part of the actual publication. Do not maintain a second release-notes file. The [release preparation boundary](docs/governance.md#release-preparation-and-publication) separates editing from publishing.

</details>

<details>
<summary>📦 Update dependencies</summary>

## Updating dependencies

Use the existing dependency owners rather than adding competing pins:

| File or package | Owns |
| --- | --- |
| `requirements-tools.txt` | Independent tools, including `pytest-cov` for CI coverage reports |
| `pytest-homeassistant[bluetooth]` in `requirements-dev.txt` | HA, pytest, pytest-asyncio and optional Bluetooth helpers; do not pin these separately |
| `.github/ha-requirements.txt` | Generated requirements from installed HA Bluetooth/USB manifests |
| `.github/requirements-locker.txt` | The deliberately chosen resolver version |

For an independent tool update:

1. Install uv from `.github/locks/uv.txt` with `--require-hashes`.
2. Run `python scripts/update_locks.py`.
3. Commit regenerated locks in the same PR.

For a HA test-plugin upgrade:

1. Install the matching official `pytest-homeassistant[bluetooth]` release and its component requirements. Do not co-install the retired `pytest-homeassistant-custom-component`.
2. Update `hacs.json`.
3. Run `python scripts/check_dependencies.py --update`.
4. Regenerate all locks and pass installed-package checks on Linux.

On macOS, add `--metadata-only` when generating dependency files. It skips installed-platform validation and is not a substitute for Linux CI.

The official plugin loads automatically and enables custom integrations by default. Import helpers from `pytest_homeassistant`, without a duplicate `pytest_plugins` registration or wrapper fixture. Keep `-p no:respx` in pytest options so HA installs its HTTPX alias before the separate respx plugin can import it. The plugin's socket/DNS guards stay enabled; brand-handler tests call the real HA views with in-memory requests rather than starting an HTTP server.

Lock freshness checks preserve existing transitive pins. To deliberately update them, remove only the relevant lock and regenerate it in a reviewed PR. Upgrade the resolver together with its lock and audit scope.

Dependabot's pip `allow` list names only independent tools from `requirements-tools.txt` and `requirements-build.txt`; update that list and its tooling group when adding a tool. HA-owned packages and the deliberately chosen `uv` resolver are not eligible for independent updates. Keep generated component, audit and resolver inputs fetchable: excluding a file referenced through `-r` or `-c` prevents Dependabot from parsing the graph before package filters run. Only `.github/locks/**` is path-excluded. Regenerate locks after an accepted tool update; the policy tests check input reachability and package ownership. See the [native allow/ignore semantics](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#allow--).

Locks target Python 3.14.2 and Linux glibc 2.39; don't use them as macOS or runtime HA dependency files.

</details>

<details>
<summary>📬 Open a PR and check the handoff</summary>

## PR metadata and handoff

Use [AGENTS.md](AGENTS.md) and the [PR template](.github/PULL_REQUEST_TEMPLATE.md). Fill in **Documentation impact** with the files you changed or a concrete reason no update is needed.

Every PR, including Dependabot PRs, needs these actual GitHub fields:

| Field | Set it to |
| --- | --- |
| Type label | Exactly one of `type: bug`, `type: feature`, `type: chore`, `type: docs` |
| Milestone | The open release receiving the change; check GitHub rather than guessing |
| Assignee | The responsible maintainer, currently @solarssk |

Priority and area labels aren't required for this small project. Checking a box in the description doesn't set GitHub metadata.

For example, after checking `gh api repos/solarssk/ha-linak/milestones`:

```sh
gh pr create --base main --title 'chore: describe the change' --body-file /tmp/pr-body.md --label 'type: chore' --milestone '<target-version>' --assignee solarssk
python scripts/check_pr_metadata.py --pr <number>
gh pr checks <number>
```

Before opening the PR, run `scripts.check_pr_docs.validate` against its final body and actual changed-file list. The `## Documentation impact` section is required.

Before handing it off:

1. Read back the live metadata and current head's checks.
2. Inspect review comments and unresolved findings.
3. Fix failures, then follow the checks on the new head.
4. Report passed, pending, skipped and failed checks accurately. Keep local tests, Linux CI and hardware observations separate.

The maintainer merges after required checks pass. Reviews aren't mandatory while there is one maintainer. Don't merge, release or tag on their behalf. After a reported merge, verify main's checks before claiming integration is complete.

The Documentation impact job also validates type, open milestone and assignee. It reruns on metadata edits, reads live GitHub values with read-only permissions and never repairs metadata itself. Ask the maintainer to resolve a missing or closed release milestone; don't create one to satisfy a gate.

### Keep Dependabot metadata current

`.github/dependabot.yml` supplies labels, assignee and numeric target milestone for each ecosystem through [native Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

Before closing a release milestone, select or create the next open one and update `milestone` in every ecosystem entry. Use its GitHub number, not its title. Check existing PRs separately; configuration changes don't repair their fields.

## Coverage signals

Tests produce `coverage.xml` and `junit.xml`. A separate trusted-run job uploads them to Codecov/Sonar using the corresponding repository secrets. These signals are advisory and do not establish hardware acceptance.

Keep Sonar Automatic Analysis disabled. The properties file separates integration code from tests and matches the verified recmedia organization. CI helpers remain covered by CodeQL and regression tests.

## Review and repository settings

CodeRabbit automatic and incremental reviews stay disabled. Request a review only when the maintainer explicitly asks.

Maintainers can compare live main protection with `.github/required-checks.json` using:

```sh
python scripts/check_github_settings.py
```

Use an existing administrative gh login locally. Never expose admin credentials to PR CI.

</details>
