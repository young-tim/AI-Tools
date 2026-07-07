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

- After the user confirms the content plan, treat **Slide IR JSON** as the build-time content source of truth. Before confirmation, use only a planning brief and outline proposal; do not create Slide IR.
- Build narrative and page intent before visual styling. Never choose a template first and force content into it.
- Improve content usefulness before polishing visuals: sharpen claims, remove weak filler, choose evidence, and make each slide answer a real audience question.
- Keep title, body text, metrics, tables, charts, logos, and process nodes editable in PPTX whenever possible.
- Store each deck's lifecycle artifacts under `.decksmith/decks/<deck-slug>/`; do not use `.decksmith/inputs/<deck-slug>/` or scatter generated files in the project root. Before confirmation, keep the workspace limited to planning inputs and authorized reference assets.
- When the user provides a website, PPT, image, screenshot, moodboard, or other
  style reference, inspect the actual visual artifact before describing or
  applying its style. Do not infer visual style from website text, metadata,
  brand category, or general industry expectations alone.
- When a new deck request resolves to a project name or slug that already exists, create the next numbered workspace such as `<deck-slug>-2`, `<deck-slug>-3`, and so on. Reuse the original slug only when the user explicitly asks to overwrite or continue that exact workspace.
- Use the bundled Node.js CLI and PptxGenJS for the full PPTX authoring chain after confirmation.
- Treat PPTX-native authoring as the only delivery route: build editable PowerPoint objects directly and verify the PPTX itself.
- Keep default themes, templates, examples, and public docs brand-neutral. Use placeholders such as `[Your Brand]` and `[Company Name]`.
- Do not claim pixel-perfect website cloning, arbitrary URL import, or full CSS-to-PPTX mapping. Reference materials inform the deck style; they are not copied blindly.
- Use the PPTX as the visual source of truth. Any PDF/PNG is a QA render of the PPTX, not a separate design target.

## Delivery Focus

Default to confirmed, formal PPTX delivery: first confirm the content plan, then
produce the final PPTX as native, editable PowerPoint content.

| Focus | Use When | Source Of Truth | Output |
|-------|----------|-----------------|--------|
| `pptx-native` | Default and only deck creation route after content confirmation; required for polished decks, client-facing decks, reports, proposals, architecture decks, and reusable template/component work | Native PPTX layout plus content source | PPTX |
| `reference-style` | The user provides a website, image, PPT, screenshot, or moodboard as style input | Style brief plus PPTX-native adaptation | PPTX |

Do not optimize a separate non-PPTX artifact first and then expect PPTX quality to follow. If the requested deliverable is a useful, beautiful PPT, design and QA the PPTX directly.

## Planning Confirmation Gate

For any deck request, confirm the content plan before generating the PPTX. This
includes ordinary PPT requests; do not treat missing quality language as
permission to skip confirmation or deliver draft-quality slides. The confirmed
planning brief must cover:

- goal, audience, delivery context, and success criteria
- content scope, slide count or structure, and the proposed outline
- style direction, visual references, visual evidence inspected, and any asset reuse authorization
- output format, editability expectations, constraints, and known assumptions

Before confirmation, you may inspect sources, ask focused questions, create the
deck workspace, and draft proposal artifacts under `input/`, such as
`brief.md`, `outline.json`, `style-brief.*`, and `reference-evidence.*`. These
files are proposed content, not approved build input. Do not generate Slide IR,
create or populate `ir/`, `output/`, `qa/`, or `manifest.json`, select the final
template or theme, run validation/build/QA commands, or start PPTX visual
authoring until the user confirms the planning brief.

If a requested style reference cannot be opened, rendered, screenshotted, or
visually inspected, stop and tell the user exactly what blocked inspection. Ask
for accessible screenshots/files or permission to use the needed browser,
network, renderer, or file conversion path. Do not create a style brief or choose
a style direction from uninspected references.

After presenting the planning brief, stop the current turn and wait for the
user's confirmation or requested changes. Do not continue into Slide IR, PPTX
generation, or QA in the same response. Treat user replies such as "确认",
"继续", "按这个做", or equivalent approval as the permission to start the
formal build phase. If the user asks for changes, revise the planning brief and
ask for confirmation again.

If the user explicitly asks for a quick draft or no-confirmation output, still
produce PPTX-native output and list the assumptions in the delivery note.

## Required Workflow

### Phase 1: Content Confirmation

1. Parse the user brief, source documents, data, and any visual references.
2. Create the deck workspace at `.decksmith/decks/<deck-slug>/` before writing inputs. In this phase, write only proposal artifacts under `input/` and optional reference assets under `assets/`.
3. Define the audience, purpose, delivery context, tone, success criteria, content scope, and constraints. If any high-impact detail is missing, ask a small number of focused questions before proceeding.
4. Create `input/brief.md` and draft `input/outline.json`. Assign one core message to each slide; for every slide, define the audience question it answers and the evidence or visual structure that makes the answer credible.
5. If the user provides a website, PPT, image, screenshot, or moodboard as style input, read `{SKILL_ROOT}/references/style-reference-workflow.md`, inspect the actual visual reference, save or describe the visual evidence in `input/reference-evidence.*`, and create `input/style-brief.md` or `input/style-brief.json` inside the deck workspace. If visual inspection is blocked, stop and ask for accessible evidence instead of inventing a style direction.
6. Present the planning brief in the user-visible response and ask for confirmation.

### Phase 2: Formal PPTX Build

Start this phase only after explicit user confirmation of the Phase 1 planning
brief, or when the user explicitly requested a no-confirmation PPTX-native build.

1. Read `{SKILL_ROOT}/references/style-presets.md` when the user describes a design tone, color mood, visual style, industry, or asks for a deck to feel premium, minimal, technical, SaaS-like, editorial, data-heavy, dark, warm, bold, or similar.
2. Read `{SKILL_ROOT}/references/template-decision.md` when selecting theme, template, layouts, and components.
3. Read `{SKILL_ROOT}/references/design-system.md` when generating or adapting theme tokens, density, motion, variance, typography, color, or component styling.
4. Read `{SKILL_ROOT}/references/asset-sources.md` when choosing icons, illustrations, or third-party visual assets.
5. Generate Slide IR with `meta.slug` when a stable output name is known, save it as `ir/presentation.json` in the deck workspace, then validate it with `decksmith validate --input <presentation.json>`. Without optional Ajv, validation uses built-in structural checks.
6. Read `{SKILL_ROOT}/references/pptx-native-delivery.md` before authoring the PPTX. Build the deck with PptxGenJS native PPTX objects directly for delivery.
7. Build the PPTX under `output/` and keep any deck-local generation scripts under `cache/` or `logs/` unless the user asks to keep implementation artifacts.
8. Run PPTX visual QA: `python3 {SKILL_ROOT}/scripts/pptx_qa.py <deck.pptx> --workspace <deck-workspace> --render required`, then open and inspect the generated `visualQa.representativePages` PNG/PDF pages. The script only creates evidence and reports whether render QA is possible; it is not the visual judgment. If the helper reports visual QA as blocked, do not downgrade silently to structural QA; state the blocker and ask whether to install/enable a renderer or proceed with the limitation. For reference-driven decks, also read `{SKILL_ROOT}/references/style-qa.md`.
9. Fix issues in this order: improve or shorten weak content, reduce text, adjust layout, switch layout, split slides, tune font size above the minimum, then handle remaining visual issues locally.
10. Confirm the deck workspace contains `manifest.json`, `qa/qa-report.json`, `ir/presentation.json` or an equivalent content source, and the requested PPTX.

## Output Workspace

Use this workspace shape after the formal build phase. Before confirmation, the
workspace may contain only `input/` planning files and optional reference assets.
Resolve `<deck-slug>` from CLI `--slug`, then `meta.slug`, then a normalized
`meta.title`. If that slug already exists for a new deck, use the next available
numbered slug (`<deck-slug>-2`, `<deck-slug>-3`, etc.) instead of mixing project
files. A pre-created planning workspace is valid before confirmation; do not add
`ir/`, `output/`, `qa/`, or `manifest.json` until Phase 2. Rebuilding a
workspace that already has generated outputs
requires `--overwrite`, which replaces generated output, QA evidence, cache, and
log files while preserving `input/`, `assets/`, and the input IR.

```text
.decksmith/
├── index.json
└── decks/
    └── <deck-slug>/
        ├── input/
        │   ├── brief.md
        │   ├── outline.json
        │   ├── style-brief.md
        │   ├── reference-evidence.json
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
        │   ├── ATTRIBUTIONS.md
        │   └── generated/
        ├── qa/
        │   ├── qa-report.json
        │   ├── pptx-qa-report.json
        │   ├── rendered-pages/
        │   └── style-qa-report.json
        ├── cache/
        ├── logs/
        └── manifest.json
```

Cache, logs, rendered QA pages, and issue screenshots should not be committed unless the user explicitly asks for evidence artifacts.

## Slide IR Rules

Apply these rules only in Phase 2 after content confirmation, or when the user
explicitly requested a no-confirmation PPTX-native build.

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
- Asset source guidance: `{SKILL_ROOT}/references/asset-sources.md`
- Layout registry: `{SKILL_ROOT}/components/layouts.json`
- Component registry: `{SKILL_ROOT}/components/components.json`
- Examples: `{SKILL_ROOT}/examples/*.json`

Reference files are subordinate to the Planning Confirmation Gate. If a
reference describes selecting a template, mapping a style, generating Slide IR,
building PPTX, or running QA, perform that action only in Phase 2 after user
confirmation, unless the user explicitly requested a no-confirmation PPTX-native build.

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

## Asset Source Rules

- Use Lucide as the default and only built-in icon source. Reference Lucide names in `icon.props.name`, or use a localized SVG asset in `icon.props.src` when a specific icon file is already available.
- Use icons only when they clarify scanning, status, category, or hierarchy. When a matching Lucide icon is unavailable or would feel generic, fall back to a native PPT shape or a simple numbered marker.
- Use unDraw as an optional illustration source when a localized illustration fits the slide message, audience, tone, and evidence needs better than native shapes, charts, screenshots, or plain text.
- Do not hotlink external assets. Download authorized Lucide SVGs and unDraw images into the active deck workspace under `assets/icons/` or `assets/images/` before referencing them in Slide IR.
- Record third-party asset provenance in Slide IR `assets[]` and in `assets/ATTRIBUTIONS.md`, including source name, source URL, license name, and whether attribution is required.
- For unDraw, do not redistribute a compiled illustration pack, build a competing asset service, or use the assets for AI/ML training datasets. Use it only as localized presentation artwork inside a deck.

## Rendering Rules

- Use a fixed 16:9 PPTX canvas by default: 13.333x7.5 in.
- Use 96px left/right and 72px top/bottom safe margins.
- Localize all fonts, images, icons, charts, and generated assets under the active deck workspace `assets/` directory.
- Do not rely on remote fonts, remote images, external services, macros, or executable links for critical text/data.
- Avoid presentation effects that require rasterizing key content. Prefer native PPTX text, shapes, connectors, tables, and charts.

## PPTX Strategy

DeckSmith uses PptxGenJS end to end for PPTX authoring. Prefer native editable
PPTX objects for text, shapes, tables, charts, and slide structure. If a visual
asset or rendering issue appears, resolve it locally in the deck build and record
the fallback in `manifest.json` and QA notes.

For SVG assets, use PptxGenJS `addImage` with base64 SVG image data.

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

Run build and QA commands only in Phase 2 after content confirmation, or when
the user explicitly requested a no-confirmation PPTX-native build.

```bash
cd {SKILL_ROOT}
node ./scripts/decksmith.mjs validate --input ./examples/ai-consulting-deck.json
node ./scripts/decksmith.mjs build --input ./examples/ai-consulting-deck.json --output-root ./.decksmith --qa true
node ./scripts/decksmith.mjs qa --workspace ./.decksmith/decks/enterprise-ai-capability-plan
node ./scripts/decksmith.mjs clean --workspace ./.decksmith/decks/enterprise-ai-capability-plan --cache-only
python3 ./scripts/pptx_qa.py ./.decksmith/decks/enterprise-ai-capability-plan/output/presentation.pptx --workspace ./.decksmith/decks/enterprise-ai-capability-plan --render required
```

Dependency handling:

- Use the repository or skill runtime dependencies for DeckSmith commands.
- Do not run `npm install`, `pnpm add`, or package-manager installs inside an active deck workspace such as `.decksmith/decks/<deck-slug>/`.
- Strict schema validation uses `ajv` only when it is already available; otherwise built-in structural validation is acceptable.
- PPTX authoring requires `pptxgenjs` from the repository or skill environment.
- PPTX render QA uses an existing LibreOffice `soffice`; install it only after explicit user approval.
