# dify-manage

Dify 工作流管理 CLI：DSL 拉取/部署、manifest 追踪、外链缓存、文件上传、run/chat。

## 业务项目初始化

在业务仓库根目录：

```bash
# 1. 配置 .env（见 .env.example）
# 2. 初始化 .dify/
python3 "<SKILL_ROOT>/scripts/dify_manage.py" init
python3 "<SKILL_ROOT>/scripts/dify_manage.py" login
python3 "<SKILL_ROOT>/scripts/dify_manage.py" apps
```

## 常用命令

> **两种等价形式任选其一**：下划线 `父_子` 形式（AI 调用推荐，无歧义不会报「命令不存在」）或 空格 `父 子` 形式（人类终端/老脚本兼容，100% 等价）。示例：`dsl_diff` ≡ `dsl diff`、`cache_download` ≡ `cache download`、`files_upload` ≡ `files upload`。

```bash
# 一级命令（无组合，天然只有一级）
pull --app-id <uuid>
deploy --app-id <uuid>
apps
run --api-key app-xxx --file-url field=https://...

# DSL / cache / files 命令（两种形式等价，AI 推荐下划线写法）
dsl_diff --app-id <uuid>                                 # 或：dsl diff --app-id <uuid>
dsl_status --check-remote --app-id <uuid>                # 或：dsl status --check-remote --app-id <uuid>
cache_download "https://..."                             # 或：cache download "https://..."
files_upload ./image.jpg --api-key app-xxx               # 或：files upload ./image.jpg --api-key app-xxx
```

详见 [SKILL.md](./SKILL.md)、[reference.md](./reference.md)。
