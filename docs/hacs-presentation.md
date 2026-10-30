# README presentation in HACS

Reviewed 2026-10-30. The root README is the product page for people browsing from
Home Assistant, as well as the GitHub entry point. Keep it useful on its own:
benefits, example values, real entities, requirements, setup, support and honest
validation limits. Move developer detail into linked documents rather than turning
the root page into a badge wall or an abbreviated installation stub.

## What HACS actually uses

The current [integration README loader](https://github.com/hacs/integration/blob/a15e87ec0d1c82e58f1ddbaf17669d3eaa261eb8/custom_components/hacs/repositories/base.py)
searches README filename variants and fetches the selected document. It does not
choose info.md. Older documentation about info.md/render_readme is not a reliable
HACS 2.x solution. This behavior is also discussed in [upstream issue 3994](https://github.com/hacs/integration/issues/3994).

The [HACS repository view](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/dashboards/hacs-repository-dashboard.ts)
passes the description to HA's ha-markdown component. Its [URL transformer](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/tools/markdown.ts)
rewrites Markdown image/document paths using repository and version context. It
does not rewrite relative src/srcset attributes in picture HTML. GitHub's theme
picture markup therefore cannot be assumed to behave the same in HACS.

## Shared product page

- Use native Markdown headings, short paragraphs, lists, images and links.
- Use one official logo on a neutral background, with intrinsic width, so both
  HA themes can read it without picture/source markup.
- Label illustrative sensor values as examples. They are not a screenshot of a
  working hardware installation, editable controls or a claim of completed tests.
- Keep language flags visible. HACS displays the root English README; the Polish
  link opens the Polish document, rather than changing HA's interface language.
- Prefer a small HA/HACS/CI/license badge row. Other quality signals remain linked
  from the detailed guides. Do not claim catalog inclusion or an official award.
- Keep unsupported motion features visibly separate from available read sensors.
- Put the full theme-aware GitHub presentation and entity reference in guide.md
  and guide.pl.md. Keep their relative links correct after moving them.

The repository metadata check rejects the root HTML constructs that previously
broke presentation and checks local Markdown link/image targets. It does not
certify visual rendering on the user's HACS version.

## Validation boundaries

Local visual previews use Markdown rendering and HA-inspired light/dark/mobile
styling. They verify layout and local image loading, not a running HACS instance.
The actual HA/HACS view still needs checking after merge/refresh. No live Home
Assistant configuration is changed for this documentation work.
