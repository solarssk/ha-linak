# Brand assets

The maintainer supplied the LINAK icon and horizontal logo used in
`custom_components/ha_linak/brand/`. These identify the hardware manufacturer;
the integration is an independent community project, not an official LINAK or
IKEA integration. LINAK names and artwork remain the property of their respective
owners and are excluded from the repository's MIT code license. Supplying an
image does not establish a redistribution license or manufacturer endorsement.

The supplied icon is 256 × 256 pixels. `icon@2x.png` is a 512 × 512 resampling,
not an additional high-resolution original. The horizontal WebP source was
converted to PNG, trimmed and resized proportionally to heights of 256 and
512 pixels. Its white background is preserved so the black lettering remains
readable in dark themes. No altered-color brand variant is invented.

Home Assistant supports local `brand/` assets since 2026.3. The dimensions and
filenames follow its [integration image requirements](https://contributors.home-assistant.io/core/integrations/brands/).
These images improve identification; they do not confer HACS default-catalog
acceptance or a Home Assistant quality-scale award.


## README vector logos

The maintainer additionally supplied `LINAK logo A_2colour.ai` and
`LINAK logo A_neg.ai`, identified as official LINAK artwork. Both contain
PDF-compatible vector paths, including the original tagline. Poppler exported
those paths to the two SVGs in `docs/assets/`; the README uses a `picture` element
with dark/light sources and a light fallback. The same source drawing, colors
and lettering are preserved. The negative version's surrounding dark rectangle
was removed and the page bounds were cropped to the artwork, producing a
transparent background. Both exports share a view box to avoid layout shifts.
They contain paths only, without scripts, external resources or embedded fonts.

These SVGs replace the earlier raster logo in the READMEs. The local HA PNG
assets retain the provenance documented above. GitHub theme selection follows its
[supported picture markup](https://github.blog/changelog/2022-08-15-specify-theme-context-for-images-in-markdown-ga/).
