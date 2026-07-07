# PPTX-First Native Delivery

Use this reference only after the content plan is confirmed, unless the user
explicitly requested a no-confirmation PPTX-native build. The goal is a strong,
editable, visually reliable `.pptx`.

## Decision Rule

Use `pptx-native` for all builds: first confirm the content plan, then produce
the formal PPTX with native editable objects. `pptx-native` is required when any
of these are true:

- The user says the final goal is a beautiful or usable PPTX.
- The deck contains service loops, roadmaps, process flows, scenario matrices, value cards, or other visuals that need deliberate native PPTX composition.
- The deck should be client-facing, reusable, or suitable for repeated editing.

If the user explicitly requests no-confirmation generation or a quick structural
check, still generate PPTX-native output and document the assumptions.

## Visual Source Of Truth

Native PPTX is the visual source. PDF/PNG renders exist only for QA and review.

## Authoring Pattern

After confirmation and before drawing slides:

1. Keep a content source: Slide IR, outline JSON, or a concise source brief.
2. Rewrite visible slide copy for presentation use: shorter titles, fewer bullets, one message per slide.
3. Define a small design system: colors, typography, margins, card styles, footer, dividers, and number badges.
4. Choose 4-6 reusable native constructs such as card, metric card, process node, pill, connector, and footer.
5. Build the PPTX directly with native text, shapes, lines, tables, and simple charts. Do not make full-slide screenshots.

Use PptxGenJS for the full PPTX authoring chain with:

- Fixed 16:9 layout.
- A token object for colors and spacing.
- Shared helpers for title, footer, cards, chips, metric cards, process nodes, and connectors.
- Text boxes sized for expected Chinese/English wrapping.
- `fit: "shrink"` only as a guardrail, not as the main density strategy.

Use PptxGenJS `addImage` for SVG assets. Encode the localized SVG as base64
image data and pass it through the `data` option:

```js
const svg = fs.readFileSync(svgPath, "utf8");
const data = `data:image/svg+xml;base64,${Buffer.from(svg, "utf8").toString("base64")}`;
slide.addImage({ data, x, y, w, h });
```

Use this for localized Lucide icons and SVG illustrations. Keep the original SVG
under the deck workspace `assets/` directory and record its source metadata in
Slide IR and `assets/ATTRIBUTIONS.md`.

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
2. Run the bundled PPTX QA helper:

   ```bash
   python3 {SKILL_ROOT}/scripts/pptx_qa.py <deck.pptx> \
     --workspace <deck-workspace> \
     --render required
   ```

   The helper writes `qa/pptx-qa-report.json`, checks PPTX package structure, runs heuristic layout preflight in `pptx.layoutQa`, and renders with LibreOffice `soffice` only when it is already installed. It does not certify visual quality by itself.

3. Do not use WPS Office for headless conversion on macOS. Its `wpsoffice` binary starts the GUI and emits Qt/runtime noise instead of acting as a reliable converter.
4. Do not install LibreOffice, Poppler, or other render tools during final QA unless the user explicitly approves. First check whether the tool exists; if it is missing, report visual QA as blocked.
5. Treat structural QA as a separate result, not as visual QA. A valid ZIP package, slide count, and text extraction prove the PPTX is structurally readable; they do not prove layout, clipping, overlap, or rendering quality.
6. Read `pptx.layoutQa` in the report before manual inspection. Resolve or explicitly justify warnings for out-of-bounds content, edge-clipping risk, text overflow, body text below the minimum size, and large overlaps between content elements. Decorative off-canvas shapes may be intentional, but decorative shapes that cover text, cards, buttons, page numbers, charts, or footers are defects.
7. If `qa/pptx-qa-report.json` has `visualQa.status` of `rendered`, inspect the `visualQa.representativePages` PNG paths at full size. At minimum check cover, most text-dense slide, most visually dense slide, and closing slide; add process/architecture or scenario/value slides when those layouts exist.
8. Inspect fine-detail layout on rendered pages: text stays inside cards and callouts, cards align to a clear grid, buttons do not overlap footer/contact/page-number areas, icons and badges do not hide labels, charts/tables stay inside safe margins, connectors meet their nodes, and repeated elements have consistent spacing and alignment.
9. If the report has `visualQa.status` of `pdf-rendered`, inspect the PDF directly and disclose that PNG page screenshots were not produced.
10. If the report has `visualQa.status` of `blocked`, stop and state exactly which renderer dependency is missing. Offer the user a choice: approve installing LibreOffice/Poppler, open the PPTX manually and provide screenshots, or accept structural-only QA with the explicit limitation.
11. Verify no obvious clipping, overlap, broken connectors, tiny body text, missing labels, position drift, formatting disorder, or container overflow.
12. Inspect the `.pptx` package when editability matters. A PPTX-first native build should not rely on `ppt/media/*` full-slide images unless the fallback is intentional and documented.
13. Update `manifest.json` and `qa/qa-report.json` to reflect the actual delivery route, QA evidence, layout warnings, fixes, and any fallbacks.

The manual equivalent is headless `soffice` to PDF, then `pdftoppm` or PyMuPDF to PNG, plus PPTX XML geometry inspection. Prefer the helper because it avoids fragile inline shell quoting and writes a machine-readable report. The final QA judgment is still made by inspecting the rendered pages and resolving the layout preflight risks, not by trusting the script exit code alone.

## When To Fall Back

Use raster or image fallback only when:

- The visual cannot reasonably be represented with native PPTX objects.
- The user accepts lower editability.
- Key content remains available as native title, labels, or summary text.
