#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { commonFiles, parseArgs, positiveInteger, renderTemplate, safeTopic, scenarioIds, scenarios } from './research_files.mjs';

try {
  const args = parseArgs(process.argv.slice(2), ['topic', 'question', 'output', 'resume', 'scenario', 'max-rounds', 'no-increment-limit']);
  if (args.help) {
    console.log('Usage: node init_research.mjs --topic "主题" [--question "原始问题"] [--scenario idea,needs,trends,technology,entry,comparison,diagnosis,pilot] [--output "/absolute/run-directory"] [--max-rounds 6] [--no-increment-limit 2]\nResume: node init_research.mjs --resume "/absolute/existing-directory"\n初始化仅生成草稿骨架；默认当前目录/.bor/<主题>/，重名加序号。续跑不修改文件。');
    process.exit(0);
  }
  if (args.resume) {
    if (Object.keys(args).some(key => key !== 'resume')) throw new Error('--resume 不能与新建参数一起使用');
    const root = path.resolve(args.resume);
    if (!fs.statSync(root).isDirectory()) throw new Error('续跑位置不是目录');
    for (const file of commonFiles) {
      const st = fs.lstatSync(path.join(root, file));
      if (!st.isFile() || st.isSymbolicLink()) throw new Error(`续跑缺少普通文件：${file}`);
    }
    console.log(JSON.stringify({ mode: 'resume', run_dir: root, files_modified: false, next: '读取原始问题、全部轮次、证据时效与剩余额度，再继续研究' }, null, 2));
    process.exit(0);
  }
  if (!args.topic?.trim()) throw new Error('新建研究须提供 --topic；主题可由研究问题自动提炼');
  const topic = safeTopic(args.topic);
  const selected = scenarioIds(args.scenario);
  const maxRounds = positiveInteger(args['max-rounds'], 6, '最大轮次');
  const noIncrementLimit = positiveInteger(args['no-increment-limit'], 2, '无增量停止阈值');
  const cwd = process.cwd();
  let root;
  if (args.output) {
    root = path.resolve(args.output);
    if (fs.existsSync(root)) throw new Error('指定目录已存在；续跑请使用 --resume，新研究请指定其他目录');
    fs.mkdirSync(path.dirname(root), { recursive: true });
    fs.mkdirSync(root);
  } else {
    const base = path.join(cwd, '.bor');
    if (fs.existsSync(base) && fs.lstatSync(base).isSymbolicLink()) throw new Error('.bor 是符号链接；请核实位置后使用显式 --output');
    fs.mkdirSync(base, { recursive: true });
    for (let index = 1; index <= 10000; index += 1) {
      const candidate = path.join(base, index === 1 ? topic : `${topic}-${index}`);
      try { fs.mkdirSync(candidate); root = candidate; break; }
      catch (err) { if (err.code !== 'EEXIST') throw err; }
    }
    if (!root) throw new Error('主题重名过多；请换用更具体的主题');
  }
  const values = {
    TOPIC: args.topic.trim(), QUESTION: args.question?.trim() || args.topic.trim(), RUN_DIR: root,
    INVOCATION_DIR: cwd, CREATED_AT: new Date().toISOString(), MAX_ROUNDS: maxRounds,
    NO_INCREMENT_LIMIT: noIncrementLimit, SCENARIOS: selected.length ? selected.map(id => `${id}（${scenarios[id].label}）`).join('、') : '待根据研究问题判断',
  };
  const planned = commonFiles.map(file => ({ file, template: file }));
  for (const id of selected) planned.push(...scenarios[id].required);
  const files = [];
  for (const item of planned) {
    if (files.includes(item.file)) continue;
    const full = path.join(root, item.file);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, renderTemplate(item.template, values), { encoding: 'utf8', flag: 'wx' });
    files.push(item.file);
  }
  console.log(JSON.stringify({ mode: 'new', run_dir: root, scenario_ids: selected, files, delivery_status: 'draft', next: '写入真实研究结果；条件性量化文件须满足数据前提后另行生成' }, null, 2));
} catch (err) {
  console.error(`初始化失败：${err.message}`);
  process.exitCode = 1;
}
