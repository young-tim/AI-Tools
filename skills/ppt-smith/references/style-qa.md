# Style QA

Use this reference for decks generated from a website, PPT, image, screenshot, or moodboard reference. Run it after standard PPTX QA.

## QA Outputs

Write `qa/style-qa-report.json` in the active deck workspace with:

```json
{
  "status": "passed | warning | failed",
  "referenceType": "website | ppt | image | mixed | none",
  "styleBrief": "input/style-brief.md",
  "referenceEvidence": "input/reference-evidence.json",
  "checks": [],
  "warnings": [],
  "fallbacks": []
}
```

Also summarize material warnings in the active deck workspace `manifest.json`.

## Checks

### Style Brief

- `style-brief` exists when a reference was provided.
- `reference-evidence` exists and shows that the actual website, PPT, image,
  screenshot, or moodboard was visually inspected.
- Website references are not assessed from text extraction alone.
- Reference type, reusable signals, non-reusable assets, and PptSmith mapping are documented.
- Chosen theme/template/layouts match the brief and the deck purpose.

### Visual Consistency

- Palette roles are consistent across cover, section, content, data, and summary slides.
- Typography hierarchy is stable and readable.
- Spacing rhythm, card treatment, radius, border, and shadow feel systematic.
- Image treatment is consistent and does not stretch or distort assets.
- Chart styling follows the selected theme and remains readable in PPTX and rendered QA pages.

### Reference Alignment

- The deck reflects the reference's broad style direction: density, hierarchy, typography feel, color mood, image language, and effects.
- The deck does not promise pixel-perfect cloning or full CSS/PPTX equivalence.
- Any deliberate divergence from the reference is recorded, especially for readability, audience fit, or PPTX editability.

### Brand And Rights

- Default templates and examples remain brand-neutral.
- Source-specific logos, proprietary illustrations, exact copy, screenshots, and private data are not reused unless explicitly authorized.
- Authorized assets are copied into the active deck workspace `assets/` directory and listed in `manifest.json`.
- Untrusted external links, macros, scripts, or executable resources are not embedded.

### PPTX Editability

- Titles, body text, core metrics, labels, tables, and basic charts remain native/editable.
- Complex gradients, textures, shadows, and compositions use SVG/PNG fallback only where appropriate.
- If a visual area is rasterized, key labels and data remain native text where feasible.

## Severity

- `failed`: missing style brief for a reference-driven deck, missing visual
  reference evidence, text-only website/style assessment, unreadable output,
  unauthorized protected asset reuse, or key content only available as a
  broken/rasterized artifact.
- `warning`: style match is weak, fallback is used for non-critical visuals, or reference divergence is acceptable but should be disclosed.
- `passed`: reference style is captured, mapped, and delivered without compromising PptSmith structure or PPTX editability.

## Fix Order

1. Fix unauthorized or unsafe asset use.
2. Fix unreadable contrast, missing fonts, missing images, and layout overflow.
3. Improve mapping from style brief to theme/template/layout.
4. Reduce excessive density or decorative effects.
5. Add or clarify fallback warnings.
