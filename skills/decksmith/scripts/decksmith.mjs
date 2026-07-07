#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SKILL_ROOT = path.resolve(__dirname, "..");
const DEFAULT_OUTPUT_ROOT = ".decksmith";
const INTERNAL_FILENAMES = {
  ir: "presentation.json",
  html: "presentation.html",
  pdf: "presentation.pdf",
  pptx: "presentation.pptx",
  manifest: "manifest.json"
};
const WORKSPACE_FILES = {
  ir: path.join("ir", INTERNAL_FILENAMES.ir),
  html: path.join("output", INTERNAL_FILENAMES.html),
  pdf: path.join("output", INTERNAL_FILENAMES.pdf),
  pptx: path.join("output", INTERNAL_FILENAMES.pptx),
  manifest: INTERNAL_FILENAMES.manifest
};
const LEGACY_WORKSPACE_FILES = {
  ir: INTERNAL_FILENAMES.ir,
  html: INTERNAL_FILENAMES.html,
  pdf: INTERNAL_FILENAMES.pdf,
  pptx: INTERNAL_FILENAMES.pptx,
  manifest: INTERNAL_FILENAMES.manifest
};

main(process.argv).catch((error) => {
  console.error(`decksmith: ${error.message}`);
  process.exitCode = 1;
});

async function main(argv) {
  const { command, options } = parseCli(argv.slice(2));
  if (!command || options.help) {
    printHelp();
    return;
  }
  if (options.version) {
    console.log("0.1.0");
    return;
  }

  switch (command) {
    case "validate": {
      requireOption(options, "input", "validate");
      const { ir, schemaWarnings } = await loadAndValidateIr(options.input);
      console.log(`valid: ${options.input} (${ir.slides.length} slides)`);
      for (const warning of schemaWarnings) console.warn(`warning: ${warning}`);
      return;
    }
    case "build": {
      requireOption(options, "input", "build");
      const result = await buildDeck({
        outputRoot: DEFAULT_OUTPUT_ROOT,
        export: "html",
        qa: "true",
        ...options
      });
      console.log(`workspace: ${result.workspace}`);
      console.log(`outputs: ${Object.values(result.outputs).filter(Boolean).join(", ")}`);
      return;
    }
    case "qa": {
      requireOption(options, "workspace", "qa");
      const report = await runQa(path.resolve(options.workspace), { write: true });
      console.log(`${report.status}: ${options.workspace}`);
      return;
    }
    case "preview": {
      requireOption(options, "workspace", "preview");
      const htmlPath = resolveWorkspaceFile(path.resolve(options.workspace), "html");
      if (!fs.existsSync(htmlPath)) {
        throw new Error(`HTML preview not found: ${htmlPath}`);
      }
      console.log(pathToFileURL(htmlPath).href);
      return;
    }
    case "clean": {
      requireOption(options, "workspace", "clean");
      cleanWorkspace(path.resolve(options.workspace), options);
      return;
    }
    default:
      throw new Error(`unknown command: ${command}`);
  }
}

function parseCli(args) {
  const options = {};
  let command = null;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!command && !arg.startsWith("-")) {
      command = arg;
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      options.help = true;
      continue;
    }
    if (arg === "--version" || arg === "-v") {
      options.version = true;
      continue;
    }
    if (!arg.startsWith("--")) {
      throw new Error(`unexpected argument: ${arg}`);
    }
    const raw = arg.slice(2);
    const eqIndex = raw.indexOf("=");
    const key = toCamelCase(eqIndex >= 0 ? raw.slice(0, eqIndex) : raw);
    if (eqIndex >= 0) {
      options[key] = raw.slice(eqIndex + 1);
      continue;
    }
    const next = args[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }
  return { command, options };
}

function requireOption(options, key, command) {
  if (!options[key]) {
    throw new Error(`${command} requires --${key.replace(/[A-Z]/g, (char) => `-${char.toLowerCase()}`)}`);
  }
}

function toCamelCase(value) {
  return value.replace(/-([a-z])/g, (_, char) => char.toUpperCase());
}

function printHelp() {
  console.log(`DeckSmith CLI

Usage:
  decksmith validate --input <presentation.json>
  decksmith build --input <presentation.json> [--output-root ./.decksmith] [--slug <slug>] [--overwrite] [--export html|html,pptx|html,pdf]
  decksmith qa --workspace <deck-workspace>
  decksmith preview --workspace <deck-workspace>
  decksmith clean --workspace <deck-workspace> [--cache-only]

HTML preview builds use only Node.js built-ins. PDF and PPTX exports load optional dependencies only when requested.`);
}

async function buildDeck(options) {
  const inputPath = path.resolve(options.input);
  const { ir, schemaWarnings } = await loadAndValidateIr(inputPath);
  const registries = loadRegistries(ir);
  const requestedSlug = assertSlug(options.slug || ir.meta?.slug || slugify(ir.meta?.title || "deck"));
  const outputRoot = path.resolve(options.outputRoot || DEFAULT_OUTPUT_ROOT);
  const slug = resolveBuildTargetSlug(outputRoot, requestedSlug, options, inputPath);
  const workspace = path.join(outputRoot, "decks", slug);
  const exports = parseExports(options.export, ir.settings || {});
  const warnings = [...schemaWarnings];
  const fallbacks = [];

  if (slug !== requestedSlug) {
    warnings.push(`deck slug "${requestedSlug}" already exists; created numbered workspace "${slug}" instead`);
  }

  prepareWorkspace(workspace, options);
  copyInputIr(inputPath, workspace);
  copyDeclaredAssets(ir, inputPath, workspace, warnings);

  const outputs = {};
  if (exports.has("html") || exports.has("pdf")) {
    const html = renderHtml(ir, registries, { warnings, fallbacks });
    outputs.html = path.join(workspace, WORKSPACE_FILES.html);
    fs.writeFileSync(outputs.html, html, "utf8");
  }

  if (exports.has("pdf")) {
    outputs.pdf = path.join(workspace, WORKSPACE_FILES.pdf);
    await exportPdf(outputs.html, outputs.pdf);
  }

  if (exports.has("pptx")) {
    outputs.pptx = path.join(workspace, WORKSPACE_FILES.pptx);
    await exportPptx(ir, registries, outputs.pptx, { warnings, fallbacks });
  }

  const qaReport = shouldRunQa(options.qa) ? await runQa(workspace, { write: true, expectedExports: exports }) : null;
  const manifest = writeManifest(workspace, {
    ir,
    slug,
    inputPath,
    outputs,
    warnings,
    fallbacks,
    registries,
    qaReport
  });
  updateIndex(outputRoot, manifest);

  return { workspace, outputs, manifest };
}

async function loadAndValidateIr(inputPath) {
  const schema = readJson(path.join(SKILL_ROOT, "schema", "presentation.schema.json"));
  const ir = readJson(path.resolve(inputPath));
  const warnings = basicValidateIr(ir);
  try {
    const { default: Ajv } = await import("ajv");
    const ajv = new Ajv({
      allErrors: true,
      strict: false,
      validateFormats: false
    });
    const validate = ajv.compile(schema);
    if (!validate(ir)) {
      const details = validate.errors.map((error) => `${error.instancePath || "/"} ${error.message}`).join("; ");
      throw new Error(`invalid Slide IR: ${details}`);
    }
  } catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" || /Cannot find package 'ajv'/.test(error.message)) {
      warnings.push('strict schema validation skipped because optional Ajv is not installed; HTML build used built-in structural validation only');
    } else {
      throw error;
    }
  }
  return { ir, schemaWarnings: [...warnings, ...findIrWarnings(ir)] };
}

function loadRegistries(ir) {
  const themePath = path.join(SKILL_ROOT, "themes", `${ir.theme}.json`);
  const templatePath = path.join(SKILL_ROOT, "templates", `${ir.template}.json`);
  if (!fs.existsSync(themePath)) {
    throw new Error(`theme not found: ${ir.theme}`);
  }
  if (ir.template && !fs.existsSync(templatePath)) {
    throw new Error(`template not found: ${ir.template}`);
  }
  return {
    theme: deepMerge(readJson(themePath), ir.themeOverrides || {}),
    template: ir.template ? readJson(templatePath) : null,
    layouts: readJson(path.join(SKILL_ROOT, "components", "layouts.json")),
    components: readJson(path.join(SKILL_ROOT, "components", "components.json"))
  };
}

function ensureWorkspace(workspace) {
  for (const dir of [
    workspace,
    path.join(workspace, "input"),
    path.join(workspace, "ir"),
    path.join(workspace, "output"),
    path.join(workspace, "assets", "images"),
    path.join(workspace, "assets", "icons"),
    path.join(workspace, "assets", "charts"),
    path.join(workspace, "assets", "fonts"),
    path.join(workspace, "assets", "generated"),
    path.join(workspace, "previews", "html"),
    path.join(workspace, "previews", "pptx"),
    path.join(workspace, "previews", "diff"),
    path.join(workspace, "qa"),
    path.join(workspace, "cache"),
    path.join(workspace, "logs")
  ]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function prepareWorkspace(workspace, options) {
  if (!fs.existsSync(workspace)) {
    ensureWorkspace(workspace);
    return;
  }
  if (workspaceHasBuildArtifacts(workspace) && !options.overwrite) {
    throw new Error(`deck workspace already has build outputs: ${workspace}. Re-run with --overwrite to replace generated output files while preserving input and assets.`);
  }
  if (options.overwrite) {
    clearBuildArtifacts(workspace);
  }
  ensureWorkspace(workspace);
}

function resolveBuildTargetSlug(outputRoot, baseSlug, options, inputPath) {
  if (options.overwrite) return baseSlug;

  const baseWorkspace = path.join(outputRoot, "decks", baseSlug);
  if (!fs.existsSync(baseWorkspace)) return baseSlug;

  const inputIsInBaseWorkspace = isPathInside(inputPath, baseWorkspace);
  if (inputIsInBaseWorkspace && !workspaceHasBuildArtifacts(baseWorkspace)) {
    return baseSlug;
  }

  for (let index = 2; index < 1000; index += 1) {
    const candidate = assertSlug(withNumericSuffix(baseSlug, index));
    const candidateWorkspace = path.join(outputRoot, "decks", candidate);
    if (!fs.existsSync(candidateWorkspace)) return candidate;
  }

  throw new Error(`could not find an available deck slug for: ${baseSlug}`);
}

function withNumericSuffix(slug, index) {
  const suffix = `-${index}`;
  const maxLength = 80;
  const root = slug.slice(0, maxLength - suffix.length).replace(/-+$/g, "") || "deck";
  return `${root}${suffix}`;
}

function isPathInside(filePath, directoryPath) {
  const relativePath = path.relative(path.resolve(directoryPath), path.resolve(filePath));
  return relativePath === "" || (!!relativePath && !relativePath.startsWith("..") && !path.isAbsolute(relativePath));
}

function workspaceHasBuildArtifacts(workspace) {
  return [
    WORKSPACE_FILES.html,
    WORKSPACE_FILES.pdf,
    WORKSPACE_FILES.pptx,
    WORKSPACE_FILES.manifest,
    path.join("qa", "qa-report.json"),
    LEGACY_WORKSPACE_FILES.html,
    LEGACY_WORKSPACE_FILES.pdf,
    LEGACY_WORKSPACE_FILES.pptx,
    LEGACY_WORKSPACE_FILES.manifest
  ].some((relativePath) => fs.existsSync(path.join(workspace, relativePath)));
}

function clearBuildArtifacts(workspace) {
  for (const relativePath of [
    "output",
    "previews",
    "qa",
    "cache",
    "logs",
    WORKSPACE_FILES.manifest,
    LEGACY_WORKSPACE_FILES.html,
    LEGACY_WORKSPACE_FILES.pdf,
    LEGACY_WORKSPACE_FILES.pptx,
    LEGACY_WORKSPACE_FILES.manifest
  ]) {
    const targetPath = path.join(workspace, relativePath);
    if (fs.existsSync(targetPath)) {
      fs.rmSync(targetPath, { recursive: true, force: true });
    }
  }
}

function copyInputIr(inputPath, workspace) {
  const dest = path.join(workspace, WORKSPACE_FILES.ir);
  if (path.resolve(inputPath) === path.resolve(dest)) return;
  fs.copyFileSync(inputPath, dest);
}

function copyDeclaredAssets(ir, inputPath, workspace, warnings) {
  const inputDir = path.dirname(inputPath);
  for (const asset of ir.assets || []) {
    if (!asset.path) continue;
    const source = path.resolve(inputDir, asset.path);
    const dest = path.resolve(workspace, asset.path);
    if (!dest.startsWith(workspace)) {
      warnings.push(`asset skipped because it resolves outside workspace: ${asset.path}`);
      continue;
    }
    if (!fs.existsSync(source)) {
      warnings.push(`asset declared but source file was not found: ${asset.path}`);
      continue;
    }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(source, dest);
  }
}

function renderHtml(ir, registries, ctx) {
  const theme = registries.theme;
  const colors = theme.colors || {};
  const settings = ir.settings || {};
  const width = settings.canvasWidth || 1920;
  const height = settings.canvasHeight || 1080;
  const font = theme.fonts?.body?.family || "Arial, sans-serif";
  const titleFont = theme.fonts?.heading?.family || font;
  const css = `
    :root {
      --canvas-w: ${width}px;
      --canvas-h: ${height}px;
      --bg: ${colors.background || "#ffffff"};
      --surface: ${colors.surface || "#f8fafc"};
      --surface-alt: ${colors.surfaceAlt || "#eef2f7"};
      --text: ${colors.textPrimary || colors.primary || "#111827"};
      --muted: ${colors.textSecondary || colors.secondary || "#4b5563"};
      --line: ${colors.line || "#e5e7eb"};
      --accent: ${colors.accent || colors.primary || "#1f2937"};
      --accent-soft: ${colors.accentSoft || "#e5e7eb"};
      --on-accent: ${colors.textOnAccent || "#ffffff"};
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #d8dee8;
      color: var(--text);
      font-family: ${font};
    }
    .deck {
      display: grid;
      gap: 40px;
      justify-content: center;
      padding: 40px;
    }
    .slide {
      position: relative;
      width: var(--canvas-w);
      height: var(--canvas-h);
      overflow: hidden;
      background: var(--bg);
      box-shadow: 0 16px 48px rgba(15, 23, 42, 0.18);
      padding: 72px 96px;
      page-break-after: always;
    }
    .slide.dark {
      --bg: #0f172a;
      --surface: #172033;
      --surface-alt: #1e293b;
      --text: #f8fafc;
      --muted: #cbd5e1;
      --line: #334155;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.16);
      background: var(--bg);
    }
    .slide-header { max-width: 1500px; margin-bottom: 34px; }
    .slide-title {
      font-family: ${titleFont};
      font-size: ${theme.typography?.slideTitle?.size || 36}px;
      line-height: ${theme.typography?.slideTitle?.lineHeight || 1.22};
      font-weight: ${theme.typography?.slideTitle?.weight || 700};
      margin: 0;
      letter-spacing: 0;
    }
    .slide-subtitle {
      margin: 12px 0 0;
      color: var(--muted);
      font-size: ${theme.typography?.slideSubtitle?.size || 22}px;
      line-height: 1.45;
    }
    .content-grid {
      display: grid;
      gap: 24px;
      align-content: stretch;
      height: calc(100% - 150px);
    }
    .layout-cover .content-grid,
    .layout-section .content-grid {
      height: 100%;
      align-content: center;
      max-width: 1320px;
    }
    .layout-cover .component-title {
      font-size: ${theme.typography?.coverTitle?.size || 60}px;
      line-height: ${theme.typography?.coverTitle?.lineHeight || 1.12};
      font-weight: ${theme.typography?.coverTitle?.weight || 700};
      max-width: 1180px;
    }
    .layout-cover .component-subtitle {
      font-size: ${theme.typography?.coverSubtitle?.size || 26}px;
      color: var(--muted);
      max-width: 980px;
    }
    .layout-two-column .content-grid,
    .layout-comparison .content-grid,
    .layout-image-text .content-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .layout-three-card .content-grid,
    .layout-process-flow .content-grid,
    .layout-roadmap .content-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .layout-kpi-dashboard .content-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .layout-architecture .content-grid,
    .layout-timeline .content-grid,
    .layout-table-report .content-grid,
    .layout-agenda .content-grid {
      grid-template-columns: 1fr;
    }
    .component {
      min-width: 0;
      color: var(--text);
      font-size: ${theme.typography?.body?.size || 19}px;
      line-height: ${theme.typography?.body?.lineHeight || 1.55};
    }
    .component-title { font-size: 30px; font-weight: 700; line-height: 1.25; }
    .component-subtitle { font-size: 24px; line-height: 1.45; }
    .body-text, .component-bullet-list, .card, .panel, .callout, .metric, .table-wrap {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px 32px;
    }
    .component-bullet-list ul,
    .component-bullet-list ol,
    .panel ul,
    .card ul,
    .node ul {
      margin: 12px 0 0;
      padding-left: 1.2em;
    }
    li { margin: 8px 0; }
    .callout {
      border-left: 8px solid var(--accent);
      font-size: 24px;
      line-height: 1.5;
      background: var(--accent-soft);
    }
    .quote {
      font-size: 32px;
      line-height: 1.35;
      border-left: 8px solid var(--accent);
      padding-left: 32px;
    }
    .panel h3, .card h3, .node h3, .arch-layer h3 { margin: 0 0 14px; font-size: 25px; }
    .metric .value { color: var(--accent); font-size: 48px; line-height: 1; font-weight: 800; }
    .metric .label { margin-top: 12px; font-weight: 700; font-size: 19px; }
    .metric .description { margin-top: 10px; color: var(--muted); font-size: 17px; }
    .node, .arch-layer {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px 28px;
      background: var(--surface);
    }
    .node .meta, .arch-layer .meta {
      color: var(--accent);
      font-weight: 700;
      margin-bottom: 10px;
      font-size: 16px;
    }
    .arch-items {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .chip {
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: var(--surface-alt);
      font-size: 16px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 17px; }
    th, td { border: 1px solid var(--line); padding: 12px 14px; text-align: left; vertical-align: top; }
    th { background: var(--surface-alt); font-weight: 700; }
    .chart-bars { display: grid; gap: 12px; margin-top: 12px; }
    .bar-row { display: grid; grid-template-columns: 180px 1fr 60px; gap: 12px; align-items: center; }
    .bar-track { height: 16px; border-radius: 999px; background: var(--surface-alt); overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); }
    .footer {
      position: absolute;
      left: 96px;
      right: 96px;
      bottom: 38px;
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 13px;
    }
    @media print {
      body { background: #fff; }
      .deck { display: block; padding: 0; }
      .slide { box-shadow: none; margin: 0; }
      @page { size: ${width}px ${height}px; margin: 0; }
    }
  `;

  const slides = ir.slides.map((slide, index) => renderSlide(slide, index, ir, ctx)).join("\n");
  return `<!doctype html>
<html lang="${escapeAttr(ir.meta?.language || "en-US")}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(ir.meta?.title || "DeckSmith Presentation")}</title>
  <style>${css}</style>
</head>
<body>
  <main class="deck" data-deck-title="${escapeAttr(ir.meta?.title || "")}">
${slides}
  </main>
</body>
</html>
`;
}

function renderSlide(slide, index, ir, ctx) {
  const layout = `layout-${slide.layout || "single-message"}`;
  const dark = slide.themeVariant === "dark" ? " dark" : "";
  const showHeader = !["cover", "section"].includes(slide.layout);
  const components = (slide.components || [])
    .filter((component) => component.visible !== false)
    .map((component) => renderComponent(component, ctx))
    .join("\n");
  const header = showHeader && (slide.title || slide.subtitle)
    ? `<header class="slide-header">${slide.title ? `<h1 class="slide-title">${escapeHtml(slide.title)}</h1>` : ""}${slide.subtitle ? `<p class="slide-subtitle">${escapeHtml(slide.subtitle)}</p>` : ""}</header>`
    : "";
  const footer = renderFooter(slide, index, ir);
  return `    <section class="slide ${layout}${dark}" data-slide-id="${escapeAttr(slide.id)}">
      ${header}
      <div class="content-grid">
        ${components}
      </div>
      ${footer}
    </section>`;
}

function renderComponent(component, ctx) {
  const type = component.type;
  switch (type) {
    case "title":
    case "subtitle":
      return `<div class="component component-${type}" data-component-id="${escapeAttr(component.id)}">${escapeHtml(component.content || component.title || "")}</div>`;
    case "body-text":
      return `<div class="component body-text" data-component-id="${escapeAttr(component.id)}">${paragraphs(component.content)}</div>`;
    case "bullet-list":
      return `<div class="component component-bullet-list" data-component-id="${escapeAttr(component.id)}">${renderList(component.items, component.variant === "agenda-numbered")}</div>`;
    case "callout":
      return `<div class="component callout" data-component-id="${escapeAttr(component.id)}">${paragraphs(component.content || component.text || component.title || "")}</div>`;
    case "quote":
      return `<blockquote class="component quote" data-component-id="${escapeAttr(component.id)}">${paragraphs(component.content || component.text || "")}</blockquote>`;
    case "comparison-panel":
      return `<article class="component panel" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.title || "")}</h3>${renderList(component.items)}</article>`;
    case "metric-card":
      return `<article class="component metric" data-component-id="${escapeAttr(component.id)}"><div class="value">${escapeHtml(component.value || "")}</div><div class="label">${escapeHtml(component.label || component.title || "")}</div>${component.description ? `<div class="description">${escapeHtml(component.description)}</div>` : ""}</article>`;
    case "process-node":
    case "timeline-node":
      return renderNode(component);
    case "architecture-layer":
      return renderArchitectureLayer(component);
    case "card":
      return `<article class="component card" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.title || "")}</h3>${component.description ? `<p>${escapeHtml(component.description)}</p>` : ""}${renderList(component.items)}</article>`;
    case "three-card":
      return `<div class="component card" data-component-id="${escapeAttr(component.id)}">${renderMiniCards(component.items || [])}</div>`;
    case "kpi-dashboard":
      return `<div class="component card" data-component-id="${escapeAttr(component.id)}">${renderMiniMetrics(component.items || [])}</div>`;
    case "table":
      return renderTable(component);
    case "bar-chart":
    case "line-chart":
    case "pie-chart":
      ctx.fallbacks.push({ componentId: component.id, type, strategy: "html-basic-chart-and-native-pptx-summary" });
      return renderBasicChart(component);
    case "image":
      return renderImage(component);
    case "icon":
      return `<div class="component card" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.icon || component.title || "Icon")}</h3></div>`;
    case "background-art":
      ctx.fallbacks.push({ componentId: component.id, type, strategy: "html-background-treatment-only" });
      return "";
    default:
      ctx.fallbacks.push({ componentId: component.id, type, strategy: "generic-card" });
      return `<article class="component card" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.title || type)}</h3>${renderList(component.items)}${component.content ? paragraphs(component.content) : ""}</article>`;
  }
}

function renderNode(component) {
  const meta = [component.phase, component.step, component.time, component.duration, component.status].filter(Boolean).join(" · ");
  return `<article class="component node" data-component-id="${escapeAttr(component.id)}">${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}<h3>${escapeHtml(component.title || "")}</h3>${component.description ? `<p>${escapeHtml(component.description)}</p>` : ""}${renderList(component.items)}</article>`;
}

function renderArchitectureLayer(component) {
  return `<section class="component arch-layer" data-component-id="${escapeAttr(component.id)}"><div class="meta">${escapeHtml(component.variant || "layer")}</div><h3>${escapeHtml(component.title || "")}</h3><div class="arch-items">${(component.items || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div></section>`;
}

function renderTable(component) {
  const headers = component.headers || [];
  const rows = component.rows || [];
  return `<div class="component table-wrap" data-component-id="${escapeAttr(component.id)}"><table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderMiniCards(items) {
  if (!items.length) return "";
  return `<div style="display:grid;grid-template-columns:repeat(${Math.min(3, items.length)}, minmax(0, 1fr));gap:16px">${items.map((item) => `<article class="node"><h3>${escapeHtml(stringifyItemTitle(item))}</h3>${item.content || item.description ? `<p>${escapeHtml(item.content || item.description)}</p>` : ""}</article>`).join("")}</div>`;
}

function renderMiniMetrics(items) {
  if (!items.length) return "";
  return `<div style="display:grid;grid-template-columns:repeat(${Math.min(4, items.length)}, minmax(0, 1fr));gap:16px">${items.map((item) => `<article class="metric"><div class="value">${escapeHtml(item.value || "")}</div><div class="label">${escapeHtml(item.label || item.title || "")}</div>${item.description ? `<div class="description">${escapeHtml(item.description)}</div>` : ""}</article>`).join("")}</div>`;
}

function renderBasicChart(component) {
  const series = component.series?.[0];
  const values = series?.data || component.data?.map((item) => item.value) || [];
  const labels = component.categories || component.data?.map((item) => item.name) || [];
  const max = Math.max(...values.map(Number), 1);
  const rows = labels.map((label, index) => {
    const value = Number(values[index] || 0);
    const width = Math.max(2, Math.round((value / max) * 100));
    return `<div class="bar-row"><div>${escapeHtml(label)}</div><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><div>${escapeHtml(String(values[index] ?? ""))}</div></div>`;
  }).join("");
  return `<div class="component card" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.title || "")}</h3><div class="chart-bars">${rows}</div></div>`;
}

function renderImage(component) {
  const src = component.src || component.path || component.asset || component.assetId || "";
  if (!src) {
    return `<div class="component card" data-component-id="${escapeAttr(component.id)}"><h3>${escapeHtml(component.title || "Image")}</h3><p>Missing image source</p></div>`;
  }
  return `<figure class="component card" data-component-id="${escapeAttr(component.id)}"><img src="${escapeAttr(src)}" alt="${escapeAttr(component.alt || component.title || "")}" style="max-width:100%;max-height:100%;object-fit:contain"><figcaption>${escapeHtml(component.title || "")}</figcaption></figure>`;
}

function renderFooter(slide, index, ir) {
  if (slide.footer?.hide) return "";
  const footer = slide.footer || ir.footer || {};
  const brand = footer.brandText || ir.footer?.brandText || "";
  const page = footer.pageNumber || String(index + 1).padStart(2, "0");
  return `<footer class="footer"><span>${escapeHtml(brand)}</span><span>${escapeHtml(page)}</span></footer>`;
}

async function exportPdf(htmlPath, pdfPath) {
  let browser;
  try {
    const { chromium } = await import("playwright");
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
    await page.pdf({
      path: pdfPath,
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: "0", bottom: "0", left: "0", right: "0" }
    });
  } catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" || /Cannot find package 'playwright'/.test(error.message)) {
      throw new Error('PDF export requires optional Playwright. Install it only when PDF export is needed: "pnpm add -D playwright" then "pnpm exec playwright install chromium".');
    }
    throw new Error(`PDF export failed. Ensure optional Playwright browsers are installed with "pnpm exec playwright install chromium" from {SKILL_ROOT}. ${error.message}`);
  } finally {
    if (browser) await browser.close();
  }
}

async function exportPptx(ir, registries, pptxPath, ctx) {
  let PptxGenJS;
  try {
    ({ default: PptxGenJS } = await import("pptxgenjs"));
  } catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" || /Cannot find package 'pptxgenjs'/.test(error.message)) {
      throw new Error('PPTX export requires optional pptxgenjs. Install it only when PPTX export is needed: "pnpm add -D pptxgenjs".');
    }
    throw error;
  }
  const pptx = new PptxGenJS();
  pptx.layout = ir.settings?.pptLayout || "LAYOUT_WIDE";
  pptx.author = ir.meta?.author || "DeckSmith";
  pptx.subject = ir.meta?.description || "";
  pptx.title = ir.meta?.title || "DeckSmith Presentation";
  pptx.company = ir.meta?.company || "";
  pptx.lang = ir.meta?.language || "en-US";
  pptx.theme = {
    headFontFace: "Arial",
    bodyFontFace: "Arial",
    lang: ir.meta?.language || "en-US"
  };

  for (const [index, slideIr] of ir.slides.entries()) {
    addPptxSlide(pptx, slideIr, index, ir, registries, ctx);
  }
  await pptx.writeFile({ fileName: pptxPath });
}

function addPptxSlide(pptx, slideIr, index, ir, registries, ctx) {
  const slide = pptx.addSlide();
  const theme = registries.theme;
  const colors = theme.colors || {};
  const isDark = slideIr.themeVariant === "dark";
  const bg = normalizeColor(isDark ? "#0F172A" : colors.background || "#FFFFFF");
  const text = normalizeColor(isDark ? "#F8FAFC" : colors.textPrimary || colors.primary || "#111827");
  const muted = normalizeColor(isDark ? "#CBD5E1" : colors.textSecondary || colors.secondary || "#4B5563");
  const accent = normalizeColor(colors.accent || colors.primary || "#0F172A");
  slide.background = { color: bg };

  const layout = slideIr.layout || "single-message";
  const showHeader = !["cover", "section"].includes(layout);
  let y = 0.48;
  if (showHeader) {
    if (slideIr.title) {
      slide.addText(slideIr.title, {
        x: 0.66,
        y,
        w: 11.9,
        h: 0.64,
        fontFace: "Arial",
        fontSize: 21,
        bold: true,
        color: text,
        margin: 0
      });
      y += 0.62;
    }
    if (slideIr.subtitle) {
      slide.addText(slideIr.subtitle, {
        x: 0.66,
        y,
        w: 11.9,
        h: 0.36,
        fontFace: "Arial",
        fontSize: 12,
        color: muted,
        margin: 0
      });
      y += 0.52;
    }
  }

  const boxes = computePptxBoxes(layout, slideIr.components?.length || 1, showHeader ? y : 0.9);
  (slideIr.components || []).forEach((component, componentIndex) => {
    const box = boxes[componentIndex] || boxes[boxes.length - 1];
    addPptxComponent(slide, component, box, { text, muted, accent, isDark, ctx });
  });

  if (!slideIr.footer?.hide) {
    const footer = slideIr.footer || ir.footer || {};
    slide.addText(footer.brandText || ir.footer?.brandText || "", {
      x: 0.66,
      y: 7.05,
      w: 5.6,
      h: 0.22,
      fontSize: 7.5,
      color: muted,
      margin: 0
    });
    slide.addText(footer.pageNumber || String(index + 1).padStart(2, "0"), {
      x: 12.0,
      y: 7.05,
      w: 0.7,
      h: 0.22,
      align: "right",
      fontSize: 7.5,
      color: muted,
      margin: 0
    });
  }

  if (slideIr.notes) {
    slide.addNotes(slideIr.notes);
  }
}

function computePptxBoxes(layout, count, top) {
  const left = 0.66;
  const width = 12.0;
  const bottom = 6.85;
  const height = Math.max(1.0, bottom - top);
  if (["cover", "section"].includes(layout)) {
    return Array.from({ length: count }, (_, index) => ({ x: left, y: 1.4 + index * 0.7, w: 10.8, h: index === 0 ? 1.0 : 0.45 }));
  }
  if (["two-column", "comparison", "image-text"].includes(layout)) {
    return Array.from({ length: count }, (_, index) => ({ x: left + (index % 2) * 6.15, y: top + Math.floor(index / 2) * 1.35, w: 5.8, h: 1.12 }));
  }
  if (["three-card", "process-flow", "roadmap"].includes(layout)) {
    return Array.from({ length: count }, (_, index) => ({ x: left + (index % 3) * 4.08, y: top + Math.floor(index / 3) * 1.82, w: 3.82, h: 1.55 }));
  }
  if (layout === "kpi-dashboard") {
    return Array.from({ length: count }, (_, index) => ({ x: left + (index % 3) * 4.08, y: top + Math.floor(index / 3) * 1.62, w: 3.82, h: 1.34 }));
  }
  if (layout === "architecture") {
    return Array.from({ length: count }, (_, index) => ({ x: left, y: top + index * Math.min(1.1, height / count), w: width, h: Math.min(0.95, height / count - 0.08) }));
  }
  if (layout === "table-report") {
    return [{ x: left, y: top, w: width, h: height }];
  }
  return Array.from({ length: count }, (_, index) => ({ x: left, y: top + index * Math.min(1.25, height / count), w: width, h: Math.min(1.05, height / count - 0.08) }));
}

function addPptxComponent(slide, component, box, env) {
  const fill = env.isDark ? "172033" : "F8FAFC";
  const line = env.isDark ? "334155" : "E5E7EB";
  const type = component.type;
  if (type === "title" || type === "subtitle" || type === "body-text" || type === "callout" || type === "quote") {
    slide.addText(component.content || component.text || component.title || "", {
      ...box,
      fontSize: type === "title" ? 22 : type === "subtitle" ? 14 : 11,
      bold: type === "title",
      color: env.text,
      valign: "mid",
      fit: "shrink",
      margin: 0.08
    });
    return;
  }
  if (type === "bullet-list") {
    slide.addText((component.items || []).map((item) => `• ${stringifyItem(item)}`).join("\n"), {
      ...box,
      fontSize: 10.5,
      color: env.text,
      breakLine: false,
      fit: "shrink",
      margin: 0.08
    });
    return;
  }
  if (type === "table") {
    const rows = [component.headers || [], ...(component.rows || [])];
    slide.addTable(rows, {
      ...box,
      border: { type: "solid", color: line, pt: 0.5 },
      color: env.text,
      fontSize: 7.8,
      margin: 0.04
    });
    return;
  }
  if (type === "image" && (component.src || component.path)) {
    const imagePath = component.src || component.path;
    if (fs.existsSync(imagePath)) {
      slide.addImage({ path: imagePath, ...box });
    } else {
      env.ctx.warnings.push(`PPTX image not found for component ${component.id}: ${imagePath}`);
      addCardText(slide, component.title || "Missing image", box, env, fill, line);
    }
    return;
  }
  if (type === "metric-card") {
    slide.addShape(slide.ShapeType?.rect || "rect", { ...box, fill: { color: fill }, line: { color: line, pt: 0.75 }, radius: 0.08 });
    slide.addText(component.value || "", { x: box.x + 0.12, y: box.y + 0.12, w: box.w - 0.24, h: 0.35, fontSize: 22, bold: true, color: env.accent, margin: 0 });
    slide.addText(component.label || component.title || "", { x: box.x + 0.12, y: box.y + 0.55, w: box.w - 0.24, h: 0.25, fontSize: 10.5, bold: true, color: env.text, margin: 0 });
    slide.addText(component.description || "", { x: box.x + 0.12, y: box.y + 0.86, w: box.w - 0.24, h: Math.max(0.2, box.h - 0.95), fontSize: 8.5, color: env.muted, fit: "shrink", margin: 0 });
    return;
  }
  if (["comparison-panel", "process-node", "timeline-node", "architecture-layer", "card", "three-card", "kpi-dashboard"].includes(type)) {
    addCardText(slide, summarizeComponent(component), box, env, fill, line);
    return;
  }
  if (["bar-chart", "line-chart", "pie-chart", "icon", "background-art"].includes(type)) {
    env.ctx.fallbacks.push({ componentId: component.id, type, strategy: "pptx-text-summary" });
    addCardText(slide, summarizeComponent(component), box, env, fill, line);
    return;
  }
  env.ctx.fallbacks.push({ componentId: component.id, type, strategy: "pptx-generic-card" });
  addCardText(slide, summarizeComponent(component), box, env, fill, line);
}

function addCardText(slide, text, box, env, fill, line) {
  slide.addShape(slide.ShapeType?.rect || "rect", { ...box, fill: { color: fill }, line: { color: line, pt: 0.75 }, radius: 0.08 });
  slide.addText(text, {
    x: box.x + 0.12,
    y: box.y + 0.12,
    w: box.w - 0.24,
    h: box.h - 0.22,
    fontSize: 9.5,
    color: env.text,
    fit: "shrink",
    margin: 0
  });
}

async function runQa(workspace, options = {}) {
  const checks = [];
  const expected = options.expectedExports || inferExpectedExports(workspace);
  const paths = {
    ir: resolveWorkspaceFile(workspace, "ir"),
    html: resolveWorkspaceFile(workspace, "html"),
    pdf: resolveWorkspaceFile(workspace, "pdf"),
    pptx: resolveWorkspaceFile(workspace, "pptx"),
    manifest: resolveWorkspaceFile(workspace, "manifest")
  };

  checks.push(checkFile(WORKSPACE_FILES.ir, paths.ir));
  if (expected.has("html")) checks.push(checkFile(WORKSPACE_FILES.html, paths.html));
  if (expected.has("pdf")) checks.push(checkFile(WORKSPACE_FILES.pdf, paths.pdf));
  if (expected.has("pptx")) checks.push(checkFile(WORKSPACE_FILES.pptx, paths.pptx));
  if (fs.existsSync(paths.html)) {
    const html = fs.readFileSync(paths.html, "utf8");
    checks.push({
      name: "stable-slide-ids",
      status: html.includes("data-slide-id=") ? "passed" : "failed",
      message: "HTML should include stable data-slide-id attributes."
    });
    checks.push({
      name: "static-html-no-script",
      status: /<script[\s>]/i.test(html) ? "failed" : "passed",
      message: "HTML preview should remain static HTML/CSS without runtime scripts."
    });
  }

  const status = checks.every((check) => check.status === "passed") ? "passed" : "failed";
  const report = {
    status,
    generatedAt: new Date().toISOString(),
    workspace,
    checks,
    warnings: []
  };

  if (options.write) {
    fs.mkdirSync(path.join(workspace, "qa"), { recursive: true });
    fs.writeFileSync(path.join(workspace, "qa", "qa-report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }
  return report;
}

function inferExpectedExports(workspace) {
  const manifestPath = resolveWorkspaceFile(workspace, "manifest");
  if (!fs.existsSync(manifestPath)) {
    return new Set(["html"]);
  }
  const manifest = readJson(manifestPath);
  const expected = new Set();
  for (const [format, outputPath] of Object.entries(manifest.outputs || {})) {
    if (outputPath) expected.add(format);
  }
  return expected.size ? expected : new Set(["html"]);
}

function writeManifest(workspace, data) {
  const now = new Date().toISOString();
  const rel = (filePath) => filePath ? toPosixPath(path.relative(workspace, filePath)) : null;
  const manifest = {
    version: "1.0",
    generatedAt: now,
    generator: {
      name: "decksmith",
      version: "0.1.0"
    },
    deck: {
      title: data.ir.meta?.title || "",
      slug: data.slug,
      author: data.ir.meta?.author || "",
      language: data.ir.meta?.language || "",
      theme: data.ir.theme,
      template: data.ir.template,
      slideCount: data.ir.slides.length
    },
    sourceFiles: {
      input: rel(data.inputPath),
      slideIr: toPosixPath(WORKSPACE_FILES.ir),
      schema: rel(path.join(SKILL_ROOT, "schema", "presentation.schema.json"))
    },
    outputs: {
      html: rel(data.outputs.html),
      pdf: rel(data.outputs.pdf),
      pptx: rel(data.outputs.pptx)
    },
    registries: {
      theme: data.ir.theme,
      template: data.ir.template,
      layoutsVersion: data.registries.layouts.version || null,
      componentsVersion: data.registries.components.version || null
    },
    warnings: unique(data.warnings),
    fallbacks: uniqueFallbacks(data.fallbacks),
    qa: data.qaReport ? {
      status: data.qaReport.status,
      report: "qa/qa-report.json"
    } : null
  };
  fs.writeFileSync(path.join(workspace, INTERNAL_FILENAMES.manifest), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return { ...manifest, workspace };
}

function updateIndex(outputRoot, manifest) {
  fs.mkdirSync(outputRoot, { recursive: true });
  const indexPath = path.join(outputRoot, "index.json");
  const existing = fs.existsSync(indexPath) ? readJson(indexPath) : { version: "1.0", decks: [] };
  const workspaceRel = toPosixPath(path.relative(outputRoot, manifest.workspace));
  const entry = {
    title: manifest.deck.title,
    slug: manifest.deck.slug,
    workspace: workspaceRel,
    updatedAt: manifest.generatedAt,
    outputs: {
      html: toPosixPath(path.join(workspaceRel, WORKSPACE_FILES.html)),
      pdf: toPosixPath(path.join(workspaceRel, WORKSPACE_FILES.pdf)),
      pptx: toPosixPath(path.join(workspaceRel, WORKSPACE_FILES.pptx))
    }
  };
  existing.decks = (existing.decks || []).filter((deck) => deck.slug !== manifest.deck.slug);
  existing.decks.push(entry);
  existing.updatedAt = manifest.generatedAt;
  fs.writeFileSync(indexPath, `${JSON.stringify(existing, null, 2)}\n`, "utf8");
}

function cleanWorkspace(workspace, options) {
  if (!fs.existsSync(workspace)) {
    throw new Error(`workspace not found: ${workspace}`);
  }
  const targets = options.cacheOnly
    ? ["cache", "logs"]
    : ["cache", "logs", path.join("previews", "html"), path.join("previews", "pptx"), path.join("previews", "diff")];
  for (const target of targets) {
    const targetPath = path.join(workspace, target);
    if (fs.existsSync(targetPath)) {
      fs.rmSync(targetPath, { recursive: true, force: true });
      fs.mkdirSync(targetPath, { recursive: true });
    }
  }
  console.log(`cleaned: ${targets.join(", ")}`);
}

function parseExports(value, settings) {
  const requested = new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean));
  const allowed = new Set(["html", "pdf", "pptx"]);
  for (const format of requested) {
    if (!allowed.has(format)) {
      throw new Error(`unsupported export format: ${format}`);
    }
  }
  if (settings.exportHtml === false) requested.delete("html");
  if (settings.exportPdf === false) requested.delete("pdf");
  if (settings.exportPptx === false) requested.delete("pptx");
  if (requested.has("pdf")) requested.add("html");
  return requested;
}

function shouldRunQa(value) {
  return !["false", "0", "no"].includes(String(value).toLowerCase());
}

function findIrWarnings(ir) {
  const warnings = [];
  const known = new Set([
    "title", "subtitle", "body-text", "bullet-list", "metric-card", "image", "icon",
    "comparison-panel", "process-node", "timeline-node", "table", "bar-chart", "line-chart",
    "pie-chart", "quote", "callout", "footer", "background-art", "architecture-layer", "card", "three-card", "kpi-dashboard"
  ]);
  for (const slide of ir.slides || []) {
    for (const component of slide.components || []) {
      if (!known.has(component.type)) {
        warnings.push(`unknown component type "${component.type}" on slide ${slide.id}; generic rendering will be used`);
      }
    }
  }
  return warnings;
}

function basicValidateIr(ir) {
  const errors = [];
  if (!ir || typeof ir !== "object" || Array.isArray(ir)) {
    throw new Error("invalid Slide IR: root must be an object");
  }
  if (!ir.version) errors.push("missing version");
  if (!ir.meta || typeof ir.meta !== "object") errors.push("missing meta");
  if (!ir.meta?.title) errors.push("missing meta.title");
  if (!ir.theme) errors.push("missing theme");
  if (!ir.settings || typeof ir.settings !== "object") errors.push("missing settings");
  if (!Array.isArray(ir.slides) || ir.slides.length === 0) errors.push("slides must be a non-empty array");
  for (const [index, slide] of (ir.slides || []).entries()) {
    if (!slide.id) errors.push(`slides[${index}] missing id`);
    if (!slide.layout) errors.push(`slides[${index}] missing layout`);
    if (!Array.isArray(slide.components)) errors.push(`slides[${index}] components must be an array`);
    for (const [componentIndex, component] of (slide.components || []).entries()) {
      if (!component.id) errors.push(`slides[${index}].components[${componentIndex}] missing id`);
      if (!component.type) errors.push(`slides[${index}].components[${componentIndex}] missing type`);
    }
  }
  if (errors.length) {
    throw new Error(`invalid Slide IR: ${errors.join("; ")}`);
  }
  return [];
}

function checkFile(name, filePath) {
  return {
    name,
    status: fs.existsSync(filePath) && fs.statSync(filePath).size > 0 ? "passed" : "failed",
    message: filePath
  };
}

function resolveWorkspaceFile(workspace, key) {
  const modern = path.join(workspace, WORKSPACE_FILES[key]);
  if (fs.existsSync(modern)) return modern;
  return path.join(workspace, LEGACY_WORKSPACE_FILES[key]);
}

function toPosixPath(value) {
  return value.split(path.sep).join("/");
}

function summarizeComponent(component) {
  const lines = [];
  if (component.phase || component.step || component.time || component.duration || component.status) {
    lines.push([component.phase, component.step, component.time, component.duration, component.status].filter(Boolean).join(" · "));
  }
  if (component.title) lines.push(component.title);
  if (component.label || component.value) lines.push([component.value, component.label].filter(Boolean).join(" "));
  if (component.description) lines.push(component.description);
  if (component.content) lines.push(component.content);
  if (component.items?.length) lines.push(component.items.map((item) => `• ${stringifyItem(item)}`).join("\n"));
  return lines.filter(Boolean).join("\n");
}

function renderList(items = [], ordered = false) {
  if (!items.length) return "";
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((item) => `<li>${escapeHtml(stringifyItem(item))}</li>`).join("")}</${tag}>`;
}

function stringifyItem(item) {
  if (typeof item === "string") return item;
  if (item == null) return "";
  return item.title || item.label || item.name || item.description || JSON.stringify(item);
}

function stringifyItemTitle(item) {
  if (typeof item === "string") return item;
  if (item == null) return "";
  return item.title || item.label || item.name || "";
}

function paragraphs(text = "") {
  return String(text).split(/\n{2,}/).map((part) => `<p>${escapeHtml(part)}</p>`).join("");
}

function slugify(value) {
  const normalized = String(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
  if (normalized) return normalized.slice(0, 80);
  return `deck-${crypto.createHash("sha1").update(String(value)).digest("hex").slice(0, 10)}`;
}

function assertSlug(value) {
  const slug = slugify(value);
  if (!/^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$/.test(slug) && !/^[a-z0-9]$/.test(slug)) {
    throw new Error(`invalid deck slug: ${value}`);
  }
  return slug;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function deepMerge(base, override) {
  if (!override || typeof override !== "object") return base;
  const result = Array.isArray(base) ? [...base] : { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (value && typeof value === "object" && !Array.isArray(value) && result[key] && typeof result[key] === "object" && !Array.isArray(result[key])) {
      result[key] = deepMerge(result[key], value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function normalizeColor(value) {
  return String(value || "000000").replace(/^#/, "").slice(0, 6).toUpperCase();
}

function unique(items) {
  return [...new Set(items)];
}

function uniqueFallbacks(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.componentId}:${item.type}:${item.strategy}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}
