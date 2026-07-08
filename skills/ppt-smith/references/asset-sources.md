# Asset Source Guidance

Use this reference after content confirmation when choosing icons or external
illustrations for a PPTX-native deck. During planning, mention the intended
asset direction only at the level of style and licensing assumptions.

## Default Icon Source

Use Lucide as the default icon source for PptSmith:

- Source name: `Lucide`
- Recommended format: SVG localized under `assets/icons/`
- Typical Slide IR asset type: `icon` or `svg`
- License label: `ISC`

Prefer a small, consistent set of Lucide icons per deck. Match stroke weight,
color, and size to the active theme. If an icon does not add meaning, remove it.
If Lucide does not have a suitable icon, use a native PPT shape or a numbered
marker instead of mixing icon libraries.

When rendering Lucide SVGs into PPTX, use PptxGenJS `addImage` with base64 SVG
image data.

## Optional Illustration Source

Use unDraw when a localized illustration fits the slide message, audience, tone,
and evidence needs.

- Source name: `unDraw`
- Recommended format: SVG or PNG localized under `assets/images/`
- Typical Slide IR asset type: `image` or `svg`
- License label: `unDraw License`

When using unDraw SVG assets, insert them through PptxGenJS `addImage` with
base64 SVG image data. PNG assets can use normal image paths.

Do not use unDraw as a filler image source. The illustration should support a
specific message, not replace evidence, product screenshots, charts, or concrete
examples.

## Provenance Records

For every third-party visual asset, include metadata in Slide IR `assets[]` when
known:

```json
{
  "id": "icon-check-circle",
  "type": "icon",
  "path": "assets/icons/check-circle.svg",
  "mimeType": "image/svg+xml",
  "source": "Lucide",
  "sourceUrl": "https://lucide.dev/icons/check-circle",
  "license": "ISC",
  "attributionRequired": false
}
```

Also add a compact line to `assets/ATTRIBUTIONS.md` for each external source or
asset family used in the deck.
