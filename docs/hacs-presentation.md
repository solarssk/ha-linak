# README presentation in HACS and GitHub

Reviewed 2026-10-31. This reference is for maintainers updating the product pages. The goal is a readable desk-integration page in HACS while retaining the accepted GitHub layout. The two renderers need separate source files.

## Official documentation and implementation

The [official HACS publishing guide](https://www.hacs.xyz/docs/publish/start/#readme) requires a README explaining use. It also defines the HACS display name in `hacs.json` and says GitHub's repository description appears in HACS. It does not supply a complete GitHub-Markdown compatibility matrix. The renderer behavior below is established from the source, rather than from old `info.md` tutorials.

| Source | Inspected revision | What it establishes |
| --- | --- | --- |
| [HACS backend](https://github.com/hacs/integration/blob/a15e87ec0d1c82e58f1ddbaf17669d3eaa261eb8/custom_components/hacs/repositories/base.py) | `a15e87e` | Root README filename selection, version selection and download |
| [HACS repository view](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/dashboards/hacs-repository-dashboard.ts) | `d97dce0` | Passes transformed README text to `ha-markdown` |
| [HACS Markdown transformation](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/tools/markdown.ts) | `d97dce0` | Regex-based conversion of relative links and assets |
| [HA Markdown element bundled by HACS](https://github.com/home-assistant/frontend/blob/3ffbd435e0e5cf23872057187f3da53bb62441a2/src/components/ha-markdown-element.ts) | `3ffbd43` | GFM parsing and HTML sanitization through the Markdown worker |
| [HA Markdown styles bundled by HACS](https://github.com/home-assistant/frontend/blob/3ffbd435e0e5cf23872057187f3da53bb62441a2/src/components/ha-markdown.ts) | `3ffbd43` | Image sizing and text styling; this revision has no table-specific spacing/border rules |
| [HA Markdown worker](https://github.com/home-assistant/frontend/blob/3ffbd435e0e5cf23872057187f3da53bb62441a2/src/resources/markdown-worker.ts) | `3ffbd43` | `marked` plus `xss`, with a restricted HTML whitelist |

HACS's frontend pins the HA frontend revision shown above. The host HA version and registered components can also affect styling, so these source snapshots are not a promise about every installed frontend.

## File routing and versions

| Surface | English | Polish | Presentation |
| --- | --- | --- | --- |
| GitHub landing page | `.github/README.md` | `.github/README.pl.md` | Centered header/badges, theme-aware official logos, contents and entity tables |
| HACS product description | `README.md` | `README.pl.md` through its language link | Native Markdown, portable logo, headings and categorized entity lists |

[GitHub's README precedence](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) selects `.github` before the root. HACS downloads root README filename variants instead. Opening the root file explicitly on GitHub still shows the HACS document.

For an installed repository, HACS's documentation loader selects its installed version/commit. Before installation it selects the available version. The link transformer can use the available version for relative assets. An older installed README can therefore remain visible after a repository merge; refreshing the browser does not install newer files. Update the integration through HACS, restart HA for integration changes, then reopen its description. No published release is currently required because this repository uses its default branch.

A reported screenshot showed installed ref `2563810`, whose README predates the native slider. That explains its old read-only text; it is separate from the rendering defects. Old `info.md`/`render_readme` advice does not select a second document in this loader; see [HACS's documentation issue](https://github.com/hacs/integration/issues/3994).

## Compatible Markdown choices

Keep the HACS description complete: explain the supported desk panel, controls/readings, requirements, setup, troubleshooting and validation status. Preserve the Sensors, Diagnostics and Controls grouping. Do not replace it with a short installation stub.

Use Markdown headings, paragraphs, lists and external images. Tables are parsed, but their spacing/borders can differ from GitHub; the HACS entity groups use lists to stay readable on narrow screens and older styles. Keep merged HTML tables, `picture`/`source` theme switching and centered layouts in the GitHub files. Avoid inline SVG and unverified custom HTML in the HACS roots.

The official neutral-background logo identifies the manufacturer. The generated dashboard illustration is no longer embedded: it could suggest an included card or a screenshot of the integration. Its legacy asset files remain for older README versions and must not be presented as the current interface. A future product screenshot must show the actual HA entities and remove private identifiers.

## Nested badge-link defect

HACS's relative-link regex can match an entire nested image link, then replace its first opening parenthesis. For the old Home Assistant badge, the relative outer destination `hacs.json` caused the external image URL to become a repository-relative path containing `/https://img.shields.io/`. The Shields image itself returned a valid SVG; the rewritten URL was wrong.

Use an absolute outer destination for every linked badge in the HACS roots. The Home Assistant badge now points to `https://www.home-assistant.io/`. Keep the minimum-version text synchronized with `hacs.json`. The actual HACS transformer was run against both versions: the old markup reproduced the corrupt image URL and the corrected markup preserved the external image URL.

## Name and catalog icon

`hacs.json`, the HA manifest and the English UI title use **LINAK Desks**. The Polish UI title is **Biurka LINAK**. The supported product is a height-adjustable desk with a DPG1C panel; the LINAK manufacturer logo alone does not define that scope. The repository name and integration domain remain `ha-linak` and `ha_linak`; existing device/entity identifiers and user device names are unchanged.

The catalog row's missing icon is independent of README images. This HACS frontend's [brand URL helper](https://github.com/home-assistant/frontend/blob/3ffbd435e0e5cf23872057187f3da53bb62441a2/src/util/brands-url.ts) uses the public brands CDN, while this integration ships local `brand/` assets. The public `ha_linak` fallback currently returns the placeholder. HACS's maintainer [confirmed the upstream issue and a fix in Marketplace 2026.11](https://github.com/hacs/integration/issues/5223#issuecomment-6222989180). Do not add unsupported icon settings, change the domain or claim that a README edit fixes that catalog icon.

## Review and rendering checks

Run the repository metadata check for all four files, including local links and the GitHub/HACS markup boundaries. For a HACS presentation change, also:

1. Run the pinned HACS URL transformer over the root Markdown and inspect every image URL, including nested badge links.
2. Render with the inspected HA worker's `marked`/`xss` pipeline and GFM options. Its pinned package versions are `marked` 15.0.4 and `xss` 1.0.15.
3. Check English/Polish output, light/dark themes and a narrow viewport. Verify that images load and content does not overflow horizontally.
4. Inspect the GitHub diff separately and preserve its accepted layout.
5. After merge and HACS update, check the installed HACS page. A local source-pipeline preview reproduces parsing and sanitization, but its page shell is not a live HA installation.

The 2026-10-31 local preview passed these parser/image checks in both languages and themes, including a 390-pixel-wide viewport. The five images (official logo and four badges) loaded in each desktop preview. No live HA configuration was changed.
