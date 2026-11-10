#!/usr/bin/env node
import process from 'node:process';
import { inspectResearch, parseArgs, scenarioIds } from './research_files.mjs';

try {
  const argv = process.argv.slice(2);
  if (argv.includes('--help')) {
    console.log('Usage: node check_research.mjs "/absolute/run-directory" [--scenario idea,needs,trends,technology,entry,comparison,diagnosis,pilot]\n检查通用文件、草稿标记、轮次与额度、本地链接、证据编号、CSV 和 ODI 计算；--scenario 用于检查对应专项文件。不会验证网页、真实样本或商业有效性。');
    process.exit(0);
  }
  const directory = argv.shift();
  if (!directory || directory.startsWith('--')) throw new Error('须指定研究目录');
  const args = parseArgs(argv, ['scenario']);
  const result = inspectResearch(directory, scenarioIds(args.scenario));
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.ok ? 0 : 1;
} catch (err) {
  console.error(`检查失败：${err.message}`);
  process.exitCode = 1;
}
