# Documentation guide

This folder explains how to use, diagnose and develop LINAK Desks. You do not need to read every file. Start with the task below; the detailed references exist so protocol findings, hardware evidence and implementation decisions remain traceable.

## Start here

- **Install the integration:** [English user guide](../.github/README.md) or [Polish user guide](../.github/README.pl.md).
- **Connection fails or entities become unavailable:** [Onboarding](onboarding.md), then [diagnostics](diagnostics.md).
- **Test the slider, Stop or saved-position buttons:** [Control guide](controls.md).
- **Check what actually worked on hardware:** [Hardware results](hardware-results.md). Passing software tests alone do not establish hardware behavior.
- **See what comes next:** [Roadmap](roadmap.md).

Technical documentation is in English. User guides and the HA interface also have Polish translations.

## Using and troubleshooting the integration

| Document | What it answers |
| --- | --- |
| [Onboarding](onboarding.md) | How discovery, connection, authentication, retry and setup errors work |
| [Diagnostics](diagnostics.md) | What diagnostic entities and downloads contain, freshness limits and privacy |
| [Controls](controls.md) | How to configure and test native height, Stop and saved-position controls |
| [Hardware results](hardware-results.md) | Which observations came from a physical desk and what still needs verification |

## Understanding or changing the implementation

| Document | What it answers |
| --- | --- |
| [Architecture](architecture.md) | How HA entities, shared state and the BLE session fit together |
| [Protocol](protocol.md) | Which messages we decode, how replies are validated and what the evidence establishes |
| [Movement](movement.md) | How command ownership, deadlines, feedback and Stop cleanup work |
| [Settings reference](settings-reference.md) | Which panel settings are known, their sources and the protected calibration design |
| [Communication review](communication-review.md) | What existing IKEA/DPG libraries already provide and where our behavior differs |

Read [Contributing](../CONTRIBUTING.md) before changing code. Agents also follow [AGENTS.md](../AGENTS.md).

## Research and experiments

| Document | Why it is separate |
| --- | --- |
| [Bluetooth investigation](bluetooth-research.md) | Compares authentication and connection implementations and records unresolved questions |
| [Standalone movement test](movement-test.md) | Describes a separate supervised protocol experiment; ordinary HA testing uses the control guide |

Research candidates are not implemented features. Hardware results record observations; they do not replace protocol or architecture references. Keep private captures and identifiers out of public documentation.

## Maintenance and presentation

| Document | What it covers |
| --- | --- |
| [Roadmap](roadmap.md) | Implementation sequence and remaining work |
| [Governance](governance.md) | CI, dependency handling, repository policy and release boundaries |
| [Branding](branding.md) | Official artwork provenance, naming and asset use |
| [HACS presentation](hacs-presentation.md) | Why HACS and GitHub have separate READMEs and how their rendering is checked |

The [assets folder](assets/) contains documentation artwork. Some legacy illustrations remain only so older installed README versions retain working image links.

## Keeping this folder useful

Update the document that owns a fact instead of copying its full explanation into several files. User guides describe available behavior; technical references explain implementation and evidence; the roadmap tracks unfinished work. When adding, renaming or removing a document, update this index and its incoming links in the same change.
