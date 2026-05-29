# AI-Tools

AI 相关工具与 [Agent Skills](https://skills.sh/) 集合。

## 安装

`<owner>` 替换为 GitHub 用户名，例如 `young-tim`。`-g` 表示安装到用户目录（如 `~/.cursor/skills/`），省略则安装到当前项目。

```bash
# 列出本仓库所有 skill
npx skills add <owner>/AI-Tools --list

# ── 安装全部 skill ──────────────────────────────────────
# 交互式：选择要装的 skill 和 Agent
npx skills add <owner>/AI-Tools -g

# 非交互：全部 skill → 全部 Agent
npx skills add <owner>/AI-Tools --all -g -y
# 等价写法
npx skills add <owner>/AI-Tools --skill '*' --agent '*' -g -y

# ── 安装指定 skill ──────────────────────────────────────
# 交互式：不指定 Agent，CLI 会提示选择
npx skills add <owner>/AI-Tools --skill dify-manage -g

# 指定 Agent（Cursor，用户级，跳过确认）
npx skills add <owner>/AI-Tools --skill dify-manage -g -y --agent cursor

# 指定 skill，安装到全部 Agent（非交互）
npx skills add <owner>/AI-Tools --skill dify-manage --agent '*' -g -y

# ── 本地开发 ────────────────────────────────────────────
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

