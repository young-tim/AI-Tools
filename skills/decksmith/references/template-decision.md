# Template Decision Guidance

Use this reference after the outline and slide goals are known and the user has
confirmed the content plan. During the planning phase, mention template or theme
direction only as a proposal; do not make final selections or proceed to Slide IR
before confirmation.

## Decision Order

1. Confirm the deck job: inform, persuade, sell, report, review, teach, align, or decide.
2. Confirm audience: executive, customer, technical, operations, product, investor, internal team, or mixed.
3. Confirm content center: strategy, product, sales, data, architecture, roadmap, project status, or training.
4. Read `input/style-brief.*` in the active deck workspace if present.
5. Read `{SKILL_ROOT}/references/style-presets.md` if the request contains a visual tone, industry style, or color mood.
6. Select template for narrative structure.
7. Select theme or `themeOverrides` for visual expression.
8. Select layouts per slide goal.
9. Select components per evidence type.

## Template Selection

| Template | Use When |
|----------|----------|
| `business-consulting` | Strategy, diagnosis, transformation plan, executive decision support |
| `product-proposal` | Product concept, requirement proposal, solution design, launch plan |
| `sales-deck` | Customer proposal, commercial value story, offer explanation |
| `data-report` | Metrics review, operating analysis, trend explanation, dashboard-style reporting |
| `technical-architecture` | Platform capability, system design, integration plan, technical roadmap |
| `project-review` | Milestone review, delivery recap, risks, next actions |

If two templates seem plausible, choose based on audience action. Example: a product analytics deck for leadership is often `data-report`; the same facts used to win funding may be `product-proposal`.

## Theme Selection

| Theme | Use When |
|-------|----------|
| `enterprise-light` | Formal executive or consulting-style decks |
| `business-blue` | Commercial, customer-facing, professional proposals |
| `tech-gradient` | Product launch, technical innovation, platform capability |
| `default-light` | Neutral general-purpose decks |
| `default-dark` | Dark-mode presentation environments or high-contrast visual stories |

When a style brief exists, choose the closest built-in theme first, then apply constrained `themeOverrides`. Do not create a new theme only to match a single reference exactly.

When a style preset is selected, use its `theme_bias` and `template_bias` as recommendations, not absolute rules. If narrative structure conflicts with style preference, keep the correct template and express the preset through theme overrides, layout density, typography, and component treatment.

## Layout Selection By Slide Goal

| Goal | Preferred Layouts |
|------|-------------------|
| Open the story | `cover`, `single-message` |
| Segment the narrative | `section`, `agenda` |
| Explain one argument | `single-message`, `image-text`, `two-column` |
| Compare options | `comparison`, `matrix`, `two-column` |
| Show numbers | `kpi-dashboard`, `table-report`, chart components |
| Explain sequence | `process-flow`, `timeline`, `roadmap` |
| Explain system | `architecture`, `matrix`, `process-flow` |
| Summarize and decide | `summary`, `qa` |

Avoid using `three-card` as the default for every slide. Cards are useful for parallel ideas, not for every argument.

## Component Selection

- Use `title`, `subtitle`, `body-text`, and `bullet-list` for narrative content.
- Use `metric-card` for headline numbers, not long explanations.
- Use `table` when exact values matter; use charts when pattern or comparison matters.
- Use `bar-chart` for ranked comparison, `line-chart` for trend, and `pie-chart` only for simple part-to-whole cases.
- Use `process-node` and `timeline-node` for flows and sequencing.
- Use `callout` and `quote` sparingly for emphasis.
- Use `background-art` only for atmosphere or section identity, not key content.

## Style Reference Mapping

When a reference is provided:

- Map visual density to slide density before choosing layouts.
- Map reference hierarchy to type scale and title treatment.
- Map image language to asset treatment, not to copied assets.
- Map motion/effects to PPTX-safe fallback strategy.
- Preserve DeckSmith content rules even if the reference is visually dense or decorative.

When only a tone or industry is provided:

- Use `industry-style-rules.csv` for domain/audience recall.
- Use `style-presets.csv` for direct style keyword recall.
- Pick one primary preset and at most one secondary preset.
- Record the selected preset IDs and reason in the style brief or theme snapshot.

## Red Flags

- The selected template changes the meaning of the content.
- The theme is chosen because it looks interesting, not because it serves audience and delivery context.
- Most slides use the same layout.
- Visual style requires rasterizing key text or data.
- The deck copies source branding or proprietary content without explicit authorization.
