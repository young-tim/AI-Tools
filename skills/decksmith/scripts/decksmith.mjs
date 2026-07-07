#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SKILL_ROOT = path.resolve(__dirname, "..");
const DEFAULT_OUTPUT_ROOT = ".decksmith";
const ENV_CACHE_FILENAME = "env.json";
const OUTPUT_PPTX_PREFIX = "presentation";
const INTERNAL_FILENAMES = {
  ir: "presentation.json",
  pptx: "presentation.pptx",
  manifest: "manifest.json"
};
const WORKSPACE_FILES = {
  ir: path.join("ir", INTERNAL_FILENAMES.ir),
  pptx: path.join("output", INTERNAL_FILENAMES.pptx),
  manifest: INTERNAL_FILENAMES.manifest
};
const LEGACY_WORKSPACE_FILES = {
  ir: INTERNAL_FILENAMES.ir,
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
  decksmith build --input <presentation.json> [--output-root ./.decksmith] [--slug <slug>] [--refresh-env] [--overwrite]
  decksmith qa --workspace <deck-workspace>
  decksmith clean --workspace <deck-workspace> [--cache-only]

Builds create versioned native PPTX output under output/presentation-vN.pptx.
Runtime paths are cached in .decksmith/env.json and refreshed with --refresh-env.`);
}

async function buildDeck(options) {
  const inputPath = path.resolve(options.input);
  const { ir, schemaWarnings } = await loadAndValidateIr(inputPath);
  const registries = loadRegistries(ir);
  const requestedSlug = assertSlug(options.slug || ir.meta?.slug || slugify(ir.meta?.title || "deck"));
  const outputRoot = path.resolve(options.outputRoot || DEFAULT_OUTPUT_ROOT);
  const slug = resolveBuildTargetSlug(outputRoot, requestedSlug, options, inputPath);
  const workspace = path.join(outputRoot, "decks", slug);
  const warnings = [...schemaWarnings];
  const fallbacks = [];
  const runtime = getRuntimeEnv(outputRoot, options);

  if (slug !== requestedSlug) {
    warnings.push(`deck slug "${requestedSlug}" already exists; created numbered workspace "${slug}" instead`);
  }

  prepareWorkspace(workspace, options);
  copyInputIr(inputPath, workspace);
  copyDeclaredAssets(ir, inputPath, workspace, warnings);

  const buildVersion = resolveNextOutputVersion(workspace, options);
  const outputs = {
    pptx: getVersionedPptxPath(workspace, buildVersion)
  };
  await buildPptxFile(ir, registries, outputs.pptx, { warnings, fallbacks });

  const qaReport = shouldRunQa(options.qa) ? await runQa(workspace, { write: true, pptxPath: outputs.pptx }) : null;
  const manifest = writeManifest(workspace, {
    ir,
    slug,
    buildVersion,
    inputPath,
    outputs,
    warnings,
    fallbacks,
    registries,
    qaReport,
    runtime
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
      warnings.push("strict schema validation unavailable; built-in structural validation only was used");
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
    path.join(workspace, "qa"),
    path.join(workspace, "qa", "rendered-pages"),
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
  if (inputIsInBaseWorkspace) {
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
    WORKSPACE_FILES.pptx,
    WORKSPACE_FILES.manifest,
    path.join("qa", "qa-report.json"),
    LEGACY_WORKSPACE_FILES.pptx,
    LEGACY_WORKSPACE_FILES.manifest
  ].some((relativePath) => fs.existsSync(path.join(workspace, relativePath))) || listOutputVersions(workspace).length > 0;
}

function clearBuildArtifacts(workspace) {
  for (const relativePath of [
    "output",
    "qa",
    "cache",
    "logs",
    WORKSPACE_FILES.manifest,
    LEGACY_WORKSPACE_FILES.pptx,
    LEGACY_WORKSPACE_FILES.manifest
  ]) {
    const targetPath = path.join(workspace, relativePath);
    if (fs.existsSync(targetPath)) {
      fs.rmSync(targetPath, { recursive: true, force: true });
    }
  }
}

function resolveNextOutputVersion(workspace, options) {
  if (options.outputVersion) {
    return parseOutputVersion(options.outputVersion);
  }
  const versions = listOutputVersions(workspace).map((entry) => entry.version);
  return versions.length ? Math.max(...versions) + 1 : 1;
}

function parseOutputVersion(value) {
  const match = String(value).trim().match(/^v?([1-9][0-9]*)$/i);
  if (!match) {
    throw new Error(`invalid output version: ${value}`);
  }
  return Number(match[1]);
}

function getVersionedPptxPath(workspace, version) {
  return path.join(workspace, "output", `${OUTPUT_PPTX_PREFIX}-v${version}.pptx`);
}

function listOutputVersions(workspace) {
  const outputDir = path.join(workspace, "output");
  if (!fs.existsSync(outputDir)) return [];
  return fs.readdirSync(outputDir)
    .map((filename) => {
      const match = filename.match(/^presentation-v([1-9][0-9]*)\.pptx$/);
      return match ? { filename, version: Number(match[1]) } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.version - b.version);
}

function getRuntimeEnv(outputRoot, options) {
  const cachePath = path.join(outputRoot, ENV_CACHE_FILENAME);
  const cached = !options.refreshEnv && fs.existsSync(cachePath) ? safeReadJson(cachePath) : null;
  if (cached && cached.version === 1 && cached.skillRoot === SKILL_ROOT && cached.node?.execPath === process.execPath) {
    return cached;
  }

  const detected = {
    version: 1,
    generatedAt: new Date().toISOString(),
    skillRoot: SKILL_ROOT,
    node: {
      execPath: process.execPath,
      version: process.version,
      platform: process.platform,
      arch: process.arch
    },
    python: {
      execPath: findExecutable(["python3", "python"])
    },
    tools: {
      soffice: findExecutable(["soffice"])
    },
    packages: {
      pptxgenjs: resolvePackageSpecifier("pptxgenjs"),
      ajv: resolvePackageSpecifier("ajv")
    }
  };

  fs.mkdirSync(outputRoot, { recursive: true });
  fs.writeFileSync(cachePath, `${JSON.stringify(detected, null, 2)}\n`, "utf8");
  return detected;
}

function resolvePackageSpecifier(specifier) {
  try {
    return import.meta.resolve(specifier);
  } catch {
    return null;
  }
}

function findExecutable(names) {
  const pathEntries = String(process.env.PATH || "").split(path.delimiter).filter(Boolean);
  const suffixes = process.platform === "win32" ? ["", ".exe", ".cmd", ".bat"] : [""];
  for (const name of names) {
    for (const dir of pathEntries) {
      for (const suffix of suffixes) {
        const candidate = path.join(dir, `${name}${suffix}`);
        if (isExecutableFile(candidate)) return candidate;
      }
    }
  }
  return null;
}

function isExecutableFile(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
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

async function buildPptxFile(ir, registries, pptxPath, ctx) {
  let PptxGenJS;
  try {
    ({ default: PptxGenJS } = await import("pptxgenjs"));
  } catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" || /Cannot find package 'pptxgenjs'/.test(error.message)) {
      throw new Error("PPTX generation requires pptxgenjs from the repository or skill runtime environment. Run the bundled DeckSmith CLI from the AI-Tools repo/skill context; do not install packages inside a deck workspace.");
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
  const paths = {
    ir: resolveWorkspaceFile(workspace, "ir"),
    pptx: options.pptxPath || resolveWorkspaceFile(workspace, "pptx"),
    manifest: resolveWorkspaceFile(workspace, "manifest")
  };

  checks.push(checkFile(WORKSPACE_FILES.ir, paths.ir));
  checks.push(checkFile(toPosixPath(path.relative(workspace, paths.pptx)), paths.pptx));

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
    build: {
      version: data.buildVersion,
      outputName: path.basename(data.outputs.pptx),
      history: listOutputVersions(workspace).map((entry) => path.join("output", entry.filename).split(path.sep).join("/"))
    },
    sourceFiles: {
      input: rel(data.inputPath),
      slideIr: toPosixPath(WORKSPACE_FILES.ir),
      schema: rel(path.join(SKILL_ROOT, "schema", "presentation.schema.json"))
    },
    outputs: {
      pptx: rel(data.outputs.pptx)
    },
    registries: {
      theme: data.ir.theme,
      template: data.ir.template,
      layoutsVersion: data.registries.layouts.version || null,
      componentsVersion: data.registries.components.version || null
    },
    runtime: data.runtime ? {
      cache: toPosixPath(path.relative(workspace, path.join(path.dirname(path.dirname(workspace)), ENV_CACHE_FILENAME))),
      node: data.runtime.node,
      python: data.runtime.python,
      tools: data.runtime.tools,
      packages: data.runtime.packages
    } : null,
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
      pptx: toPosixPath(path.join(workspaceRel, manifest.outputs.pptx))
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
    : ["cache", "logs", path.join("qa", "rendered-pages")];
  for (const target of targets) {
    const targetPath = path.join(workspace, target);
    if (fs.existsSync(targetPath)) {
      fs.rmSync(targetPath, { recursive: true, force: true });
      fs.mkdirSync(targetPath, { recursive: true });
    }
  }
  console.log(`cleaned: ${targets.join(", ")}`);
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
  if (key === "pptx") {
    const manifestPath = path.join(workspace, WORKSPACE_FILES.manifest);
    const manifest = fs.existsSync(manifestPath) ? safeReadJson(manifestPath) : null;
    if (manifest?.outputs?.pptx) {
      const manifestPptx = path.join(workspace, manifest.outputs.pptx);
      if (fs.existsSync(manifestPptx)) return manifestPptx;
    }
    const versions = listOutputVersions(workspace);
    if (versions.length) {
      return path.join(workspace, "output", versions[versions.length - 1].filename);
    }
  }
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

function stringifyItem(item) {
  if (typeof item === "string") return item;
  if (item == null) return "";
  return item.title || item.label || item.name || item.description || JSON.stringify(item);
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

function safeReadJson(filePath) {
  try {
    return readJson(filePath);
  } catch {
    return null;
  }
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
