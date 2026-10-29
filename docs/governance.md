# Repository governance and validation

This personal hardware-research alpha follows Tier 1 of the [solarssk playbook](https://github.com/solarssk/playbook), with extra real-HA tests, type checking and packaging validation. Reassess before external installations depend on it or hardware movement is shipped. No official Home Assistant quality-scale award, HACS default-catalog acceptance, or earned OpenSSF rating is claimed.

CodeQL uses GitHub default setup. OpenSSF Scorecard runs in report-only mode; its result is not a certification.

Required checks after bootstrap: Quality, Tests, Hassfest, Dependency audit and Secret scan. HACS validation is monitored separately because it also queries external branding/catalog services. The maintainer merges pull requests. Required review count is zero while there is one maintainer. Force pushes and branch deletion on main are blocked.

Dependency audit checks direct runtime and tooling pins in requirements-audit.txt. It does not certify the pinned Home Assistant release or all of its transitive dependencies. The HA/test-plugin pair is upgraded together and tested, rather than independently by Dependabot.

No Codecov/Sonar project or token has been configured. Reports must not claim those services have analyzed this repository. CI runs are the evidence for passing checks; workflow files alone are not results.
