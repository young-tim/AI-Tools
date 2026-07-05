---
name: decksmith
description: >-
  AI Presentation Compiler: creates enterprise slides, PPT decks, proposals, reports,
  reviews, and slide-based deliverables from Slide IR (structured JSON), with built-in
  themes, templates, layouts, and components. Exports high-fidelity HTML preview, PDF,
  and editable PPTX. Use when creating presentations, pitch decks, project reports,
  meeting slides, sales proposals, data reports, technical architecture decks, or when
  the user provides a website, PPT, image, screenshot, moodboard, or visual reference
  to learn presentation style, effects, layout, typography, or design direction. 当用户需要制作演示稿、幻灯片、PPT、方案、报告、汇报、提案，或参考网站、PPT、图片、截图学习风格并生成演示稿时触发。
---

# DeckSmith

DeckSmith is an AI presentation compiler. Use it to turn a brief, document, dataset,
or visual reference into a structured slide deck with reliable HTML, PDF, and editable
PPTX outputs.

## Core Contract

- Treat **Slide IR JSON** as the only source of truth. Do not treat HTML, PDF, or PPTX as the primary source.
- Build narrative and page intent before visual styling. Never choose a template first and force content into it.
- Keep title, body text, metrics, tables, charts, logos, and process nodes editable in PPTX whenever possible.
- Store all deliverables under `.decksmith/`; do not scatter generated files in the project root.
- Keep default themes, templates, examples, and public docs brand-neutral. Use placeholders such as `[Your Brand]` and `[Company Name]`.
- Do not claim pixel-perfect website cloning, arbitrary URL import, or full CSS-to-PPTX mapping. Reference materials inform the deck style; they are not copied blindly.

## Required Workflow

1. Parse the user brief, source documents, data, and any visual references.
2. If the user provides a website, PPT, image, screenshot, or moodboard as style input, read `{SKILL_ROOT}/references/style-reference-workflow.md` and create `.decksmith/source/style-brief.md` or `.decksmith/source/style-brief.json` before choosing a theme.
3. Define the audience, purpose, delivery context, tone, and success criteria.
4. Create an outline and assign one core message to each slide.
5. Read `{SKILL_ROOT}/references/style-presets.md` when the user describes a design tone, color mood, visual style, industry, or asks for a deck to feel premium, minimal, technical, SaaS-like, editorial, data-heavy, dark, warm, bold, or similar.
6. Read `{SKILL_ROOT}/references/template-decision.md` when selecting theme, template, layouts, and components.
7. Read `{SKILL_ROOT}/references/design-system.md` when generating or adapting theme tokens, density, motion, variance, typography, color, or component styling.
8. Generate `.decksmith/presentation.json` as Slide IR and validate it against `{SKILL_ROOT}/schema/presentation.schema.json`.
9. Render `.decksmith/presentation.html`, export `.decksmith/presentation.pdf`, and compile `.decksmith/presentation.pptx`.
10. Run HTML layout QA, PPTX回渲 visual QA, and style QA. For reference-driven decks, read `{SKILL_ROOT}/references/style-qa.md`.
11. Fix issues in this order: reduce text, adjust layout, switch layout, split slides, tune font size above the minimum, then use SVG/PNG fallback for complex visuals.
12. Write `.decksmith/manifest.json` with source files, assets, warnings, fallbacks, and QA results.

## Output Workspace

Use this workspace shape for every build:

```text
.decksmith/
├── presentation.json
├── presentation.html
├── presentation.pdf
├── presentation.pptx
├── manifest.json
├── source/
│   ├── brief.md
│   ├── outline.json
│   ├── style-brief.md
│   ├── theme.json
│   ├── template.json
│   └── data.json
├── assets/
│   ├── images/
│   ├── icons/
│   ├── charts/
│   ├── fonts/
│   └── generated/
├── previews/
│   ├── html/
│   ├── pptx/
│   └── diff/
├── qa/
│   ├── qa-report.json
│   ├── html-layout-report.json
│   ├── pptx-visual-diff.json
│   └── style-qa-report.json
├── cache/
└── logs/
```

Cache, logs, preview screenshots, and issue screenshots should not be committed unless the user explicitly asks for evidence artifacts.

## Slide IR Rules

Use the schema in `{SKILL_ROOT}/schema/presentation.schema.json`. The root object includes:

- `version`, `meta`, `theme`, `template`, `settings`, `assets`, and `slides`
- optional `themeOverrides` for reference-driven style adaptation
- slide-level `id`, `type`, `layout`, `title`, `subtitle`, `components`, `notes`, and `qa`

Do not store large arbitrary CSS blocks in Slide IR. Express visuals through Theme, Template, Layout, Component, Variant, and constrained `themeOverrides`.

## Built-In Resources

Read these files instead of recreating lists from memory:

- Themes: `{SKILL_ROOT}/themes/*.json`
- Templates: `{SKILL_ROOT}/templates/*.json`
- Style preset data: `{SKILL_ROOT}/references/style-presets.csv` and `{SKILL_ROOT}/references/industry-style-rules.csv`
- Layout registry: `{SKILL_ROOT}/components/layouts.json`
- Component registry: `{SKILL_ROOT}/components/components.json`
- Examples: `{SKILL_ROOT}/examples/*.json`

V1 built-ins include 5 themes, 6 templates, 18 layouts, and 18 components. Use registered layouts and components first. Add a new layout or component only when the requested deck cannot be represented by the existing registry.

## Content Rules

- Use conclusion-style slide titles, not topic labels.
- Keep one core message per slide.
- Prefer 5 or fewer body bullets per slide, 4 or fewer bullets per card, and 6 or fewer cards per slide.
- Minimum body size: HTML 18px / PPT 13.5pt. Recommended body size: HTML 22px / PPT 16.5pt.
- Do not fill space with generic icons, decorative gradients, vague copy, or low-information cards.
- Charts must state a clear conclusion and include units, time range, source, and key labels when relevant.

## Rendering Rules

- Use a fixed 16:9 canvas by default: HTML 1920x1080 px, PPTX 13.333x7.5 in.
- Use 96px left/right and 72px top/bottom safe margins.
- Localize all fonts, images, icons, charts, and generated assets under `.decksmith/assets/`.
- Do not rely on public CSS, remote fonts, remote scripts, async APIs, or pseudo-elements for critical text/data.
- Every slide section in HTML must include a stable `data-slide-id`.

## PPTX Strategy

Use this fallback order:

```text
Native editable PPTX object
↓
SVG fallback
↓
High-resolution PNG fallback
↓
Structured content plus QA warning
↓
Fail only when key content cannot be represented
```

Never convert an entire slide to a screenshot as the default fix. If a complex visual area is rasterized, keep slide title, key labels, and critical numbers as editable text.

## Unsupported As Key Content

Do not make these effects the only way to express critical content: blur filters, backdrop filters, blend modes, masks, clip paths, CSS 3D transforms, WebGL, Canvas text, dynamic script-generated content, pseudo-element text, macros, executable links, or unvalidated external resources.

## QA Checklist

Before delivery, verify:

- `.decksmith/presentation.json` exists and validates.
- HTML has no obvious overflow, overlap, missing image, missing font, or contrast issue.
- PDF matches HTML without browser headers/footers.
- PPTX opens in common slide editors and preserves core text/data as independent objects.
- HTML screenshots and PPTX回渲 screenshots are visually close for supported components.
- `.decksmith/qa/qa-report.json` exists; reference-driven decks also include `style-qa-report.json`.
- Any fallback is recorded in `manifest.json` and explained clearly.

## CLI Reference

```bash
decksmith create --input ./brief.md --theme enterprise-light --template business-consulting --output ./.decksmith
decksmith build --input .decksmith/presentation.json --output ./.decksmith --export html,pdf,pptx --qa true
decksmith preview --workspace ./.decksmith
decksmith export --workspace ./.decksmith --format pdf,pptx
decksmith qa --workspace ./.decksmith
decksmith clean --workspace ./.decksmith --cache-only
```
