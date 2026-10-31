# Separate GitHub and HACS presentation

Reviewed 2026-10-30. The accepted GitHub presentation and the HACS product page serve different renderers. Keep both useful on their own; do not simplify the GitHub landing page as a side effect of repairing HACS.

## File routing

| Surface | English | Polish | Presentation |
| --- | --- | --- | --- |
| GitHub repository landing page | .github/README.md | .github/README.pl.md | Centered header/badges, theme-aware official logos, contents and merged entity table |
| HACS description | README.md | README.pl.md via language link | Full product description with native Markdown, portable images and sensor lists |

[GitHub's documented precedence](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) is .github, then repository root, then docs. The files in .github restore the previously accepted README content and layout, with only relative paths adjusted for the new directory. Their language switch stays within .github. Opening a root README file explicitly on GitHub still shows the HACS document; the automatic repository landing page uses .github/README.md.

The current [HACS README loader](https://github.com/hacs/integration/blob/a15e87ec0d1c82e58f1ddbaf17669d3eaa261eb8/custom_components/hacs/repositories/base.py) selects root README filename variants and downloads that exact raw path for the selected version. It does not use GitHub's preferred-README endpoint, nor choose .github/README.md or info.md. This gives independent presentation without a separate repository, a release-branch workaround, hidden content or conditional CSS.

## HACS renderer

The [HACS repository view](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/dashboards/hacs-repository-dashboard.ts) passes the description to HA's ha-markdown component. Its [URL transformer](https://github.com/hacs/frontend/blob/d97dce047de482e6993419aa898f2267cfb5a152/src/tools/markdown.ts) rewrites Markdown image/document paths, but not relative src/srcset attributes in picture HTML. Older info.md/render_readme documentation is not a solution for this loader; see [upstream discussion](https://github.com/hacs/integration/issues/3994).

The root product descriptions retain benefits, example values, everyday use, actual sensor names, requirements, setup, support and honest validation limits. They are not a reduced installation stub. Illustrations are labelled as examples, not screenshots of working hardware or available motion controls. HACS displays the English root document; its Polish link opens the Polish page rather than changing HA's interface language.

## Maintenance and checks

- Change the relevant surface deliberately; update both when shared product facts such as supported features, requirements or setup behavior change.
- Keep picture/source and merged HTML tables in the GitHub-facing files. Preserve their accepted layout unless a redesign is explicitly requested.
- Use native Markdown and a neutral-background official logo in the HACS files.
- Keep language switches within their own surface. Links from HACS to the full GitHub reference point to .github/README files.
- The metadata check validates all four files' local links/images, disallows the problematic HTML in the HACS roots, and guards the restored GitHub layout.

Local HACS previews use Markdown rendering and HA-inspired light/dark styling, with remote badges omitted. They are not a running HACS instance. Actual HACS rendering needs checking after merge/refresh. No live HA configuration is changed.
