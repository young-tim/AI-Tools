---
name: dify-manage
description: >-
  Manages Dify via bundled CLI: pull/export DSL, patch working.yml, deploy,
  cache remote files, upload to Dify, run/chat workflows. Use when the user
  mentions Dify, workflow DSL, pull, deploy, dify-manage, or Dify file inputs.
  当用户需要管理 Dify 工作流 DSL、拉取、编辑、部署、文件缓存、文件上传、运行或调试 Dify 应用时触发。
---

# Dify 管理

## CLI

**SKILL_ROOT** = 本 `SKILL.md` 所在目录（安装后通常在 `~/.cursor/skills/dify-manage/`）。

```bash
# 基命令（后续命令均接在此后）
python3 "{SKILL_ROOT}/scripts/dify_manage.py" <命令> [选项]
# 或："{SKILL_ROOT}/scripts/dify" <命令> [选项]
```

**两种等价调用形式（任选其一，全部命令都支持）：**

| 形式 | 说明 | 示例 |
|---|---|---|
| **下划线 `父_子`（推荐，AI 友好无歧义）** | 所有 DSL / cache / files 命令都有独立的一级别名，不会误触发「命令不存在」 | `dsl_status`、`dsl_diff`、`cache_download`、`files_upload` |
| 空格 `父 子`（人类习惯写法，完全兼容） | 原有两级结构继续保留，老脚本 / 终端肌肉记忆不受影响 | `dsl status`、`dsl diff`、`cache download`、`files upload` |

除这 9 个别名命令外的其他命令（`init`、`login`、`pull`、`deploy`、`apps`、`run`、`chat` 等）天然只有一级，不存在形式差异。

业务项目内可自建 `bin/dify` 包装，启动时 `cd` 到项目根以发现 `.env` / `.dify/`。

## 首次使用（业务项目根目录）

先 `cd` 到含 `.env` 的业务仓库根，再执行：

```bash
# 1. 配置 .env（见 skill 内 .env.example）
# 2. 初始化 .dify/ 骨架（dsl、cache、manifest 等）
python3 "{SKILL_ROOT}/scripts/dify_manage.py" init

# 3. 需要 Console 操作时（须用户确认）
python3 "{SKILL_ROOT}/scripts/dify_manage.py" login

# 4. 列出应用
python3 "{SKILL_ROOT}/scripts/dify_manage.py" apps
```

`login` 也会自动创建 `.dify/` 并写入 `session.json`，但不会建好 `dsl/`、`cache/` 等子目录；**首次务必先 `init`**。

## 项目布局（使用方仓库，非本 skill）

| 路径 | 内容 | Git |
|------|------|-----|
| `.env` | `DIFY_CONSOLE_URL`、`DIFY_BASE_URL` | 真实 ignore |
| `.dify/session.json` | Console token | **ignore** |
| `.dify/manifest.yml` | 应用索引、hash | 建议提交 |
| `.dify/dsl/{app_id}/` | `{ts}-remote.yml`、`working.yml` | remote ignore |
| `.dify/apps/{app_id}.yml` | 业务元数据 | 按需 |
| `.dify/fixtures/{app_id}/` | `smoke.json`、`assets/` | 按需 |
| `.dify/cache/downloads/` | `{md5(url)}-{name}` | **ignore** |

## Token 优先级

`OS env` > `.dify/session.json` > `.env` token。`login`/`refresh` 只写 `session.json`。

## 安全

- 未指定 app → `apps` 确认
- deploy/login 须用户确认
- `--app-id`、`--api-key` 每次传入
- skill 内不固化业务 URL、token、应用名

## DSL 工作流（推荐下划线写法，空格写法同样兼容）

```bash
python3 "{SKILL_ROOT}/scripts/dify_manage.py" init
python3 "{SKILL_ROOT}/scripts/dify_manage.py" apps
python3 "{SKILL_ROOT}/scripts/dify_manage.py" pull --app-id <id>
# 编辑 .dify/dsl/<id>/working.yml
python3 "{SKILL_ROOT}/scripts/dify_manage.py" dsl_diff --app-id <id>     # 等价：dsl diff --app-id <id>
python3 "{SKILL_ROOT}/scripts/dify_manage.py" dsl_validate --app-id <id> --checklist   # 上线前静态校验 + Dify 官方检查清单 1:1 模拟器；等价 dsl validate --checklist
python3 "{SKILL_ROOT}/scripts/dify_manage.py" deploy --app-id <id>
# deploy 默认自动触发前置 gate（静态校验 + 清单）：invalid_var≥1 / handle 缺失率≥50% / 孤立节点≥80% 会阻断；
# 确认风险后可加 --skip-validate / --skip-checklist 绕过，或 --checklist-warn-only 放宽阻断为告警
# deploy **publish 成功后还会自动回拉 remote 做内容完整性校验（P0兜底 Dify 后端静默丢 35 条边的 bug）**：
#   默认最多自动重新 import+publish 1 次（瞬态丢边一般重试即恢复）；
#   可用 --post-verify-retry N 调重试次数，或 --skip-post-verify 完全跳过（不推荐）
```

维护：`dsl_refresh`（更新 working 哈希）、`dsl_reset`（回滚 working 到最新 remote）、`dsl_prune --keep 3`（清理旧 remote 快照）、`pull --sync-working`。以上命令均有下划线和空格两种等价形式。

## 文件工作流（推荐下划线写法，空格写法同样兼容）

```bash
cache_download "https://example.com/a.jpg"                                    # 等价：cache download "..."
files_upload path-or-url --api-key app-xxx                                    # 等价：files upload ...
run --api-key app-xxx --file-url product_image=https://...
run --api-key app-xxx --fixtures .dify/fixtures/<id>/smoke.json
```

## DSL 规则

- 改前 `pull`；只 patch 目标节点
- 禁止旧 YAML 整包覆盖
- deploy 前先跑 `dsl_diff`；注意 `default` / `file_upload` 字段变更风险

## Agent 清单

> **原则：AI 生成命令时优先使用下划线形式（`dsl_status`、`cache_download`、`files_upload` 等），避免触发「命令不存在」；人类用户和已有脚本可继续使用空格形式（`dsl status` 等），两者 100% 等价。**

1. 首次使用：在业务项目根执行 `init`（见上文「首次使用」完整命令）
2. 未指定 app → `apps`
3. 改 DSL 前 `pull`；编辑 `working.yml`
4. 部署前先跑 `dsl_validate --checklist --app-id <id>`（**已作为 deploy 前置 gate 默认自动触发**），确认无 invalid_var 节点、handle 缺失率 < 50%、孤立节点 < 80%，再跑 `dsl_diff --app-id <id>` 对比差异；**deploy publish 成功后还会回拉 remote 做 nodes/edges 4 维度完整性校验，默认自动重试 1 次兜底 Dify 后端静默丢边，校验失败不阻塞仅 stderr 告警**；异常定位用 `dsl_status --check-remote --app-id <id>`。用户明确确认风险后，可加 `--skip-validate` / `--skip-checklist` / `--skip-post-verify` 绕过 gates，或 `--checklist-warn-only` 放宽阻断为告警、`--post-verify-retry N` 改重试次数
5. 外链：`cache_download <url>` → `files_upload <path-or-url> --api-key app-xxx` 或 `run --file-url`
6. 敏感操作（login / deploy / import / publish）**须用户确认**后再执行
7. 无用户明确要求不主动执行 `login`

## 参考

[reference.md](reference.md)
