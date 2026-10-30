# Changelog

## Unreleased

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

- Add an unregistered movement research controller with explicit centimeter conversion, measured travel limits, bounded I/O, Stop on completion/cancellation, progress checks and simulated failure tests. Installed HA behavior remains read-only pending supervised hardware validation.
- Adopt the playbook Tier 2 maintenance baseline and document the native-control contract.
- Package the supplied LINAK icon and logo as local HA brand images, with provenance and trademark notices.

### Adopter action

- Update Home Assistant to 2026.10.4 or newer before installing this alpha.

- **Safer dependency downloads:** Update the lock generator and HA test stack to remove vulnerable uv certificate stores (GHSA-hq85-5cpj-mr62).

- **Visible test reports:** Codecov and Sonar receive integration coverage and test results separately from required CI checks.

- **Predictable validation:** CI uses hashed dependency files and checks that updates keep the Home Assistant test stack consistent.
- **Reviewed maintenance:** Dependency proposals respect HA-owned versions, and workflow/documentation checks protect future changes.

## 0.1.0a2 — unpublished alpha

- Add native HA progress, translated validation failures and retry for desk onboarding.
- Bound complete connection/read attempts and individual notification/position operations; release connections after failure or flow cancellation.
- Select the current connectable device through HA's Bluetooth manager and pass an adapter-update callback to the connector.
- Test slow/failed setup, progress revisits, retry, cancellation and HA setup-retry behavior. Real Raspberry Pi onboarding remains unverified.

### Adopter action

- Redownload/update the custom integration and restart HA. Cancel an old pending setup before trying again. If it still fails, report the setup-stage warning and HA version with private identifiers removed.

## 0.1.0a1 — unpublished local alpha

- Add native Home Assistant UI configuration and Bluetooth discovery.
- Validate extended reads before creating a config entry.
- Add actual height in centimeters, offset, stored positions and reminder profiles.
- Share one asynchronous BLE connection, serialize queries and reconnect after failed reads.
- Add English/Polish translations and diagnostics omitting device identifiers.
- Add captured DPG1C protocol fixtures and real Home Assistant tests with simulated Bluetooth.

Hardware movement, setting changes, Raspberry Pi operation and HACS publication are not yet validated.
