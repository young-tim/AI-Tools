# AI-Tools

AI 相关工具与 [Agent Skills](https://skills.sh/) 集合。

## 安装

```bash
# 列出本仓库所有 skill
npx skills add <owner>/AI-Tools --list

# 安装指定 skill（Cursor 用户级）
npx skills add <owner>/AI-Tools --skill dify-manage -g -y --agent cursor

# 本地开发
npx skills add ./skills/dify-manage -g -y --agent cursor
```

## Skills

| Skill | 说明 |
|-------|------|
| [dify-manage](./skills/dify-manage/) | Dify DSL 拉取/编辑/部署；文件缓存与上传 |

## 仓库结构

```text
AI-Tools/
├── README.md
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        ├── README.md
        └── scripts/ ...
```

新增 skill：在 `skills/` 下复制 `dify-manage` 骨架，改 `SKILL.md` frontmatter 即可。

业务项目数据（`.dify/`、`.env`）不放在本仓库，由使用方项目维护。
