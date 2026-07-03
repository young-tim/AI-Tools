# AI-Tools 项目 Agent 指南

本文档为 AI 编程助手在本仓库中创建和维护 Skills 时必须遵守的规范。

## Skill 创建规范

所有 Skills 必须遵循 [npx skills](https://skills.sh/) 生态规范，并满足本仓库的额外要求。

### 目录结构

本仓库采用**多 Skill Monorepo** 结构，所有 Skills 位于 `skills/` 目录下。`.agents/skills/` 通过符号链接自动指向 `skills/`，无需手动同步：

```text
AI-Tools/
├── AGENTS.md              # 本文件（AI 行为规范）
├── README.md              # 项目说明与 Skills 清单
├── .agents/skills/        # 符号链接，自动指向 skills/，无需手动操作
└── skills/
    └── <skill-name>/
        ├── SKILL.md       # 必需：Skill 核心指令文件
        ├── README.md      # 可选：Skill 使用说明
        ├── scripts/       # 可选：可执行脚本目录
        ├── schema/        # 可选：JSON Schema 定义
        ├── themes/        # 可选：主题配置
        ├── templates/     # 可选：模板配置
        ├── components/    # 可选：组件定义
        └── examples/      # 可选：示例文件
```

### SKILL.md 规范

SKILL.md 是 Skill 的核心入口，**必须**包含 YAML frontmatter：

```markdown
---
name: <skill-name>
description: >-
  英文功能描述，说明该 Skill 做什么。Use when <触发条件1>, <触发条件2>, or any
  <场景关键词>. 中文触发说明：当用户需要<中文场景>时触发。
---

# <Skill 名称>

## 功能说明

## 何时使用

## 工作流程

## 参考资源（引用本目录下其他文件）
```

**Frontmatter 要求：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | Skill 唯一标识，小写字母+连字符，与目录名一致 |
| `description` | 是 | 必须同时包含英文描述和中文触发词，格式：`<英文功能说明>. 当用户需要<中文场景>时触发。` |

**description 编写规则：**
- 开头用英文说明 Skill 功能
- 必须包含 `Use when` 或 `Invoke when` 列出典型触发场景
- 结尾必须包含中文触发说明
- 列出所有相关关键词（中英文），便于 AI 路由匹配

### 品牌中立性

本仓库是开源项目，所有 Skill **禁止**包含：
- 特定公司/品牌名称（使用 `[Your Brand]`、`[Company Name]` 等占位符）
- 内部域名、私有 API 地址
- 个人身份信息

### 文件引用

SKILL.md 中引用同目录下其他文件时，使用 `{SKILL_ROOT}` 占位符表示 Skill 根目录：

```markdown
Schema 定义位于 `{SKILL_ROOT}/schema/presentation.schema.json`
```

安装后 `{SKILL_ROOT}` 会被替换为实际路径。

### JSON 文件规范

所有 JSON 配置文件（schema、themes、templates、components、examples）：
- 必须通过 JSON 语法校验（可使用 `python3 -c "import json; json.load(open('file.json'))"` 验证）
- 字符串中禁止使用未转义的双引号
- 中文描述使用中文标点，但注意 JSON 字符串内的引号需转义或避免使用

## 创建新 Skill 的流程

**必须严格按以下步骤执行：**

1. **规划 Skill**：明确功能范围、触发场景、依赖资源
2. **创建目录**：在 `skills/` 下创建 `<skill-name>/` 目录
3. **编写 SKILL.md**：包含正确的 frontmatter，description 中英文触发词完整
4. **添加资源文件**：scripts/schema/themes/templates/components/examples 等按需创建
5. **语法校验**：所有 JSON 文件必须通过语法验证
6. **本地测试**：
   ```bash
   # 验证 Skill 能被识别
   npx skills add ./skills/<skill-name> --list
   # 验证能被加载
   npx skills use ./skills/<skill-name>
   ```
7. **更新 README.md**：在「Skills 清单」表格中添加新 Skill 条目

**注意**：由于 `.agents/skills/` 是符号链接，修改 `skills/` 下的文件会自动生效，无需手动同步。

## 修改现有 Skill 的流程

1. 修改 `skills/<skill-name>/` 下的源文件
2. 如涉及 JSON 文件，运行语法校验
3. 如新增/删除 Skill 或修改了说明，更新 README.md 清单

## Skills 清单维护

README.md 中的 Skills 清单表格必须与 `skills/` 目录保持同步：

```markdown
| Skill                                | 说明                        |
| ------------------------------------ | ------------------------- |
| [decksmith](./skills/decksmith/)     | AI 演示稿编译器，生成 PPT/PDF/HTML |
| [dify-manage](./skills/dify-manage/) | Dify DSL 拉取/编辑/部署；文件缓存与上传 |
```

- 新增 Skill 时必须添加一行
- 删除 Skill 时必须移除对应行
- 功能变更时更新说明列

## 禁止事项

- ❌ 不要在 SKILL.md 中硬编码品牌名称或私有信息
- ❌ 不要提交包含语法错误的 JSON 文件
- ❌ 不要在 Skill 中引入未在说明中提及的系统级依赖（如需依赖，需在 SKILL.md 中明确说明安装方式）
- ❌ 不需要手动同步到 `.agents/skills/`（符号链接自动生效）
