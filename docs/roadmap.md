# Implementation plan

1. Completed: seven extended DPG1C reads on real hardware, strict protocol parsing, native HA discovery/configuration, centimeter sensors, lifecycle and simulated-BLE tests on HA 2026.10.4. Raspberry Pi reads/reconnect after manual pairing and owner-confirmed restart recovery are recorded; automatic unbonded first pairing and proxy validation remain open.
2. Implemented: [native centimeter slider, Stop and stored-position buttons](controls.md), with measured bounds, exclusive session ownership, bounded I/O and simulated HA/failure/cancellation tests. Onboarding collects the desk range; existing installations can set it in Configure.
3. Next: supervised short movements and Stop tests on DPG1C, including loss of feedback/connection. Record evidence before recommending unattended automations.
4. Validate the native controls on Raspberry Pi, including translated action errors, physical stopping, shutdown/unload and reconnect without resuming.
5. Device settings: follow the [settings/configuration reference](settings-reference.md), including a protected offset-calibration flow, post-install options/reconfiguration, verified memory/reminder writes, preservation of unrelated bits and readback. Design the configuration model alongside movement controls.
6. First external alpha: hardware results, versioned GitHub Release, HACS installation verification and release milestone. No default-catalog or official quality-scale acceptance is claimed.

The project adopts the playbook Tier 2 baseline. HACS is the distribution method; Home Assistant runs directly on the Raspberry Pi, without a Mac bridge.
