---
name: decksmith
description: >-
  AI Presentation Compiler: creates enterprise slides, PPT decks, proposals, reports,
  reviews, and slide-based deliverables from Slide IR (structured JSON), with built-in
  themes, templates, layouts, components, and PPTX-first native delivery guidance.
  Produces editable, high-design PowerPoint decks with strong narrative structure,
  useful slide content, reusable templates, and PPTX visual QA. Use when creating
  presentations, pitch decks, project reports, meeting slides, sales proposals,
  data reports, technical architecture decks, or when the user provides a website,
  PPT, image, screenshot, moodboard, or visual reference to learn presentation
  style, effects, layout, typography, or design direction. Use also when the user
  prioritizes polished PPTX output, high-design slides, presentation aesthetics,
  PPTX editability, reusable templates, or slide component systems. 当用户需要制作演示稿、幻灯片、PPT、方案、报告、汇报、提案，或参考网站、PPT、图片、截图学习风格并生成演示稿，或强调PPTX观赏性、高设计感、可编辑性、模板体系、组件体系时触发。
---

# DeckSmith

DeckSmith is an AI presentation compiler. Use it to turn a brief, document, dataset,
or visual reference into a structured, editable, high-design PPTX deck.

## Core Contract

- Treat **Slide IR JSON** as the default planning and content source of truth. For PPTX-first delivery, keep the Slide IR or equivalent outline as the content source, but let the native PPTX build be the visual source of truth.
- Build narrative and page intent before visual styling. Never choose a template first and force content into it.
- Improve content usefulness before polishing visuals: sharpen claims, remove weak filler, choose evidence, and make each slide answer a real audience question.
- Keep title, body text, metrics, tables, charts, logos, and process nodes editable in PPTX whenever possible.
- Store each deck's inputs, IR, outputs, assets, QA, cache, and logs under `.decksmith/decks/<deck-slug>/`; do not use `.decksmith/inputs/<deck-slug>/` or scatter generated files in the project root.
- Use the bundled Node.js CLI for Slide IR validation and draft PPTX export when useful, but use native PPTX authoring for polished delivery.
- Treat manual deck-local PPTX generation as the preferred route for high-design deliverables when the default exporter is too generic.
- Keep default themes, templates, examples, and public docs brand-neutral. Use placeholders such as `[Your Brand]` and `[Company Name]`.
- Do not claim pixel-perfect website cloning, arbitrary URL import, or full CSS-to-PPTX mapping. Reference materials inform the deck style; they are not copied blindly.
- Use the PPTX as the visual source of truth. Any PDF/PNG is a QA render of the PPTX, not a separate design target.

## Delivery Focus

Default to PPTX delivery.

| Focus | Use When | Source Of Truth | Output |
|-------|----------|-----------------|--------|
| `pptx-first` | Any polished deck, client-facing deck, report, proposal, architecture deck, or reusable template/component work | Native PPTX layout plus content source | PPTX |
| `reference-style` | The user provides a website, image, PPT, screenshot, or moodboard as style input | Style brief plus PPTX-native adaptation | PPTX |
| `draft-export` | The user needs a fast rough structure and accepts a lower-design editable draft | Slide IR and default PPTX exporter | PPTX draft |

Do not optimize a separate preview first and then expect PPTX quality to follow. If the requested deliverable is a useful, beautiful PPT, design and QA the PPTX directly.

## Planning Confirmation Gate

For formal, client-facing, high-design, or `pptx-first` decks, create a planning brief and get user confirmation before visual generation. The confirmed planning brief must cover:

- goal, audience, delivery context, and success criteria
- content scope, slide count or structure, and the proposed outline
- style direction, visual references, and any asset reuse authorization
- output format, editability expectations, constraints, and known assumptions

Before confirmation, you may inspect sources, ask focused questions, create the deck workspace, and draft `input/brief.md`, `input/outline.json`, and `input/style-brief.*` when relevant. Do not generate Slide IR, select the final template or theme, or start PPTX visual authoring until the user confirms the planning brief.

Exception: when the user explicitly asks for a quick draft, rough structure, or no-confirmation flow, use `draft-export`. In that case, list the default assumptions in the delivery note and state that formal polish still requires confirmation before refinement.

## Required Workflow

1. Parse the user brief, source documents, data, and any visual references.
2. Create the deck workspace at `.decksmith/decks/<deck-slug>/` before writing inputs. Store briefs, outlines, style briefs, data, and reference notes under `input/`; store the Slide IR or equivalent content source under `ir/`; store deliverable PPTX files under `output/`.
3. Define the audience, purpose, delivery context, tone, success criteria, content scope, and constraints. If any high-impact detail is missing, ask a small number of focused questions before proceeding.
4. Create `input/brief.md` and draft `input/outline.json`. Assign one core message to each slide; for every slide, define the audience question it answers and the evidence or visual structure that makes the answer credible.
5. If the user provides a website, PPT, image, screenshot, or moodboard as style input, read `{SKILL_ROOT}/references/style-reference-workflow.md` and create `input/style-brief.md` or `input/style-brief.json` inside the deck workspace.
6. Present the planning brief for confirmation before formal `pptx-first` or high-design generation. Wait for user confirmation unless the user explicitly requested `draft-export`.
7. Read `{SKILL_ROOT}/references/style-presets.md` when the user describes a design tone, color mood, visual style, industry, or asks for a deck to feel premium, minimal, technical, SaaS-like, editorial, data-heavy, dark, warm, bold, or similar.
8. Read `{SKILL_ROOT}/references/template-decision.md` when selecting theme, template, layouts, and components.
9. Read `{SKILL_ROOT}/references/design-system.md` when generating or adapting theme tokens, density, motion, variance, typography, color, or component styling.
10. Generate Slide IR with `meta.slug` when a stable output name is known, save it as `ir/presentation.json` in the deck workspace, then validate it with `decksmith validate --input <presentation.json>`. Without optional Ajv, validation uses built-in structural checks.
11. Read `{SKILL_ROOT}/references/pptx-native-delivery.md` before authoring the PPTX. Build native PPTX objects directly for polished delivery; use the default exporter only for drafts or simple decks.
12. Build the PPTX under `output/` and keep any deck-local generation scripts under `cache/` or `logs/` unless the user asks to keep implementation artifacts.
13. Run PPTX visual QA: `python3 {SKILL_ROOT}/scripts/pptx_qa.py <deck.pptx> --workspace <deck-workspace> --render required`, then open and inspect the generated `visualQa.representativePages` PNG/PDF pages. The script only creates evidence and reports whether render QA is possible; it is not the visual judgment. If the helper reports visual QA as blocked, do not downgrade silently to structural QA; state the blocker and ask whether to install/enable a renderer or proceed with the limitation. For reference-driven decks, also read `{SKILL_ROOT}/references/style-qa.md`.
14. Fix issues in this order: improve or shorten weak content, reduce text, adjust layout, switch layout, split slides, tune font size above the minimum, then use SVG/PNG fallback for complex non-critical visuals.
15. Confirm the deck workspace contains `manifest.json`, `qa/qa-report.json`, `ir/presentation.json` or an equivalent content source, and the requested PPTX.

## Output Workspace

Use this workspace shape for every build. Resolve `<deck-slug>` from CLI `--slug`, then `meta.slug`, then a normalized `meta.title`. A pre-created input-only workspace is valid. Rebuilding a workspace that already has generated outputs requires `--overwrite`, which replaces generated output, QA, preview, cache, and log files while preserving `input/`, `assets/`, and the input IR.

```text
.decksmith/
├── index.json
└── decks/
    └── <deck-slug>/
        ├── input/
        │   ├── brief.md
        │   ├── outline.json
        │   ├── style-brief.md
        │   ├── theme.json
        │   ├── template.json
        │   └── data.json
        ├── ir/
        │   └── presentation.json
        ├── output/
        │   └── presentation.pptx
        ├── assets/
        │   ├── images/
        │   ├── icons/
        │   ├── charts/
        │   ├── fonts/
        │   └── generated/
        ├── previews/
        │   ├── pptx/
        │   └── qa/
        ├── qa/
        │   ├── qa-report.json
        │   ├── pptx-qa-report.json
        │   └── style-qa-report.json
        ├── cache/
        ├── logs/
        └── manifest.json
```

Cache, logs, preview screenshots, and issue screenshots should not be committed unless the user explicitly asks for evidence artifacts.

## Slide IR Rules

Use the schema in `{SKILL_ROOT}/schema/presentation.schema.json`. The root object includes:

- `version`, `meta`, `theme`, `template`, `settings`, `assets`, and `slides`
- optional `meta.slug` for deterministic output workspace naming
- optional `themeOverrides` for reference-driven style adaptation
- slide-level `id`, `type`, `layout`, `title`, `subtitle`, `components`, `notes`, and `qa`

Do not store large arbitrary CSS blocks in Slide IR. Express visuals through Theme, Template, Layout, Component, Variant, and constrained `themeOverrides`.

## Built-In Resources

Read these files instead of recreating lists from memory:

- Themes: `{SKILL_ROOT}/themes/*.json`
- Templates: `{SKILL_ROOT}/templates/*.json`
- Style preset data: `{SKILL_ROOT}/references/style-presets.csv` and `{SKILL_ROOT}/references/industry-style-rules.csv`
- PPTX-first delivery: `{SKILL_ROOT}/references/pptx-native-delivery.md`
- Layout registry: `{SKILL_ROOT}/components/layouts.json`
- Component registry: `{SKILL_ROOT}/components/components.json`
- Examples: `{SKILL_ROOT}/examples/*.json`

V1 built-ins include 5 themes, 6 templates, 18 layouts, and 18 components. Use registered layouts and components first. Add a new layout or component only when the requested deck cannot be represented by the existing registry.

## Content Rules

- Use conclusion-style slide titles, not topic labels.
- Keep one core message per slide.
- Prefer 5 or fewer body bullets per slide, 4 or fewer bullets per card, and 6 or fewer cards per slide.
- Minimum body size: PPT 13.5pt. Recommended body size: PPT 16.5pt.
- Do not fill space with generic icons, decorative gradients, vague copy, or low-information cards.
- Charts must state a clear conclusion and include units, time range, source, and key labels when relevant.
- Each slide should earn its place: remove slides that do not change what the audience knows, believes, or decides.
- Prefer concrete nouns, numbers, timelines, ownership, risks, and decisions over generic claims.

## Rendering Rules

- Use a fixed 16:9 PPTX canvas by default: 13.333x7.5 in.
- Use 96px left/right and 72px top/bottom safe margins.
- Localize all fonts, images, icons, charts, and generated assets under the active deck workspace `assets/` directory.
- Do not rely on remote fonts, remote images, external services, macros, or executable links for critical text/data.
- Avoid presentation effects that require rasterizing key content. Prefer native PPTX text, shapes, connectors, tables, and charts.

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

The default DeckSmith PPTX exporter is a structured editable draft exporter. For polished customer-facing PPTX decks, use native PPTX objects and deck-specific helpers.

## Unsupported As Key Content

Do not make these effects the only way to express critical content: blur filters, backdrop filters, blend modes, masks, clip paths, CSS 3D transforms, WebGL, Canvas text, dynamic script-generated content, pseudo-element text, macros, executable links, or unvalidated external resources.

## QA Checklist

Before delivery, verify:

- `ir/presentation.json` exists in the active deck workspace and validates.
- New builds store Slide IR at `ir/presentation.json` and deliverables under `output/`; legacy root-level files are read only for compatibility.
- PPTX opens in common slide editors and preserves core text/data as independent objects.
- Content QA passes: each slide has a clear claim, relevant evidence, and no filler that could be removed without changing the message.
- Render the final PPTX to PDF/PNG with `{SKILL_ROOT}/scripts/pptx_qa.py` and inspect representative full-size slides.
- Structural PPTX checks, including ZIP validity, slide count, text extraction, and media listing, are not visual QA. Use them as evidence only when render QA is explicitly blocked or the user accepts structural-only QA.
- Do not use WPS Office as a command-line PPTX renderer on macOS, and do not install LibreOffice or Poppler during QA without explicit user approval.
- `qa/qa-report.json` exists in the active deck workspace; reference-driven decks also include `style-qa-report.json`.
- Any fallback is recorded in `manifest.json` and explained clearly.

## CLI Reference

```bash
cd {SKILL_ROOT}
node ./scripts/decksmith.mjs validate --input ./examples/ai-consulting-deck.json
node ./scripts/decksmith.mjs build --input ./examples/ai-consulting-deck.json --output-root ./.decksmith --export pptx --qa true
node ./scripts/decksmith.mjs qa --workspace ./.decksmith/decks/enterprise-ai-capability-plan
node ./scripts/decksmith.mjs clean --workspace ./.decksmith/decks/enterprise-ai-capability-plan --cache-only
python3 ./scripts/pptx_qa.py ./.decksmith/decks/enterprise-ai-capability-plan/output/presentation.pptx --workspace ./.decksmith/decks/enterprise-ai-capability-plan --render required
```

Optional dependencies:

- Strict schema validation: install `ajv`.
- Draft PPTX export: install `pptxgenjs`, then build with `--export pptx`.
- PPTX render QA: use an existing LibreOffice `soffice`; install it only after explicit user approval.

Prefer `pnpm` when installing optional dependencies. If `pnpm` is unavailable, fall back to npm equivalents.
