# Style Presets

Use this reference when a user asks for a visual tone, color mood, design style, industry fit, or a deck that should feel premium, technical, minimal, SaaS-like, editorial, data-heavy, warm, bold, dark, or similar.

DeckSmith uses table-backed recall for style decisions:

- `{SKILL_ROOT}/references/style-presets.csv` stores reusable presentation style presets.
- `{SKILL_ROOT}/references/industry-style-rules.csv` maps common deck domains and audience contexts to preferred presets.

These CSV files are deliberately compact. They play the same role as a design intelligence table: make style recall stable, searchable, and easy to expand without bloating `SKILL.md`.

## Recall Order

1. Identify deck domain, audience, delivery setting, and desired tone from the user request.
2. If a style reference exists, read `input/style-brief.*` in the active deck workspace and extract keywords such as palette, density, image language, typography, motion, and hierarchy.
3. Search `industry-style-rules.csv` for matching domain, audience, or trigger keywords.
4. Search `style-presets.csv` for matching style keywords and tone words.
5. Select one primary preset and at most one secondary preset.
6. Map the preset to built-in `theme`, `template`, `themeOverrides`, preferred layouts, and component treatment.
7. Record the chosen preset IDs in `input/style-brief.*` or `input/theme.json` in the active deck workspace.

## Preset Selection Rules

- Prefer audience and use case over surface-level taste. A finance board deck should not become cyberpunk just because the user says "tech".
- Use a secondary preset only to add a narrow accent, for example `executive-minimal` plus `data-ops-dashboard`.
- Do not combine more than two presets. If the request mixes too many tones, choose the one that best supports the deck's business goal.
- If a preset implies effects that are weak in PPTX, keep them as atmosphere and preserve key text/data as native objects.
- If no preset matches, use `executive-minimal` for formal decks, `saas-product-clean` for product decks, and `data-ops-dashboard` for metric-heavy decks.

## Preset Fields

`style-presets.csv` columns:

- `preset_id`: stable preset identifier.
- `display_name`: human-readable name.
- `triggers`: English and Chinese keywords for recall.
- `best_for`: deck types and business contexts.
- `avoid_for`: contexts where the preset is usually wrong.
- `theme_bias`: closest built-in DeckSmith theme.
- `template_bias`: likely template choices.
- `color_mood`: palette direction and contrast.
- `typography`: type personality and hierarchy guidance.
- `layout_bias`: layout and density guidance.
- `component_bias`: component treatment guidance.
- `effects`: PPTX-safe effect guidance.
- `avoid`: anti-patterns.

`industry-style-rules.csv` columns:

- `domain`: product, industry, or deck domain.
- `audience`: target audience.
- `triggers`: recall keywords.
- `primary_preset`: default preset.
- `secondary_preset`: optional accent preset.
- `template_bias`: likely DeckSmith template.
- `notes`: constraints and anti-pattern hints.

## Output Mapping

When a preset is selected, write a compact mapping:

```json
{
  "stylePreset": {
    "primary": "executive-minimal",
    "secondary": "data-ops-dashboard",
    "reason": "Executive decision deck with metric-heavy evidence",
    "theme": "enterprise-light",
    "template": "business-consulting",
    "themeOverrides": {
      "colors": {},
      "typography": {},
      "spacing": {}
    },
    "preferredLayouts": ["single-message", "comparison", "kpi-dashboard", "summary"],
    "avoidLayouts": ["three-card"],
    "pptxRisks": []
  }
}
```

Keep the mapping concise. The preset should guide decisions; it should not replace Slide IR or the built-in theme/template registries.
