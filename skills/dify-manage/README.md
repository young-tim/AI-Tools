# dify-manage

Dify 工作流管理 CLI：DSL 拉取/部署、manifest 追踪、外链缓存、文件上传、run/chat。

## 安装

```bash
# GitHub（替换 owner/repo）
npx skills add <owner>/AI-Tools --skill dify-manage -g -y --agent cursor

# 本地
npx skills add ./skills/dify-manage -g -y --agent cursor
# 或从仓库根：npx skills add ./skills/dify-manage ...
```

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

```bash
pull --app-id <uuid>
dsl diff --app-id <uuid>
deploy --app-id <uuid>
cache download "https://..."
files upload ./image.jpg --api-key app-xxx
run --api-key app-xxx --file-url field=https://...
```

详见 [SKILL.md](./SKILL.md)、[reference.md](./reference.md)。
