# Style Reference Workflow

Use this reference when the user provides a website, PPT, image, screenshot,
moodboard, or existing deck as visual inspiration. In the planning phase, the
goal is to produce a style brief proposal for user confirmation, not to start
Slide IR or PPTX generation. After confirmation, the style brief guides the
formal PPTX build.

## Principles

- Extract style decisions into `input/style-brief.md` or `input/style-brief.json` in the active deck workspace before selecting a final theme or template.
- Separate reusable style signals from protected or source-specific assets. Colors, spacing rhythm, hierarchy, and visual treatment can inspire; logos, proprietary illustrations, exact copy, and distinctive brand marks require explicit user authorization.
- Capture what matters for slides: visual hierarchy, density, typography, color roles, image language, chart style, page rhythm, and PPTX feasibility.
- Prefer describing patterns over copying pixels. DeckSmith must still output registered layouts, components, and editable PPTX objects.

## Input-Specific Extraction

### Website Reference

1. Capture or inspect representative sections: hero, content blocks, data/metric areas, cards, navigation-like structures, CTA/footer if relevant.
2. Record colors by role: background, surface, primary, accent, text, muted text, border, positive/warning/error, chart palette.
3. Record typography: heading family/style, body family/style, weight contrast, title scale, body scale, line height, capitalization, and numeric style.
4. Record layout rhythm: canvas density, margins, grid columns, card radius, shadow/elevation, section spacing, alignment, and image-to-text ratio.
5. Record motion/effects only as presentation guidance: reveal style, transition feel, gradient use, shadows, blur, texture, dimensionality. Mark anything hard to preserve in PPTX as a fallback risk.
6. Do not download or reuse website assets unless authorized and safe to localize under the active deck workspace `assets/` directory.

### PPT Reference

1. Identify deck purpose, slide sequence, title style, section breaks, recurring layouts, chart treatment, and footer system.
2. Extract reusable slide grammar: cover composition, agenda style, data slide style, comparison style, summary/action style.
3. Capture editable-object expectations: which visual treatments must remain native text/shapes/tables/charts, and which can be SVG/PNG fallback.
4. Do not copy exact proprietary copy, logo, or confidential visual assets into default templates.

### Image or Screenshot Reference

1. Treat the image as a mood/reference sample. Extract palette, contrast, texture, shape language, composition, lighting, and visual density.
2. Convert image cues into slide-safe theme tokens and layout guidance.
3. Avoid overfitting the deck to one image. Use the image to guide style, not content structure.

## Style Brief Shape

Create a concise brief with these fields:

```json
{
  "referenceType": "website | ppt | image | mixed",
  "sourceSummary": "What was provided and what style should be learned",
  "authorizedAssets": [],
  "doNotReuse": [],
  "styleKeywords": [],
  "audienceFit": "Why this style fits or does not fit the deck audience",
  "colorRoles": {
    "background": "",
    "surface": "",
    "primary": "",
    "accent": "",
    "text": "",
    "mutedText": "",
    "border": "",
    "chartPalette": []
  },
  "typography": {
    "heading": "",
    "body": "",
    "scale": "",
    "weightContrast": "",
    "numberStyle": ""
  },
  "layout": {
    "density": "low | medium | high",
    "grid": "",
    "spacingRhythm": "",
    "cardTreatment": "",
    "imageTreatment": ""
  },
  "effects": {
    "motion": "none | subtle | standard | expressive",
    "depth": "",
    "texture": "",
    "fallbackRisks": []
  },
  "decksmithMapping": {
    "theme": "",
    "template": "",
    "themeOverrides": {},
    "preferredLayouts": [],
    "avoidLayouts": []
  }
}
```

## Completion Check

- A style brief exists before Slide IR theme/template selection.
- The style brief maps to DeckSmith theme, template, `themeOverrides`, preferred layouts, and fallback risks.
- Protected assets and source-specific content are listed under `doNotReuse` unless user authorization is explicit.
- The resulting deck remains a DeckSmith presentation, not a website clone or image replica.
- During the planning phase, present the style brief with the content plan and
  stop for user confirmation before final template selection, Slide IR, or PPTX
  generation.
