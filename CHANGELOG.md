# Changelog

## Unreleased

- Clarify required HA coroutine hooks and simplify test setup/assertions to address existing Sonar findings without changing device behavior.
- Group sensors, diagnostics and controls in one entity section across GitHub/HACS READMEs; link the native HA test procedure.
- Add a standalone supervised movement test runner with characteristic checks, a 2 cm experiment limit, timed Stop and English result-recording instructions.
- Record manufacturer settings/variant evidence, pinned community protocol candidates, protected offset calibration and post-install configuration requirements for the next control milestones.
- Standardize Markdown prose and list-item paragraphs on single source lines; document the authoring convention while preserving structural markup and rendered content.

- Use a readable desk name instead of the Bluetooth address when Home Assistant has no advertised name, and replace an existing address-only entry title on the next setup.
- Preserve the GitHub presentation in .github/README files and provide separate HACS product descriptions with portable Markdown and artwork.
- Consolidate repository labels into four change types plus dependency and security markers.
- Require PR type, release milestone and assignee in the existing documentation gate; document the complete agent workflow and handoff checks.
- Document DPG1C authentication/initialization research and the hardware validation plan; distinguish notification stages and log elapsed stage time without device identifiers.
- Show LINAK and the advertised desk name on Bluetooth discovery cards instead of the internal integration domain.
- Detect cumulative retreat from the best position in the requested direction. Backward movement and jitter no longer reset the progress deadline.
- Preserve the final movement Stop and its reservation through repeated cancellation using the same bounded cleanup-draining path as close().
- Wait for the reserved Stop to settle before disconnecting on close cancellation, including repeated cancellation and Stop timeout. Observe late errors from shielded cleanup tasks.
- Discard the movement controller and BLE transport after a timeout, even when final Stop succeeds. Reserve the controller until a shared explicit Stop fully completes, preventing overlapping targets and late Stop writes.
- Group sensor rows under one merged entity-type cell in both README tables and place icons beside the HA entity labels.
- Separate supported panels, HA sensor entities, requirements and environment validation in both READMEs; match entity labels to HA translations and add section icons and quality badges.
- Extract the supplied official Illustrator logos as theme-aware SVGs; simplify both READMEs for hobbyist users with language flags, centered HA/HACS badges and a collapsible contents list.
- Redesign the English and Polish READMEs with LINAK branding, matching navigation, feature tables and one shared installation/configuration path per language.
- Add an unregistered movement research controller with explicit centimeter conversion, measured travel limits, bounded I/O, Stop on completion/cancellation, progress checks and simulated failure tests. The controller now also supports the native HA entities described in 0.1.0a7.
- Adopt the playbook Tier 2 maintenance baseline and document the native-control contract.
- Package the supplied LINAK icon and logo as local HA brand images, with provenance and trademark notices.

### Adopter action

- Update Home Assistant to 2026.10.4 or newer before installing this alpha.
- **Safer dependency downloads:** Update the lock generator and HA test stack to remove vulnerable uv certificate stores (GHSA-hq85-5cpj-mr62).
- **Visible test reports:** Codecov and Sonar receive integration coverage and test results separately from required CI checks.
- **Predictable validation:** CI uses hashed dependency files and checks that updates keep the Home Assistant test stack consistent.
- **Reviewed maintenance:** Dependency proposals respect HA-owned versions, and workflow/documentation checks protect future changes.

## 0.1.0a7 (unpublished alpha)

- Recheck the desk on range submission and keep disconnected readings unavailable during control cleanup; test stalled feedback and both connections during range reload.
- Add a native centimeter height slider, Stop and go-to-memory buttons, with English/Polish labels and action errors.
- Collect measured command bounds during onboarding and support range changes through Options Flow; controls are registered by default. No target is restored or sent on setup/reconnect.
- Reserve the shared BLE session across fresh offset/memory reads, movement, feedback and final Stop; reject concurrent targets, yield polling and stop/disconnect on interruption or unload.
- Validate characteristic operations, retain the bounded motion guards and expose software control outcomes in redacted diagnostics. Physical movement/Stop verification remains pending.

### Adopter action

- Update via HACS and restart HA. For an existing entry, set measured centimeter bounds once in LINAK configuration. New onboarding includes the range. Follow [the supervised HA test](docs/controls.md) before using automations. Offset/memory/reminder writes are not included.

## 0.1.0a6: unpublished alpha

- Show the native desk name with a short address suffix on discovery cards, using the same naming helper as HA Idasen and removing the repeated LINAK prefix.
- Resolve cached discovery/device names consistently for cards, selection and entry titles; generic LINAK/address fallbacks do not hide native names.
- Read optional standard GAP Device Name after pairing when cached naming is unavailable, and improve an existing fallback device name without changing user device names, existing LINAK entry titles, entity IDs or bonds.

### Adopter action

- Redownload and restart HA. Keep the existing integration and pairing; the device name can improve during setup. A discovery card can still use LINAK plus a short suffix until a native name is available. Physical naming behavior needs validation.

## 0.1.0a5: unpublished alpha

- Show stored heights and reminder profiles as regular desk sensors; retain height offset as a diagnostic parameter without changing existing entity IDs.
- Add a diagnostic connection binary sensor and optional, default-disabled Bluetooth signal-strength and backend sensors using HA-managed data only. Recheck enabled RSSI availability every 60 seconds even during repeated connection failures.
- Add the Bluetooth address to local device information; keep downloaded diagnostics free of names, addresses and adapter identifiers.

### Adopter action

- Redownload and restart HA. Enable optional Bluetooth sensors in the entity registry when needed; no new pairing, bond reset or desk setting write is required. Automatic first pairing from 0.1.0a4 still needs hardware validation.

## 0.1.0a4: unpublished alpha

- Provide a temporary, device-restricted BlueZ agent for local Just Works pairing, using the same application connection for registration and pairing. Reuse existing bonds; retain backend pairing for proxies.
- Report unavailable local pairing-agent infrastructure separately from rejected authentication.
- Suppress incomplete height notifications before initial setup is ready, while retaining unavailable-state notifications after invalid readings or link loss.

### Adopter action

- Redownload and restart HA to load the updated integration. The new automatic first-pairing path still requires a supervised Raspberry Pi test; keep an existing working bond. No movement or panel setting writes are enabled.

## 0.1.0a3: unpublished alpha

- Pair through the selected Bluetooth backend before subscribing; let CoreBluetooth manage authentication automatically.
- Distinguish authentication failure, pairing timeout, unsupported pairing and lost connections in English and Polish setup errors.
- Interrupt pending BLE operations on link loss and drain transport cleanup through repeated cancellation.
- Wait for HA-managed local/proxy adapters before setup. No panel user-ID writes or movement are enabled.

### Adopter action

- Redownload the integration and restart HA, then retry with pairing enabled on the panel. Raspberry Pi and proxy validation of this change is still required.

## 0.1.0a2: unpublished alpha

- Add native HA progress, translated validation failures and retry for desk onboarding.
- Bound complete connection/read attempts and individual notification/position operations; release connections after failure or flow cancellation.
- Select the current connectable device through HA's Bluetooth manager and pass an adapter-update callback to the connector.
- Test slow/failed setup, progress revisits, retry, cancellation and HA setup-retry behavior. Real Raspberry Pi onboarding remains unverified.

### Adopter action

- Redownload/update the custom integration and restart HA. Cancel an old pending setup before trying again. If it still fails, report the setup-stage warning and HA version with private identifiers removed.

## 0.1.0a1: unpublished local alpha

- Add native Home Assistant UI configuration and Bluetooth discovery.
- Validate extended reads before creating a config entry.
- Add actual height in centimeters, offset, stored positions and reminder profiles.
- Share one asynchronous BLE connection, serialize queries and reconnect after failed reads.
- Add English/Polish translations and diagnostics omitting device identifiers.
- Add captured DPG1C protocol fixtures and real Home Assistant tests with simulated Bluetooth.

Hardware movement, setting changes, Raspberry Pi operation and HACS publication are not yet validated.
