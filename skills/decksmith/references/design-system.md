# Design System Guidance

Use this reference after content confirmation when adapting a theme, creating
`themeOverrides`, or translating a confirmed style brief into DeckSmith
presentation tokens. During planning, describe the intended design direction but
do not finalize design tokens or generate PPTX objects.

## Token Layers

Use a three-layer token model:

```text
Primitive tokens: raw values
↓
Semantic tokens: role-based aliases
↓
Slide/component tokens: presentation-specific application
```

Examples:

- Primitive: `color.blue.600`, `space.24`, `radius.8`, `font.sans`
- Semantic: `color.primary`, `color.surface`, `color.textMuted`, `space.sectionGap`
- Slide/component: `slide.title.color`, `metricCard.value.color`, `chart.axis.color`

Keep raw values in theme files or `themeOverrides`. Components should consume semantic or slide/component roles rather than ad hoc values.

## Design Dials

Use these optional dials when a user asks for a specific feel, or when a style reference implies one.

| Dial | Low | Medium | High |
|------|-----|--------|------|
| `density` | Spacious, fewer objects, generous margins | Balanced enterprise presentation | Dense dashboard/report with tighter tables and KPIs |
| `motion` | Static or subtle fades | Standard section/element reveals | Expressive but still PPTX-safe transitions |
| `variance` | Consistent, restrained pages | Moderate layout variety | Strong contrast between section, data, and story slides |

Defaults: `density=medium`, `motion=subtle`, `variance=medium`.

## Color Rules

- Define color roles first: background, surface, surfaceAlt, primary, secondary, accent, text, mutedText, border, chart palette, positive, warning, danger.
- Preserve readable contrast for slide projection and rendered QA pages.
- Use accent color sparingly for hierarchy, not decoration.
- For charts, avoid relying on color alone; use labels, direct values, or patterns when needed.
- If a reference uses a palette that is too low contrast, keep the character but increase contrast in semantic roles.

## Typography Rules

- Choose heading/body pairing by audience and delivery context: formal, technical, product, sales, or analytical.
- Preserve clear hierarchy between cover title, section title, slide title, subtitle, body, caption, metric value, and metric label.
- Keep minimum body size at PPT 13.5pt. Do not solve density by shrinking below this floor.
- Use tabular or stable numeric styling for KPI and table-heavy decks when available.

## Layout And Shape Rules

- Use spacing and alignment as a system: page margins, section gap, card padding, list gap, chart inset, and footer position must feel related.
- Match shape language across cards, callouts, charts, and process nodes. Avoid random radius and shadow values.
- Use depth only where it clarifies hierarchy. Complex blur/glass effects must have PPTX-safe fallbacks.
- Use image treatment consistently: full bleed, framed product image, masked screenshot, background texture, or icon/illustration system.

## Theme Override Guidance

Use `themeOverrides` for project-specific adaptation when the built-in theme is close but not exact. Keep overrides constrained:

- OK: color roles, font families, type scale, spacing, radius, shadow, chart palette, footer label, logo placement.
- Avoid: arbitrary CSS blocks, one-off component hacks, page-specific hardcoded colors, behavior scripts.

When overrides become large or repeated across decks, promote them into a new theme JSON file and add a README entry only if the theme is intended as public skill content.

## PPTX Safety

Before finalizing a design system, mark each style feature as:

- `native`: text, basic shapes, lines, tables, simple charts.
- `svg`: icons, vector decoration, simple illustrations.
- `raster`: complex gradients, textures, shadows, image composites.
- `avoid`: effects that carry critical meaning but cannot be represented reliably.

The deck may use raster visuals for atmosphere, but core messages and data must remain editable or clearly labeled in native objects.
