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

`-g` 表示安装到用户目录（如 `~/.agents/skills/`），省略则安装到当前项目。

> **注意**：使用 `--all` 或 `--agent '*'` 安装全部 Agent 时，部分 Agent（如 Eve、PromptScript）不支持全局 skill 安装，会出现 `does not support global skill installation` 警告。这些警告不影响其他 Agent（Cursor、Trae、Claude Code 等）的安装成功。建议指定你实际使用的 Agent 来避免无关报错。

```bash
# 列出本仓库所有 skill
npx skills add young-tim/AI-Tools --list

# ── 安装全部 skill ──────────────────────────────────────
# 交互式：选择要装的 skill 和 Agent
npx skills add young-tim/AI-Tools -g

# 非交互：全部 skill → 指定 Agent（推荐，避免不支持的 Agent 报错）
npx skills add young-tim/AI-Tools --all -g -y --agent cursor
npx skills add young-tim/AI-Tools --all -g -y --agent trae

# 非交互：全部 skill → 全部 Agent（可能出现部分 Agent 不支持全局安装的警告）
npx skills add young-tim/AI-Tools --all -g -y
# 等价写法
npx skills add young-tim/AI-Tools --skill '*' --agent '*' -g -y

# ── 安装指定 skill ──────────────────────────────────────
# 交互式：不指定 Agent，CLI 会提示选择
npx skills add young-tim/AI-Tools --skill dify-manage -g

# 指定 Agent（Cursor，用户级，跳过确认）
npx skills add young-tim/AI-Tools --skill dify-manage -g -y --agent cursor

# 指定 Agent（Trae CN）
npx skills add young-tim/AI-Tools --skill dify-manage -g -y --agent trae-cn

# 指定 Agent（OpenAI Codex CLI）
npx skills add young-tim/AI-Tools --skill dify-manage -g -y --agent codex

# 指定 Agent（Claude Code）
npx skills add young-tim/AI-Tools --skill dify-manage -g -y --agent claude

# 指定 skill，安装到全部 Agent（非交互，可能有部分警告）
npx skills add young-tim/AI-Tools --skill dify-manage --agent '*' -g -y

# ── 本地开发 ────────────────────────────────────────────
npx skills add ./skills/dify-manage -g -y --agent cursor
```

## Skills 更新

当本仓库发布新版本后，你可以通过以下方式更新已安装的 Skills：

### 让 AI 帮你更新（推荐）

复制下面一句话发给 AI 编程助手即可：

> 请帮我更新从 [https://github.com/young-tim/AI-Tools](https://github.com/young-tim/AI-Tools) 安装的 skill（如 dify-manage），拉取最新版本。

### 命令行更新

重新执行 `npx skills add` 即可覆盖更新到最新版本：

```bash
# 更新单个 skill（例如 dify-manage）
npx skills add young-tim/AI-Tools --skill dify-manage -g -y --agent cursor

# 更新全部已安装的 skill
npx skills add young-tim/AI-Tools --all -g -y

# 更新到全部 Agent
npx skills add young-tim/AI-Tools --skill dify-manage --agent '*' -g -y
```

### 本地开发更新

如果你是通过本地路径（`./skills/dify-manage`）安装的：
- `.agents/skills/` 是指向 `skills/` 的符号链接，**修改源文件即自动生效，无需重新安装**。
- 如果需要强制刷新链接，可重新执行：
  ```bash
  npx skills add ./skills/dify-manage -g -y --agent cursor
  ```

## Skills 清单


| Skill                                | 说明                        |
| ------------------------------------ | ------------------------- |
| [decksmith](./skills/decksmith/)     | AI 演示稿编译器：直接输出 PPTX-native、高设计感、内容有效、可编辑的客户交付型 PPT（Node.js/PptxGenJS 版本） |
| [ppt-smith](./skills/ppt-smith/)     | AI 演示稿编译器：基于 officecli，直接输出 PPTX-native、高设计感、内容有效、可编辑的客户交付型 PPT（officecli 版本） |
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
