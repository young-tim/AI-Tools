import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const templateDir = fileURLToPath(new URL('../templates/', import.meta.url));
export const commonFiles = ['README.md', 'report.md', 'action-plan.md', 'evidence.csv', 'research-log.md'];
export const evidenceHeaders = ['evidence_id', 'source', 'source_date', 'collected_at', 'locator', 'excerpt_or_value', 'population_scope', 'claim_ids', 'limitations', 'conflicts'];
export const scenarios = JSON.parse(fs.readFileSync(path.join(templateDir, 'scenarios.json'), 'utf8'));

export function parseArgs(argv, allowed) {
  const values = {};
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === '--help') { values.help = true; continue; }
    const key = flag.startsWith('--') ? flag.slice(2) : '';
    if (!allowed.includes(key)) throw new Error(`未知参数：${flag}；使用 --help 查看用法`);
    if (Object.hasOwn(values, key)) throw new Error(`参数重复：${flag}`);
    const value = argv[++i];
    if (!value || value.startsWith('--')) throw new Error(`参数缺少值：${flag}`);
    values[key] = value;
  }
  return values;
}

export function scenarioIds(value = '') {
  const ids = [...new Set(value.split(',').map(x => x.trim()).filter(Boolean))];
  for (const id of ids) {
    if (!Object.hasOwn(scenarios, id)) throw new Error(`未知场景：${id}；可选：${Object.keys(scenarios).join(', ')}`);
  }
  return ids;
}

export function safeTopic(topic) {
  let name = topic.normalize('NFKC').replace(/[\u0000-\u001f\u007f<>:"/\\|?*]/g, '-')
    .replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^[. -]+|[. -]+$/g, '');
  while (Buffer.byteLength(name, 'utf8') > 180) name = [...name].slice(0, -1).join('');
  if (!name) throw new Error('研究主题不能是空白、点路径或仅包含无效字符');
  return name;
}

export function positiveInteger(value, fallback, label) {
  if (value === undefined) return fallback;
  if (!/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(Number(value))) throw new Error(`${label}须为正整数`);
  return Number(value);
}

export function renderTemplate(filename, values) {
  const template = fs.readFileSync(path.join(templateDir, filename), 'utf8');
  return template.replace(/\{\{([A-Z_]+)\}\}/g, (token, key) => {
    if (!Object.hasOwn(values, key)) throw new Error(`模板变量未定义：${token}`);
    return String(values[key]).replace(/[\r\n]+/g, ' ');
  });
}

// Strict CSV parsing: quoted commas/newlines and escaped double quotes are supported.
export function parseCsv(input) {
  const text = input.replace(/^\uFEFF/, '');
  const rows = [];
  let row = [], cell = '', quoted = false, closedQuote = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i += 1; }
        else { quoted = false; closedQuote = true; }
      } else cell += ch;
      continue;
    }
    if (ch === '"') {
      if (cell || closedQuote) throw new Error('CSV 引号必须位于字段开头');
      quoted = true;
    } else if (ch === ',') {
      row.push(cell); cell = ''; closedQuote = false;
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i += 1;
      row.push(cell); rows.push(row); row = []; cell = ''; closedQuote = false;
    } else {
      if (closedQuote) throw new Error('CSV 闭合引号后存在多余字符');
      cell += ch;
    }
  }
  if (quoted) throw new Error('CSV 引号未闭合');
  if (cell || row.length || closedQuote) { row.push(cell); rows.push(row); }
  if (!rows.length || !rows[0].length || rows[0].some(x => !x.trim())) throw new Error('CSV 缺少有效表头');
  if (new Set(rows[0]).size !== rows[0].length) throw new Error('CSV 表头重复');
  rows.slice(1).forEach((r, i) => {
    if (r.length !== rows[0].length) throw new Error(`CSV 第 ${i + 2} 行列数与表头不一致`);
  });
  return rows;
}

function section(text, heading) {
  const start = new RegExp(`^## ${heading}[^\\n]*\\n`, 'm').exec(text);
  if (!start) return '';
  const rest = text.slice(start.index + start[0].length);
  const end = rest.search(/^## /m);
  return end < 0 ? rest : rest.slice(0, end);
}

function checkRoundState(text, errors) {
  const fixed = section(text, '固定任务信息');
  const current = section(text, '当前状态');
  const history = section(text, '轮次记录');
  function numberField(block, label) {
    const matches = [...block.matchAll(new RegExp(`^\\s*[-*]?\\s*${label}\\s*[：:]\\s*(\\d+)\\s*$`, 'gm'))];
    if (matches.length !== 1 || !Number.isSafeInteger(Number(matches[0][1]))) {
      errors.push(`research-log.md：${label}须为唯一明确的整数`);
      return null;
    }
    return Number(matches[0][1]);
  }
  const max = numberField(fixed, '最大轮次');
  const limit = numberField(fixed, '连续无增量停止阈值');
  const done = numberField(current, '累计轮次');
  const noIncrement = numberField(current, '连续无增量轮次');
  const remaining = numberField(current, '剩余轮次');
  const records = [...history.matchAll(/^###\s+第\s*(\d+)\s*轮(?:[^\n]*)$/gm)].map(m => Number(m[1]));
  if (max !== null && max < 1 || limit !== null && limit < 1) errors.push('research-log.md：研究上限和停止阈值须为正整数');
  if (done !== null && (done < 1 || records.length !== done || records.some((n, i) => n !== i + 1))) {
    errors.push('research-log.md：须在本主题文件中保存至少一轮记录，连续编号且与累计轮次一致');
  }
  if (max !== null && done !== null && remaining !== null && (done > max || remaining !== max - done)) {
    errors.push('research-log.md：剩余轮次须等于最大轮次减累计轮次，且不得超额');
  }
  if (noIncrement !== null && done !== null && noIncrement > done) errors.push('research-log.md：连续无增量轮次不得超过累计轮次');
}

export function inspectResearch(directory, selected = []) {
  const root = path.resolve(directory);
  const errors = [], warnings = [], markdown = [], csvFiles = [];
  function read(file) {
    const full = path.join(root, file);
    try {
      const st = fs.lstatSync(full);
      if (!st.isFile() || st.isSymbolicLink()) throw new Error('不是普通文件');
      const value = fs.readFileSync(full, 'utf8');
      if (!value.trim()) throw new Error('文件为空');
      return value;
    } catch (err) { errors.push(`${file}：${err.message}`); return null; }
  }
  const needed = new Set(commonFiles);
  for (const id of selected) {
    if (!Object.hasOwn(scenarios, id)) { errors.push(`未知场景：${id}`); continue; }
    for (const item of scenarios[id].required) needed.add(item.file);
  }
  for (const file of needed) {
    const text = read(file);
    if (text !== null) (file.endsWith('.csv') ? csvFiles : markdown).push({ file, text });
  }
  function walkArtifacts(dir, prefix = 'artifacts') {
    if (!fs.existsSync(dir)) return;
    if (fs.lstatSync(dir).isSymbolicLink()) { errors.push(`${prefix}：不检查符号链接目录`); return; }
    for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = `${prefix}/${item.name}`;
      if (item.isDirectory()) walkArtifacts(path.join(dir, item.name), file);
      else if (!needed.has(file) && /\.(md|csv)$/.test(item.name)) {
        const text = read(file);
        if (text !== null) (file.endsWith('.csv') ? csvFiles : markdown).push({ file, text });
      }
    }
  }
  try { walkArtifacts(path.join(root, 'artifacts')); }
  catch (err) { errors.push(`artifacts：${err.message}`); }
  const log = markdown.find(x => x.file === 'research-log.md');
  if (log) checkRoundState(log.text, errors);
  const tables = new Map();
  for (const { file, text } of csvFiles) {
    try {
      const rows = parseCsv(text);
      if (file !== 'evidence.csv' && rows.length === 1) throw new Error('专项产物只有表头，尚未形成结果');
      tables.set(file, rows);
    } catch (err) { errors.push(`${file}：${err.message}`); }
  }
  const ids = new Set();
  const evidence = tables.get('evidence.csv');
  if (evidence) {
    if (JSON.stringify(evidence[0]) !== JSON.stringify(evidenceHeaders)) errors.push('evidence.csv：表头须与输出规范一致');
    else {
      for (const row of evidence.slice(1)) {
        const record = Object.fromEntries(evidenceHeaders.map((key, i) => [key, row[i]]));
        if (!/^E\d{3,}$/.test(record.evidence_id)) errors.push(`证据编号无效：${record.evidence_id}`);
        if (ids.has(record.evidence_id)) errors.push(`证据编号重复：${record.evidence_id}`);
        ids.add(record.evidence_id);
        for (const key of ['source', 'collected_at', 'locator', 'excerpt_or_value', 'population_scope']) {
          if (!record[key].trim()) errors.push(`${record.evidence_id}：缺少 ${key}`);
        }
      }
      if (evidence.length === 1) {
        warnings.push('尚无登记证据；只能交付待验证发现和补证计划');
        const report = markdown.find(x => x.file === 'report.md')?.text || '';
        if (!report.includes('待验证')) errors.push('没有登记证据时，主报告须明确标记待验证');
      }
    }
  }
  for (const { file, text } of [...markdown, ...csvFiles.filter(x => x.file !== 'evidence.csv')]) {
    if (/BOR_DRAFT|\{\{[A-Z_]+\}\}|\bTODO\b|待填写/.test(text)) errors.push(`${file}：仍含初始化或未完成占位标记`);
    for (const id of new Set(text.match(/\bE\d{3,}\b/g) || [])) {
      if (!ids.has(id)) errors.push(`${file}：引用未登记证据 ${id}`);
    }
    if (!file.endsWith('.md')) continue;
    for (const link of text.matchAll(/!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+"[^"]*")?\s*\)/g)) {
      const target = link[1] || link[2];
      if (/^[a-z][a-z\d+.-]*:/i.test(target) || target.startsWith('#')) continue;
      try {
        const local = decodeURIComponent(target.split('#')[0]);
        const resolved = path.resolve(root, path.dirname(file), local);
        if (!fs.existsSync(resolved)) errors.push(`${file}：本地链接不存在 ${target}`);
      } catch { errors.push(`${file}：无法解析本地链接 ${target}`); }
    }
  }
  const odi = tables.get('artifacts/odi-results.csv');
  if (odi) {
    const expected = ['outcome_id', 'outcome', 'segment', 'sample_size', 'importance', 'satisfaction', 'opportunity_score', 'scale_max', 'evidence_ids'];
    if (JSON.stringify(odi[0]) !== JSON.stringify(expected)) errors.push('odi-results.csv：表头须与输出规范一致');
    else odi.slice(1).forEach((row, index) => {
      const [, outcome, segment, sample, importance, satisfaction, score, scale, refs] = row;
      const [i, s, o] = [importance, satisfaction, score].map(Number);
      if (!outcome.trim() || !segment.trim() || !/^[1-9]\d*$/.test(sample) || !importance.trim() || !satisfaction.trim() || !score.trim() ||
          ![i, s, o].every(Number.isFinite) || Number(scale) !== 10 || i < 0 || i > 10 || s < 0 || s > 10 || Math.abs(o - (i + Math.max(i - s, 0))) > 0.02 ||
          !(refs.match(/\bE\d{3,}\b/g) || []).some(id => ids.has(id))) {
        errors.push(`odi-results.csv 第 ${index + 2} 行：检查真实样本、0～10 量表、机会分数公式和证据引用`);
      }
    });
  }
  warnings.push('仅检查本地结构；未验证网页可达性、样本真实性、因果识别或商业结论');
  return { ok: errors.length === 0, run_dir: root, errors, warnings };
}
