# AI-Tools

AI 相关工具与 [Agent Skills](https://skills.sh/) 集合。

## Skills 安装

### 让 AI 帮你装（推荐）

复制下面一句话发给当前使用的 AI 编程助手即可，无需自己选 Agent 或记命令：

**安装单个 skill（如 dify-manage）：**

> 请从 GitHub 仓库 [https://github.com/young-tim/AI-Tools](https://github.com/young-tim/AI-Tools) 安装 dify-manage 这个 skill，装到我当前用的 AI 编程工具里。

**安装全部 skill：**

> 请安装 [https://github.com/young-tim/AI-Tools](https://github.com/young-tim/AI-Tools) 仓库里的全部 skill。

### 命令行安装

`<owner>` 替换为 GitHub 用户名，例如 `young-tim`。`-g` 表示安装到用户目录（如 `~/.agents/skills/`），省略则安装到当前项目。

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

## Skills 清单


| Skill                                | 说明                        |
| ------------------------------------ | ------------------------- |
| [decksmith](./skills/decksmith/)     | AI 演示稿编译器：通过 Slide IR 生成企业级幻灯片，内置主题/模板/组件，导出 HTML/PDF/可编辑 PPTX |
| [dify-manage](./skills/dify-manage/) | Dify DSL 拉取/编辑/部署；文件缓存与上传 |


## 仓库结构

```text
AI-Tools/
├── AGENTS.md              # AI Agent 创建/维护 Skill 的规范指南
├── README.md
└── skills/
    └── <skill-name>/
        ├── SKILL.md       # Skill 核心指令（必需）
        ├── README.md      # Skill 使用说明（可选）
        ├── scripts/       # 可执行脚本（可选）
        ├── schema/        # JSON Schema（可选）
        ├── themes/        # 主题配置（可选）
        ├── templates/     # 模板配置（可选）
        ├── components/    # 组件定义（可选）
        └── examples/      # 示例文件（可选）
```

新增/修改 Skill 请阅读 [AGENTS.md](./AGENTS.md) 中的规范。