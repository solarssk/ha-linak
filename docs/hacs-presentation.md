# README and brand presentation in Marketplace and GitHub

HA 2026.11 introduces the built-in Marketplace, replacing the separate HACS installation and migrating existing repositories and downloads. This integration supports HA 2026.11.0 or newer. The root product README, GitHub landing page and HA brand routes are separate surfaces; fixing one does not replace the others.

## Official documentation and implementation

| Source | Contract |
| --- | --- |
| [HA 2026.11 release notes](https://www.home-assistant.io/blog/2026/11/04/release-202611/#welcome-to-the-marketplace) | Built-in Marketplace, HACS migration and custom repositories through Settings > Marketplace > Add from link |
| [Marketplace integration guide](https://contributors.home-assistant.io/marketplace/guides/integrations/) | Repository structure, local `brand/`, catalog/release image ingestion and first-install versus update restart behavior |
| [HA brand requirements](https://contributors.home-assistant.io/core/integrations/brands/) | Image names, sizes and custom integration assets |
| [HA 2026.11.0 brand handlers](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/brands/__init__.py) and [fallback constants](https://github.com/home-assistant/core/blob/2026.11.0/homeassistant/components/brands/const.py) | Authenticated local-first integration and Marketplace routes and exact fallback order |
| [Repository metadata reference](https://contributors.home-assistant.io/marketplace/reference/hacs-json/) | `homeassistant` declares the minimum; its version comparison applies to repositories with releases |

The public repository URL is `https://github.com/solarssk/ha-linak`. Adding it from a link requires connecting GitHub when prompted; it does not mean this repository has been accepted into the default catalog. The first Marketplace install of this config-flow integration can load without a restart. Updating an already loaded integration still requires a restart. Manual copying retains the restart procedure in the user guides.

## File routing and versions

| Surface | English | Polish | Presentation |
| --- | --- | --- | --- |
| GitHub landing page | `.github/README.md` | `.github/README.pl.md` | Centered header/badges, theme-aware official logos, contents and entity tables |
| Marketplace/legacy HACS product description | `README.md` | `README.pl.md` through its language link | Native Markdown, portable logo, headings and categorized entity lists |
| Installed HA and Marketplace brand images | `custom_components/ha_linak/brand/` | Same manufacturer assets | Local PNG icon/logo and HA fallbacks, independent of README markup |

[GitHub's README precedence](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) selects `.github` before the root. The product README remains at the root for Marketplace/HACS discovery. Opening that file explicitly on GitHub still shows the product document.

An older installed revision can retain older files. Compare the installed revision with the intended source before changing markup. Refreshing a browser does not install an integration update. Neither `info.md` nor `render_readme` is a solution for the current root README contract.

## Compatible Markdown choices

Keep the product description complete: supported desk panel, controls/readings, requirements, setup, troubleshooting and validation limits. Preserve the Sensors, Diagnostics and Controls grouping. Keep the existing native Markdown headings, paragraphs, lists, external images and compact supported-device table. The categorized entity lists stay readable on narrow screens.

Keep merged HTML entity tables, `picture`/`source` theme switching and centered layouts in the GitHub files. Avoid inline SVG and unverified custom HTML in the roots. The neutral-background logo identifies the manufacturer in both themes. Do not replace it with a generated dashboard illustration that could suggest an included card or actual screenshot. A future screenshot must show real HA entities and remove private identifiers.

Use an absolute outer destination for every linked badge in the roots. Earlier HACS relative-link rewriting corrupted a nested badge whose outer destination was `hacs.json`, turning the image URL into a repository-relative path containing `/https://img.shields.io/`. Keep minimum-version text and badges synchronized with `hacs.json`; a valid Shields response alone is not proof of correct rendering.

## Name and catalog icon

`hacs.json`, the HA manifest and both UI titles use **LINAK**. The supported product is a height-adjustable desk with a DPG1C panel. The repository name and integration domain remain `ha-linak` and `ha_linak`; device/entity identifiers and user device names are unchanged.

The catalog icon is independent of the README logo. HA 2026.11.0 serves both brand surfaces through its backend:

| Authenticated route | First source | Subsequent cache/CDN paths |
| --- | --- | --- |
| `/api/brands/integration/ha_linak/{image}` | Discovered custom integration's `brand/` files | `brands/ha_linak/{image}` |
| `/api/brands/marketplace/ha_linak/{image}` | Same local files | `ha_linak/{image}`, then `marketplace/ha_linak/{image}` |

Requests need an authenticated HA session or a current brands access token. Supported image names are `icon.png`, `logo.png`, their `@2x` versions and each corresponding `dark_` name. The integration ships four light PNGs; HA resolves dark requests to their light equivalents. Standard-resolution/icon fallbacks cover missing higher-resolution/logo files. Exact dimensions and provenance belong to [the asset reference](branding.md).

Local brand discovery does not require successful config-entry setup or a desk connection. Deterministic tests discover the real integration directory and call both real view handlers with in-memory requests. They compare response bytes against the shipped files with and without `placeholder=no`, exercise session/query-token authentication and reject any cache/CDN or placeholder path. Socket/DNS guards remain enabled. This verifies the backend source and fallback contract, not the running frontend's rendering or a production API.

Before installation, local files are not present. The official guide says the brands site collects assets from the latest release of each integration in the catalog. This repository has neither a published release nor confirmed catalog acceptance at this update. A custom-link installation can supply the files for installed views, but a pre-installation icon is not guaranteed. Raising the minimum or editing a README does not populate the CDN. An HTTP 200 response could be a placeholder; image bytes and source paths matter.

The earlier HACS [missing-icon report](https://github.com/hacs/integration/issues/5223#issuecomment-6222989180) records the maintainer's fix in Marketplace 2026.11. Its older frontend CDN URL helper is historical evidence, not the current HA contract. Do not add unsupported manifest/icon settings or rename the domain.

## Review and rendering checks

1. Run the repository metadata check over all four READMEs, local links and the GitHub/root markup boundaries.
2. Run the brand tests against the pinned real HA package. Confirm real PNG bytes, local paths, dark/high-resolution fallbacks and no CDN/placeholder access, not only status 200.
3. For layout or image changes, inspect both languages, light/dark themes and a narrow viewport. Preserve the GitHub layout separately.
4. Let the maintainer confirm the installed Marketplace and integration views. Simulated tests do not replace that frontend check. Never connect to a production HA instance as part of automated tests.

The previous root layout was checked with the HACS 2 source pipeline: [backend `a15e87e`](https://github.com/hacs/integration/blob/a15e87ec0d1c82e58f1ddbaf17669d3eaa261eb8/custom_components/hacs/repositories/base.py), [transformer `d97dce0`](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/tools/markdown.ts) and [HA Markdown worker `3ffbd43`](https://github.com/home-assistant/frontend/blob/3ffbd435e0e5cf23872057187f3da53bb62441a2/src/resources/markdown-worker.ts), with `marked` 15.0.4 and `xss` 1.0.15. English/Polish images loaded in both themes and at 390-pixel width. That is historical parsing/layout evidence, not a Marketplace 2026.11 visual pass.
