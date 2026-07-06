# PPTX-First Native Delivery

Use this reference when the user prioritizes PPTX quality, polished customer-facing slides, high-design PPTX, or says HTML is not needed. The goal is a strong `.pptx`, not HTML/PPTX parity.

## Decision Rule

Use `pptx-first` when any of these are true:

- The user says the final goal is a beautiful or usable PPTX.
- The user complains that HTML and PPTX differ and asks to prioritize PPTX.
- The deck contains service loops, roadmaps, process flows, scenario matrices, value cards, or other visuals where the default PPTX exporter would flatten the design into basic text boxes.
- The user does not need HTML/PDF as independent deliverables.

Do not use `pptx-first` only because a deck is visually important. If HTML/PDF is the primary output, keep the HTML route and disclose PPTX editability/fidelity tradeoffs.

## Visual Source Of Truth

Pick one visual source:

- **PPTX-first**: native PPTX is the visual source. HTML can be omitted or generated later from PPTX renders only as a preview.
- **HTML-first**: HTML is the visual source. PPTX may be less editable or may require raster fallbacks if the user accepts that.

Never promise that the default HTML renderer and default PPTX exporter will match. They are separate renderers.

## Authoring Pattern

Before drawing slides:

1. Keep a content source: Slide IR, outline JSON, or a concise source brief.
2. Rewrite visible slide copy for presentation use: shorter titles, fewer bullets, one message per slide.
3. Define a small design system: colors, typography, margins, card styles, footer, dividers, and number badges.
4. Choose 4-6 reusable native constructs such as card, metric card, process node, pill, connector, and footer.
5. Build the PPTX directly with native text, shapes, lines, tables, and simple charts. Do not make full-slide screenshots.

For `pptxgenjs`, use a reusable helper module or deck-local script with:

- Fixed 16:9 layout.
- A token object for colors and spacing.
- Shared helpers for title, footer, cards, chips, metric cards, process nodes, and connectors.
- Text boxes sized for expected Chinese/English wrapping.
- `fit: "shrink"` only as a guardrail, not as the main density strategy.

## Content And Design Rules

- Prefer direct claims over section labels.
- Shorten copy before lowering font size.
- Avoid repeated same-shape card grids across every slide; vary cover, matrix, loop, process, and summary structures.
- Use native connectors behind nodes in process and loop diagrams.
- Use decorative shapes only where they support hierarchy; they must not carry critical meaning.
- Keep core text and data editable wherever possible.
- If a complex visual area must be rasterized, keep key labels and numbers as native text and record the fallback.

## QA Checklist

Run these checks before delivery:

1. Confirm the PPTX slide count matches the requested page limit.
2. Run `slides_test.py <deck.pptx>` with a Python environment that has the required packages, if available.
3. Render the PPTX with headless `soffice`.

   Use a temporary profile outside the committed source tree, or under the deck workspace cache. The `UserInstallation` path is only the office runtime profile; the generated PDF is written to `<preview-dir>`.

   ```bash
   soffice -env:UserInstallation=file://<temp-or-cache-profile-dir> \
     --headless --convert-to pdf --outdir <preview-dir> <deck.pptx>
   ```

4. Render the PDF to PNG pages:

   ```bash
   pdftoppm -png -r 140 <preview.pdf> <preview-dir>/page
   ```

5. Inspect representative slides at full size: cover, most text-dense slide, process/architecture slide, scenario/value slide, and closing slide.
6. Verify no obvious clipping, overlap, broken connectors, tiny body text, or missing labels.
7. Inspect the `.pptx` package when editability matters. A PPTX-first native build should not rely on `ppt/media/*` full-slide images unless the fallback is intentional and documented.
8. Update `manifest.json` and `qa/qa-report.json` to reflect the actual delivery route. If HTML is not maintained, set expectations clearly.

## When To Fall Back

Use the default DeckSmith CLI exporter instead of native PPTX when:

- The user wants fast draft slides or an HTML preview.
- The layout is simple and editability matters more than design polish.
- The deck must be generated only from registered Theme, Template, Layout, and Component abstractions.

Use raster or image fallback only when:

- The visual cannot reasonably be represented with native PPTX objects.
- The user accepts lower editability.
- Key content remains available as native title, labels, or summary text.
