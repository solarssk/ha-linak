# Remaining implementation and validation work

The integration implements native HA reads, configuration, protected calibration and explicit movement controls. This roadmap tracks the work needed to validate those controls and extend configuration; it does not replace the [hardware evidence](hardware-results.md).

| Priority | Work | Current state | Completion evidence |
| --- | --- | --- | --- |
| 1 | Full supervised target and Stop validation | Readiness activation and limited movement feedback observed; full travel unverified | Up/down arrival, physical Stop, bounds, lifecycle and recovery on Raspberry Pi |
| 2 | Connection/environment coverage | Local reads and scoped pairing evidence available | Fresh unbonded onboarding; local-only, proxy-only and mixed-path comparison |
| 3 | Settings/readiness persistence | Calibration write/readback and one reconnect observed | Agreed restart/power-cycle tests, without assuming active status persists |
| 4 | Settings freshness and traffic | Full 60-second refresh; no durable stale snapshot | Separate live telemetry from last-read settings and test reconciliation after panel edits/restart |
| 5 | Post-install configuration | HA name, preparation, calibration and measured bounds implemented | Supported connection/device reconfiguration without routine delete/re-add |
| 6 | Additional panel setters | Memory/reminder/unit candidates catalogued | Verified encoding, permissions, preserved bits, acknowledgement, readback and persistence |
| 7 | Versioned external alpha | HACS packaging and repository CI exist | Hardware evidence, release assets and installation verification for the published revision |

There is no verified automatic firmware-limit import, generic settings-write API, default HACS-catalog acceptance or HA quality-scale award. Runtime remains inside Home Assistant; a Mac bridge is not part of the deployment model.
