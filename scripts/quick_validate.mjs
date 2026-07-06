#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const RESOURCE_JSON_DIRS = ["schema", "themes", "templates", "components", "examples"];

function usage() {
  console.error("Usage: node scripts/quick_validate.mjs <skill-dir> [<skill-dir> ...]");
}

function fail(message) {
  return { ok: false, message };
}

function pass(message) {
  return { ok: true, message };
}

function parseFrontmatter(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) return null;
  const fields = {};
  const lines = match[1].split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fieldMatch = line.match(/^([A-Za-z0-9_-]+):(?:\s*(.*))?$/);
    if (!fieldMatch) continue;

    const [, key, rawValue = ""] = fieldMatch;
    const value = rawValue.trim();
    if (value === ">-" || value === "|-" || value === ">" || value === "|") {
      const block = [];
      while (index + 1 < lines.length && /^(?:\s{2,}|\t)/.test(lines[index + 1])) {
        index += 1;
        block.push(lines[index].replace(/^(?:\s{2}|\t)/, ""));
      }
      fields[key] = block.join(" ").replace(/\s+/g, " ").trim();
    } else {
      fields[key] = value.replace(/^["']|["']$/g, "");
    }
  }

  return fields;
}

function isValidSkillName(name) {
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name) && name.length < 64;
}

function walkJsonFiles(root) {
  const files = [];
  for (const dirname of RESOURCE_JSON_DIRS) {
    const dir = path.join(root, dirname);
    if (!fs.existsSync(dir)) continue;
    walk(dir, (file) => {
      if (file.endsWith(".json")) files.push(file);
    });
  }
  return files;
}

function walk(dir, visit) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, visit);
    } else if (entry.isFile()) {
      visit(fullPath);
    }
  }
}

function validateJsonFiles(skillDir) {
  const errors = [];
  const jsonFiles = walkJsonFiles(skillDir);
  for (const file of jsonFiles) {
    try {
      JSON.parse(fs.readFileSync(file, "utf8"));
    } catch (error) {
      errors.push(`${path.relative(process.cwd(), file)}: ${error.message}`);
    }
  }
  return { count: jsonFiles.length, errors };
}

function validateSkill(skillDirInput) {
  const skillDir = path.resolve(skillDirInput);
  const rel = path.relative(process.cwd(), skillDir) || ".";
  const skillMd = path.join(skillDir, "SKILL.md");
  const results = [];

  if (!fs.existsSync(skillDir) || !fs.statSync(skillDir).isDirectory()) {
    return [fail(`${rel}: skill directory does not exist`)];
  }

  if (!fs.existsSync(skillMd)) {
    return [fail(`${rel}: missing SKILL.md`)];
  }

  const text = fs.readFileSync(skillMd, "utf8");
  const frontmatter = parseFrontmatter(text);
  if (!frontmatter) {
    return [fail(`${rel}: SKILL.md is missing YAML frontmatter delimiters`)];
  }

  const dirName = path.basename(skillDir);
  if (!frontmatter.name) {
    results.push(fail(`${rel}: frontmatter missing required "name"`));
  } else {
    if (!isValidSkillName(frontmatter.name)) {
      results.push(fail(`${rel}: invalid skill name "${frontmatter.name}"`));
    }
    if (frontmatter.name !== dirName) {
      results.push(fail(`${rel}: frontmatter name "${frontmatter.name}" does not match directory "${dirName}"`));
    }
  }

  const description = frontmatter.description || "";
  if (!description) {
    results.push(fail(`${rel}: frontmatter missing required "description"`));
  } else {
    if (!/(?:Use when|Invoke when)/.test(description)) {
      results.push(fail(`${rel}: description must include "Use when" or "Invoke when" triggers`));
    }
    if (!/(?:当用户需要|中文触发说明)/.test(description)) {
      results.push(fail(`${rel}: description must include Chinese trigger wording`));
    }
  }

  const extraFields = Object.keys(frontmatter).filter((key) => !["name", "description"].includes(key));
  if (extraFields.length > 0) {
    results.push(fail(`${rel}: frontmatter has unsupported field(s): ${extraFields.join(", ")}`));
  }

  const { count, errors } = validateJsonFiles(skillDir);
  for (const error of errors) {
    results.push(fail(error));
  }
  if (errors.length === 0) {
    results.push(pass(`${rel}: JSON resources ok (${count} files)`));
  }

  if (results.every((result) => result.ok)) {
    results.unshift(pass(`${rel}: SKILL.md frontmatter ok`));
  }

  return results;
}

function main() {
  const skillDirs = process.argv.slice(2);
  if (skillDirs.length === 0) {
    usage();
    process.exit(2);
  }

  let failed = false;
  for (const skillDir of skillDirs) {
    const results = validateSkill(skillDir);
    for (const result of results) {
      const marker = result.ok ? "ok" : "error";
      console.log(`${marker}: ${result.message}`);
      if (!result.ok) failed = true;
    }
  }

  process.exit(failed ? 1 : 0);
}

main();
