# Style Reference Workflow

Use this reference when the user provides a website, PPT, image, screenshot,
moodboard, or existing deck as visual inspiration. In the planning phase, the
goal is to produce a style brief proposal for user confirmation, not to start
Slide IR or PPTX generation. After confirmation, the style brief guides the
formal PPTX build.

## Visual Evidence Gate

Do not write a style brief from text-only website extraction, metadata, search
snippets, brand category, or general industry assumptions. First inspect the
actual visual reference and record evidence in `input/reference-evidence.md` or
`input/reference-evidence.json`. Evidence should include what was viewed, how it
was viewed, and which visual observations drive the proposed style.

If the reference cannot be visually inspected, stop and ask the user for one of:
accessible screenshots, the source file, permission to browse/render the URL, or
permission to use the needed local converter. Do not continue to template
selection, Slide IR, or PPTX generation with an invented style.

## Principles

- Extract style decisions into `input/style-brief.md` or `input/style-brief.json` in the active deck workspace before selecting a final theme or template.
- Base style decisions on inspected visual evidence, not on textual content alone.
- Separate reusable style signals from protected or source-specific assets. Colors, spacing rhythm, hierarchy, and visual treatment can inspire; logos, proprietary illustrations, exact copy, and distinctive brand marks require explicit user authorization.
- Capture what matters for slides: visual hierarchy, density, typography, color roles, image language, chart style, page rhythm, and PPTX feasibility.
- Prefer describing patterns over copying pixels. DeckSmith must still output registered layouts, components, and editable PPTX objects.

## Input-Specific Extraction

### Website Reference

1. Open or render the URL and capture/inspect representative visual sections:
   hero, content blocks, data/metric areas, cards, navigation-like structures,
   CTA/footer if relevant. Prefer screenshots or rendered page captures over
   DOM/text extraction.
2. Record colors by role: background, surface, primary, accent, text, muted text, border, positive/warning/error, chart palette.
3. Record typography: heading family/style, body family/style, weight contrast, title scale, body scale, line height, capitalization, and numeric style.
4. Record layout rhythm: canvas density, margins, grid columns, card radius, shadow/elevation, section spacing, alignment, and image-to-text ratio.
5. Record motion/effects only as presentation guidance: reveal style, transition feel, gradient use, shadows, blur, texture, dimensionality. Mark anything hard to preserve in PPTX as a fallback risk.
6. If only text can be fetched and no visual render or screenshot is available,
   report style-reference inspection as blocked instead of guessing the visual
   style.
7. Do not download or reuse website assets unless authorized and safe to localize under the active deck workspace `assets/` directory.

### PPT Reference

1. Open or render representative slides before extracting style. If rendering is
   unavailable, inspect the PPT package only as a structural fallback and ask the
   user for screenshots before claiming visual style.
2. Identify deck purpose, slide sequence, title style, section breaks, recurring layouts, chart treatment, and footer system.
3. Extract reusable slide grammar: cover composition, agenda style, data slide style, comparison style, summary/action style.
4. Capture editable-object expectations: which visual treatments must remain native text/shapes/tables/charts, and which can be SVG/PNG fallback.
5. Do not copy exact proprietary copy, logo, or confidential visual assets into default templates.

### Image or Screenshot Reference

1. View the actual image or screenshot before extracting style.
2. Treat the image as a mood/reference sample. Extract palette, contrast, texture, shape language, composition, lighting, and visual density.
3. Convert image cues into slide-safe theme tokens and layout guidance.
4. Avoid overfitting the deck to one image. Use the image to guide style, not content structure.

## Style Brief Shape

Create a concise brief with these fields:

```json
{
  "referenceType": "website | ppt | image | mixed",
  "sourceSummary": "What was provided and what style should be learned",
  "visualEvidence": [
    {
      "source": "URL, file path, screenshot path, or slide/page identifier",
      "inspectionMethod": "browser screenshot | rendered slides | viewed image | user-provided screenshot",
      "observations": []
    }
  ],
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

- `input/reference-evidence.*` exists for every visual reference, or the task is
  stopped as blocked with a clear request for accessible visual evidence.
- A style brief exists before Slide IR theme/template selection.
- The style brief cites actual visual evidence and does not rely on text-only
  extraction or generic assumptions.
- The style brief maps to DeckSmith theme, template, `themeOverrides`, preferred layouts, and fallback risks.
- Protected assets and source-specific content are listed under `doNotReuse` unless user authorization is explicit.
- The resulting deck remains a DeckSmith presentation, not a website clone or image replica.
- During the planning phase, present the style brief with the content plan and
  stop for user confirmation before final template selection, Slide IR, or PPTX
  generation.
