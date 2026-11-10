import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { commonFiles, evidenceHeaders, inspectResearch, parseCsv, safeTopic, scenarios } from './research_files.mjs';

const init = fileURLToPath(new URL('./init_research.mjs', import.meta.url));
function workspace(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bor-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return fs.realpathSync(dir);
}
function run(cwd, ...args) { return spawnSync(process.execPath, [init, ...args], { cwd, encoding: 'utf8' }); }
function success(result) {
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}
function csv(rows) {
  return rows.map(row => row.map(value => /[",\r\n]/.test(String(value)) ? `"${String(value).replaceAll('"', '""')}"` : value).join(',')).join('\n') + '\n';
}
function delivered(dir) {
  for (const file of commonFiles) fs.writeFileSync(path.join(dir, file), file === 'evidence.csv' ? csv([evidenceHeaders]) : '# 测试产物\n\n待验证。仅用于工具验证，没有真实研究证据。\n');
  fs.writeFileSync(path.join(dir, 'research-log.md'), '# 测试研究记录\n\n## 固定任务信息\n- 最大轮次：2\n- 连续无增量停止阈值：2\n\n## 当前状态\n- 累计轮次：1\n- 连续无增量轮次：1\n- 剩余轮次：1\n\n## 轮次记录\n### 第 1 轮\n完成测试资料的缺口检查，当前待验证。\n');
}
function addEvidence(dir, extra = []) {
  fs.writeFileSync(path.join(dir, 'evidence.csv'), csv([evidenceHeaders,
    ['E001', '测试记录', '', '2026-01-01T00:00:00Z', '测试行1', '测试观测', '仅测试样本', 'C001', '合成测试输入', ''], ...extra]));
}

test('默认使用调用目录且保留中文主题，重名不覆盖', t => {
  const cwd = workspace(t);
  const first = success(run(cwd, '--topic', '收纳需求', '--scenario', 'needs'));
  assert.equal(first.run_dir, path.join(cwd, '.bor', '收纳需求'));
  const report = path.join(first.run_dir, 'report.md');
  fs.writeFileSync(report, '保留已有研究');
  const second = success(run(cwd, '--topic', '收纳需求'));
  assert.equal(second.run_dir, `${first.run_dir}-2`);
  assert.equal(fs.readFileSync(report, 'utf8'), '保留已有研究');
});

test('危险主题不能逃逸 .bor，空白和点路径拒绝', t => {
  const cwd = workspace(t);
  for (const bad of [' ', '.', '..', '///']) assert.throws(() => safeTopic(bad));
  const result = success(run(cwd, '--topic', '../../外部/主题'));
  assert.equal(path.dirname(result.run_dir), path.join(cwd, '.bor'));
  assert.ok(Buffer.byteLength(safeTopic('汉'.repeat(200)), 'utf8') <= 180);
});

test('显式位置不追加主题，已有目录拒绝新建且保留内容', t => {
  const cwd = workspace(t), target = path.join(cwd, 'chosen');
  const result = success(run(cwd, '--topic', '主题', '--output', target));
  assert.equal(result.run_dir, target);
  const before = fs.readFileSync(path.join(target, 'report.md'), 'utf8');
  assert.notEqual(run(cwd, '--topic', '另一个', '--output', target).status, 0);
  assert.equal(fs.readFileSync(path.join(target, 'report.md'), 'utf8'), before);
});

test('续跑不改文件，混合新建参数与缺失文件拒绝', t => {
  const cwd = workspace(t), result = success(run(cwd, '--topic', '续跑'));
  const log = path.join(result.run_dir, 'research-log.md');
  fs.appendFileSync(log, '\n累计轮次：4；剩余轮次：2\n');
  const before = fs.readFileSync(log, 'utf8');
  assert.equal(success(run(cwd, '--resume', result.run_dir)).files_modified, false);
  assert.equal(fs.readFileSync(log, 'utf8'), before);
  assert.notEqual(run(cwd, '--resume', result.run_dir, '--topic', '不应新建').status, 0);
  fs.unlinkSync(path.join(result.run_dir, 'evidence.csv'));
  assert.notEqual(run(cwd, '--resume', result.run_dir).status, 0);
});

test('8类场景创建对应草稿，不自动生成数据依赖文件', t => {
  const cwd = workspace(t);
  for (const [id, config] of Object.entries(scenarios)) {
    const result = success(run(cwd, '--topic', id, '--scenario', id));
    for (const item of config.required) assert.ok(fs.existsSync(path.join(result.run_dir, item.file)));
    for (const item of config.conditional) assert.ok(!fs.existsSync(path.join(result.run_dir, item.file)));
    assert.equal(inspectResearch(result.run_dir, [id]).ok, false, '初始化不能被判为完成');
  }
});

test('未知场景或非法额度在写入前拒绝', t => {
  const cwd = workspace(t);
  assert.notEqual(run(cwd, '--topic', '主题', '--scenario', 'unknown').status, 0);
  assert.notEqual(run(cwd, '--topic', '主题', '--max-rounds', '0').status, 0);
  assert.ok(!fs.existsSync(path.join(cwd, '.bor')));
});

test('拒绝默认 .bor 符号链接，避免误写其他位置', t => {
  const cwd = workspace(t), target = path.join(cwd, 'elsewhere');
  fs.mkdirSync(target); fs.symlinkSync(target, path.join(cwd, '.bor'));
  assert.notEqual(run(cwd, '--topic', '主题').status, 0);
  assert.deepEqual(fs.readdirSync(target), []);
});

test('CSV支持带逗号、换行、转义引号及CRLF，拒绝损坏结构', () => {
  assert.deepEqual(parseCsv('a,b\r\n"含,逗号","两行\n双""引号"\r\n'), [['a', 'b'], ['含,逗号', '两行\n双"引号']]);
  for (const bad of ['a,a\n1,2\n', 'a,b\n1\n', 'a,b\n"未闭合,2', 'a,b\n"a"尾部,b\n']) assert.throws(() => parseCsv(bad));
});

test('无证据的待验证交付可通过结构检查，相关限制仍会提示', t => {
  const cwd = workspace(t); delivered(cwd);
  const result = inspectResearch(cwd);
  assert.equal(result.ok, true, result.errors.join('\n'));
  assert.ok(result.warnings.some(x => x.includes('尚无登记证据')));
  assert.equal(inspectResearch(cwd, ['needs']).ok, false, '指定场景必须核对专项文件');
});

test('检查器发现坏链接、未知及重复证据编号', t => {
  const cwd = workspace(t); delivered(cwd); addEvidence(cwd);
  fs.appendFileSync(path.join(cwd, 'report.md'), '\n依据 E002，[不存在](missing.md)。\n');
  let result = inspectResearch(cwd);
  assert.ok(result.errors.some(x => x.includes('E002')));
  assert.ok(result.errors.some(x => x.includes('missing.md')));
  addEvidence(cwd, [['E001', '测试记录2', '', '2026-01-01', '行2', '测试值', '测试样本', '', '', '']]);
  result = inspectResearch(cwd);
  assert.ok(result.errors.some(x => x.includes('证据编号重复')));
});

test('ODI文件须有真实数据引用结构及一致的比例缩放计算', t => {
  const cwd = workspace(t); delivered(cwd); addEvidence(cwd);
  fs.mkdirSync(path.join(cwd, 'artifacts'));
  fs.writeFileSync(path.join(cwd, 'artifacts/needs-map.md'), '# 仅供工具验证的测试需求地图\n依据 E001，全部输入为合成测试资料。\n');
  const file = path.join(cwd, 'artifacts/odi-results.csv');
  const header = ['outcome_id', 'outcome', 'segment', 'sample_size', 'importance', 'satisfaction', 'opportunity_score', 'scale_max', 'evidence_ids'];
  fs.writeFileSync(file, csv([header, ['O001', '测试结果', '测试细分', '20', '8', '3', '13', '10', 'E001']]));
  assert.equal(inspectResearch(cwd, ['needs']).ok, true);
  fs.writeFileSync(file, csv([header, ['O001', '测试结果', '测试细分', '20', '8', '3', '8', '10', 'E001']]));
  assert.ok(inspectResearch(cwd, ['needs']).errors.some(x => x.includes('机会分数公式')));
});

test('轮次写错位置或删除草稿标记不足以完成交付', t => {
  const cwd = workspace(t); delivered(cwd);
  const file = path.join(cwd, 'research-log.md');
  const correct = fs.readFileSync(file, 'utf8');
  fs.writeFileSync(file, correct.replace('累计轮次：1', '累计轮次：0').replace('剩余轮次：1', '剩余轮次：2').replace(/### 第 1 轮[\s\S]*/, '尚未记录。\n'));
  fs.writeFileSync(path.join(cwd, 'misplaced-log.md'), correct);
  assert.ok(inspectResearch(cwd).errors.some(x => x.includes('本主题文件中保存至少一轮')));
});

test('额度与轮次数冲突、重复轮次不能通过检查', t => {
  const cwd = workspace(t); delivered(cwd);
  const file = path.join(cwd, 'research-log.md');
  const correct = fs.readFileSync(file, 'utf8');
  fs.writeFileSync(file, correct.replace('剩余轮次：1', '剩余轮次：2'));
  assert.ok(inspectResearch(cwd).errors.some(x => x.includes('剩余轮次须等于')));
  fs.writeFileSync(file, correct.replace('累计轮次：1', '累计轮次：2').replace('剩余轮次：1', '剩余轮次：0') + '\n### 第 1 轮\n重复测试记录。\n');
  assert.ok(inspectResearch(cwd).errors.some(x => x.includes('连续编号')));
});
