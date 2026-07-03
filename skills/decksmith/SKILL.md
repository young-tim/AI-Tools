---
name: decksmith
description: >-
  AI Presentation Compiler: generates enterprise slides, PPT, decks, proposals, reports,
  and reviews via Slide IR (structured JSON), with built-in themes, templates, and components.
  Exports high-fidelity HTML preview, PDF for delivery, and editable PPTX. Use when creating
  presentations, slides, pitch decks, proposals, project reports, meeting slides, or any
  slide-based deliverable. 当用户需要制作演示稿、幻灯片、PPT、方案、报告、汇报、提案时触发。
---

# DeckSmith — AI Presentation Compiler

## 核心理念

DeckSmith 是面向 AI 的演示稿编译与交付引擎。核心方法：**Schema First, HTML Rendered, PPTX Compiled**。

- **Slide IR** 是唯一可信结构化源（不是 HTML，也不是 PPTX）
- **HTML** 是高保真预览层，也是 PDF 输出基础
- **PDF** 是稳定交付层，适合打印、归档、客户交付
- **PPTX** 是混合可编辑交付层，核心内容保留原生对象

AI 不直接操作 PowerPoint 底层坐标、XML、母版；AI 专注于内容逻辑、叙事结构、版式选择和组件填充，系统负责编译为稳定可交付文件。

---

## 强制工作流程

**必须严格按以下顺序执行，不得跳过任何步骤：**

1. **读取需求**：解析用户需求、Markdown 文档、大纲、JSON 数据或业务输入
2. **定义场景**：识别演示目标、受众、场景、语气和风格要求
3. **生成大纲**：先构建演示稿大纲，确定整体叙事结构
4. **定义核心结论**：为每页明确一个核心结论/表达目标
5. **选择版式组件**：根据内容目的选择 Layout 和 Component，不得平均使用卡片页
6. **生成 Slide IR**：输出结构化 JSON 作为唯一可信源
7. **Schema 校验**：验证 Schema 合法性、内容密度、组件兼容性、资产引用
8. **渲染 HTML**：输出到 `.decksmith/presentation.html`，高保真预览
9. **HTML QA**：检测文本溢出、元素重叠、越界、图片缺失、字体问题
10. **导出 PDF**：输出到 `.decksmith/presentation.pdf`，无边距、高保真
11. **编译 PPTX**：输出到 `.decksmith/presentation.pptx`，核心内容原生可编辑
12. **PPTX 回渲**：将 PPTX 渲染为图片进行视觉对比
13. **视觉 QA**：比对 HTML 与 PPTX 截图，生成差异图和 QA 报告
14. **问题修复**：优先压缩文本 → 调整布局 → 切换 Layout → 拆页 → 微调字号 → SVG/图片回退
15. **写入清单**：生成 `manifest.json`，完成交付

**重要：必须先确定内容逻辑，再选择视觉模板；不得先选模板再强行填内容。**

---

## 输出工作空间

所有输出**必须**写入项目根目录或指定目录下的 `.decksmith/`，不得散落到项目根目录。

### 必需输出文件

```text
.decksmith/
├── presentation.json          # Slide IR（唯一结构化源）
├── presentation.html          # HTML 预览
├── presentation.pdf           # PDF 交付
├── presentation.pptx          # PPTX 交付
├── manifest.json              # 构建清单
├── source/
│   ├── brief.md               # 原始需求快照
│   ├── outline.json           # AI 生成的大纲
│   ├── theme.json             # 主题快照
│   ├── template.json          # 模板快照
│   └── data.json              # 原始数据
├── assets/
│   ├── images/                # 图片、产品图、背景图
│   ├── icons/                 # SVG/PNG 图标
│   ├── charts/                # 图表
│   ├── fonts/                 # 字体
│   └── generated/             # AI 生成素材
├── previews/
│   ├── html/                  # HTML 截图
│   ├── pptx/                  # PPTX 回渲截图
│   └── diff/                  # 视觉差异图
├── qa/
│   ├── qa-report.json         # 总体 QA 报告
│   ├── html-layout-report.json
│   ├── pptx-visual-diff.json
│   └── issues/                # 问题截图
├── cache/                     # 缓存（不提交 Git）
└── logs/                      # 日志（不提交 Git）
```

### .gitignore 建议

```gitignore
.decksmith/cache/
.decksmith/logs/
.decksmith/previews/
.decksmith/qa/issues/
```

---

## 页面尺寸与坐标体系

V1 默认使用 **16:9 宽屏**：

| 项目 | HTML | PPTX |
|------|------|------|
| 画布尺寸 | 1920 × 1080 px | 13.333 × 7.5 in |
| 换算比例 | 1 inch = 144 px |  |
| 字号换算 | PPT pt = HTML px × 0.75 |  |

### 字号对应表

| HTML | PPT | 用途 |
|-----:|----:|------|
| 64px | 48pt | 封面标题 |
| 56px | 42pt | 章节标题 |
| 48px | 36pt | 页面标题 |
| 40px | 30pt | 页面标题 |
| 32px | 24pt | 正文大 |
| 24px | 18pt | 正文 |
| 20px | 15pt | 正文小 |
| 18px | 13.5pt | 最小字号（不得低于） |

### 安全边距

```text
左/右：96px
上/下：72px
```

**核心内容不得超出安全边距。**

---

## Slide IR 数据模型

### 演示稿根结构

```json
{
  "version": "1.0",
  "meta": {
    "title": "演示稿标题",
    "author": "作者",
    "language": "zh-CN",
    "ratio": "16:9",
    "createdAt": "2026-07-03"
  },
  "theme": "enterprise-light",
  "template": "business-consulting",
  "settings": {
    "canvasWidth": 1920,
    "canvasHeight": 1080,
    "pptLayout": "LAYOUT_WIDE",
    "editablePriority": "hybrid",
    "exportHtml": true,
    "exportPdf": true,
    "exportPptx": true
  },
  "assets": [],
  "slides": []
}
```

### 单页 Slide 结构

```json
{
  "id": "slide-03",
  "type": "comparison",
  "layout": "two-column-comparison",
  "title": "页面标题（必须是结论式）",
  "subtitle": "副标题/补充说明",
  "themeVariant": "light",
  "components": [],
  "notes": "演讲备注",
  "qa": {
    "maxTextDensity": "medium",
    "allowRasterFallback": true
  }
}
```

**重要：Slide IR 中不得保存大段任意 CSS；所有视觉表现由 Theme、Layout、Component、Variant 控制。**

---

## 可用主题（V1 内置）

| 主题 ID | 名称 | 适用场景 |
|---------|------|----------|
| `default-light` | 默认浅色 | 通用演示 |
| `default-dark` | 默认深色 | 深色模式 |
| `enterprise-light` | 企业浅色咨询 | 企业咨询、正式汇报 |
| `business-blue` | 商务蓝 | 商务提案、客户演示 |
| `tech-gradient` | 科技渐变 | 技术分享、产品发布 |

---

## 可用 Layout（V1 必须支持）

| Layout ID | 使用场景 |
|-----------|----------|
| `cover` | 项目封面、品牌封面 |
| `section` | 章节过渡页 |
| `agenda` | 目录页 |
| `single-message` | 单一结论页 |
| `two-column` | 双栏内容页 |
| `three-card` | 三卡片信息页 |
| `image-text` | 图文组合页 |
| `comparison` | 对比分析页 |
| `kpi-dashboard` | 指标数据页 |
| `process-flow` | 流程图页 |
| `timeline` | 时间轴页 |
| `roadmap` | 实施路线图页 |
| `architecture` | 技术/业务架构页 |
| `matrix` | 四象限矩阵页 |
| `funnel` | 漏斗模型页 |
| `table-report` | 表格报告页 |
| `summary` | 总结与行动项页 |
| `qa` | 问答/结束页 |

---

## 可用 Component（V1 必须支持）

| Component ID | 说明 | PPTX 策略 |
|--------------|------|-----------|
| `title` | 页面标题 | 原生文本框 |
| `subtitle` | 页面副标题 | 原生文本框 |
| `body-text` | 正文段落 | 原生文本框 |
| `bullet-list` | 要点列表 | 原生文本框 |
| `metric-card` | 指标卡片 | 原生形状+文本 |
| `image` | 图片/产品图/截图 | 原生图片 |
| `icon` | 图标 | SVG/PNG |
| `comparison-panel` | 对比卡片 | 原生形状+文本 |
| `process-node` | 流程节点 | 原生形状+文本+连线 |
| `timeline-node` | 时间轴节点 | 原生形状+文本 |
| `table` | 数据表格 | 原生表格/形状组合 |
| `bar-chart` | 柱状图 | 原生图表优先 |
| `line-chart` | 折线图 | 原生图表优先 |
| `pie-chart` | 饼图/环图 | 原生图表优先 |
| `quote` | 引文/观点 | 原生文本+装饰 |
| `callout` | 强调信息 | 原生形状+文本 |
| `footer` | 页码/品牌/来源 | 原生文本+Logo |
| `background-art` | 背景视觉/插画 | SVG/图片回退 |

**每个组件必须同时提供 HTML Renderer 和 PPTX Renderer。**

---

## 可用模板（V1 内置）

| Template ID | 使用场景 |
|-------------|----------|
| `business-consulting` | 企业咨询/战略方案/诊断报告 |
| `product-proposal` | 产品方案/需求汇报/立项材料 |
| `sales-deck` | 客户提案/售前演示/商务方案 |
| `data-report` | 经营数据/运营复盘/业务分析 |
| `technical-architecture` | 技术架构/平台方案/系统能力 |
| `project-review` | 项目复盘/阶段总结/里程碑汇报 |

---

## 内容约束规则

### 标题规则

**必须使用结论式标题，禁止仅描述主题。**

❌ 错误示例：
- AI 项目现状
- 平台能力介绍
- 数据分析
- 产品优势

✅ 正确示例：
- 当前审核流程的主要瓶颈是人工判断无法规模化
- 系统已具备从素材解析到风险分级的自动化闭环
- 平台价值不在于替代人工，而在于沉淀可复用的风险判断能力
- 数据回流可持续提升高风险案例的识别准确率

### 单页内容密度限制

| 项目 | 默认规则 |
|------|----------|
| 单页核心结论 | 不超过 1 个 |
| 正文条目 | 建议 ≤ 5 条 |
| 单卡片条目 | 建议 ≤ 4 条 |
| 单页卡片数量 | 建议 ≤ 6 个 |
| 主要视觉区域 | 建议 ≤ 1 个 |
| 正文最小字号 | HTML 18px / PPT 13.5pt（不得低于） |
| 推荐正文字号 | HTML 22px / PPT 16.5pt |

**超出密度限制时，必须拆页、缩短文案或切换 Layout，禁止无限缩小字号。**

---

## HTML 渲染要求

- 每页使用固定 1920×1080 画布，不允许响应式重排导致不同设备显示不同
- 每页必须有唯一 `data-slide-id`
- 所有字体加载完成后才能截图/导出 PDF
- 所有图片加载完成后才能构建
- 图表必须生成静态 SVG 或稳定 DOM
- 关键内容不得依赖异步接口
- 禁止依赖公网 CSS、字体、脚本；所有资源必须本地化到 `.decksmith/assets/`
- 禁止将关键文本/数据放在 `::before`/`::after` 伪元素中

### HTML 页面结构示例

```html
<section class="slide slide--comparison" data-slide-id="slide-03">
  <header class="slide__header">
    <h1>传统流程与 AI 协同流程的差异</h1>
    <p>从人工经验驱动，转向结构化、可复用的业务能力</p>
  </header>
  <main class="slide__content">
    <!-- 由组件系统生成 -->
  </main>
  <footer class="slide__footer">
    <span>[Your Brand]</span>
    <span>03</span>
  </footer>
</section>
```

---

## PPTX 编译策略

PPTX 采用三级输出策略：

1. **Native Editable（原生可编辑）**：标题、正文、数字、表格、Logo、普通图片、流程节点、时间轴、箭头、矩形、圆角卡片、基础图表（柱状/折线/饼图）→ 优先使用 PowerPoint 原生对象
2. **Vector Fallback（SVG 回退）**：复杂图标、部分 SVG 图表、插画、装饰图形 → 保留为 SVG 维持清晰度
3. **Raster Fallback（图片回退）**：复杂渐变、玻璃拟态、模糊、复杂阴影、地图、复杂背景、Canvas 图表、无法稳定映射的区域 → 高分辨率 PNG

### PPTX 强制原则

- 标题、正文、核心指标**不得**整体截图
- 核心内容必须优先保留为独立对象
- Logo 必须作为独立图片对象
- 表格优先原生表格或形状组合
- 基础图表优先原生图表
- 复杂视觉区域图片化时，**必须保留关键标题和数据标签为文本对象**

---

## 不支持样式与降级优先级

以下效果**不得**作为关键内容表现形式（允许在 HTML 预览中存在，但 PPTX 必须有降级方案）：

- `filter: blur()`
- `backdrop-filter`
- `mix-blend-mode`
- `clip-path`
- `mask-image`
- CSS 3D Transform
- WebGL
- Canvas 承载核心正文
- 动态脚本生成关键文字/数据
- 伪元素承载核心内容
- 复杂浏览器私有 CSS

### 降级优先级

```text
原生 PowerPoint 对象
        ↓
SVG
        ↓
高清 PNG
        ↓
保留结构化内容并输出 QA 警告
        ↓
仅在关键内容无法呈现时标记页面失败
```

降级时必须给出明确提示，例如：
> Slide slide-07 中的 heatmap-chart 暂不支持原生 PPTX 输出，已自动降级为 SVG 图像。标题、图例与关键数值仍保留为可编辑文本。

---

## 图表要求

- 图表必须传达明确结论，不能只是视觉装饰
- 每张图表必须包含标题，必要时包含数据来源、时间范围、单位、关键结论
- V1 支持图表：柱状图、横向条形图、折线图、面积图、饼图、环图、漏斗图、堆叠柱状图、简单散点图、四象限矩阵、趋势指标卡
- 基础图表优先 PPTX 原生图表输出
- 复杂图表（热力图、桑基图、关系网络、复杂地图、自定义仪表盘）可用 SVG/PNG，但标题、图例、关键标签、关键数值尽量保留原生文本

---

## 资产处理

- 所有图片、图标、Logo、字体、SVG、图表、AI 生成素材必须统一管理
- 所有资源必须写入 `.decksmith/assets/`
- 资产清单记录在 `manifest.json`
- 默认禁止直接加载任意公网资源
- 在线资源必须经过：域名白名单校验 → 下载 → 本地缓存 → 格式转换 → 写入 `.decksmith/assets/`
- 图片裁切策略：`contain`（默认）、`cover`、`stretch`、`crop-focus-center/top/left/right`
- 默认不得拉伸变形

---

## 自动质量检测（QA）

### HTML 阶段检测项

- 文本溢出
- 元素重叠
- 页面越界
- 图片缺失
- 字体加载失败
- 图标缺失
- 内容密度过高
- 文字对比度不足
- 关键内容遮挡

### PPTX 阶段流程

```text
生成 PPTX → 回渲为 PDF/PNG → 与 HTML 截图比对 → 生成差异图 → 输出 QA 报告
```

### QA 报告示例

```json
{
  "presentationId": "enterprise-consulting-deck",
  "status": "warning",
  "slides": [
    {
      "slideId": "slide-03",
      "status": "passed",
      "issues": []
    },
    {
      "slideId": "slide-05",
      "status": "warning",
      "issues": [
        {
          "type": "text-overflow",
          "severity": "medium",
          "componentId": "metric-card-3",
          "message": "指标说明文本超过组件最大高度。"
        }
      ]
    }
  ]
}
```

### 自动修复顺序（必须严格按此顺序）

1. 压缩冗余文本
2. 调整组件布局
3. 切换更适合的 Layout
4. 拆分页面
5. 在不低于最小字号前提下微调字号
6. 对复杂区域启用 SVG 或图片回退

**禁止默认采用「缩小整页」或「将全页文字转图片」作为修复方式。**

---

## AI 生成行为规范

**AI 必须严格遵守以下规则：**

1. 必须先规划大纲，再生成页面
2. 必须为每页定义一个核心结论或表达目标
3. 必须根据内容目的选择 Layout，不得平均地将所有页面生成为卡片页
4. 避免重复使用渐变背景、三栏卡片、无意义图标、泛化插画、低信息密度文案
5. 不能为了填满页面而增加无价值内容
6. 必须优先使用结论式标题
7. 必须在图表页明确说明结论，不能只展示图表
8. 必须将复杂内容拆成多页，不能压缩到一页
9. 必须通过已注册的 Component 输出内容，禁止直接手写自由 HTML 或 CSS
10. 不得新增未经支持的 CSS 结构、JavaScript 动画或不受控组件
11. 示例内容中使用通用占位符（如 `[Your Brand]`、`[Company Name]`），不得硬编码特定品牌名称

---

## 错误处理

单个组件、图片、字体或复杂图表失败时，**不得**导致整份演示稿构建失败。

错误处理遵循降级优先级（见上文）。

- 字体缺失：使用主题定义的 fallback 字体，QA 报告记录字体替换
- 资源加载失败：HTML/PDF/PPTX 统一使用占位符或错误状态组件，不得出现空白区域且不记录问题

---

## 安全要求

- 不得直接访问任意 URL、内网地址、云元数据地址、用户未授权文件路径
- 外部资源必须经过：域名白名单、文件类型校验、大小限制、下载超时、格式转换、本地缓存
- 不允许 HTML 中执行用户提供的任意 JavaScript
- 不允许通过 HTML 渲染器访问本机敏感路径
- 不允许在 PPTX/PDF 中注入未经校验的外部链接、宏、脚本、可执行文件

---

## CLI 命令参考

```bash
# 创建演示稿
decksmith create \
  --input ./brief.md \
  --theme enterprise-light \
  --template business-consulting \
  --output ./.decksmith

# 基于 Slide IR 构建
decksmith build \
  --input .decksmith/presentation.json \
  --output ./.decksmith \
  --export html,pdf,pptx \
  --qa true

# 启动 HTML 预览
decksmith preview \
  --workspace ./.decksmith

# 单独导出指定格式
decksmith export \
  --workspace ./.decksmith \
  --format pdf,pptx

# 执行质量检测
decksmith qa \
  --workspace ./.decksmith

# 清理缓存
decksmith clean \
  --workspace ./.decksmith \
  --cache-only
```

---

## V1 最小可行范围

### 必须具备

- 支持 Markdown、JSON、自然语言需求作为输入
- 支持 Slide IR JSON 作为唯一结构化源
- 支持 16:9 演示稿
- 支持至少 5 套主题
- 支持至少 6 套模板
- 支持至少 18 个 Layout（见上文列表）
- 支持至少 18 个基础组件（见上文列表）
- 支持 HTML 预览
- 支持高保真 PDF 输出
- 支持混合可编辑 PPTX 输出
- 支持图片、图标、表格、流程图、时间轴、基础图表
- 支持本地资产管理
- 支持 HTML 与 PPTX 的视觉 QA
- 支持 CLI 和 Skill 调用
- 所有输出统一写入 `.decksmith/`

### V1 明确不做

- 自由拖拽编辑器
- 在线多人协作
- 完整 PowerPoint 母版编辑
- 复杂动画编辑
- 任意网页 URL 一键导入
- 任意 CSS 100% 可编辑映射
- 复杂 WebGL、Canvas、交互图表编辑

---

## 验收标准检查清单

| 验收项 | 标准 |
|--------|------|
| 工作目录 | 所有构建产物统一输出到 `.decksmith/` |
| 结构化源 | 每份演示稿必须存在 `.decksmith/presentation.json` |
| HTML 输出 | 可本地打开，页面无明显错位、溢出、图片缺失 |
| PDF 输出 | 与 HTML 基本一致，无默认浏览器页眉页脚 |
| PPTX 输出 | 可在 PowerPoint/Keynote/LibreOffice/Google Slides 中打开 |
| 可编辑性 | 标题、正文、核心数据、Logo、流程节点、基础表格保持独立对象 |
| 视觉一致性 | 基础组件在 HTML 与 PPTX 中保持较高一致性 |
| 降级能力 | 复杂背景和不支持组件可使用 SVG 或 PNG 回退 |
| 字体处理 | 字体缺失时有 fallback 与 QA 警告 |
| 内容密度 | 不允许依靠无限缩小字号塞入内容 |
| QA 报告 | 每次构建必须生成 `.decksmith/qa/qa-report.json` |
| 错误恢复 | 单个组件失败不得导致整份 PPT 构建失败 |
| 运行稳定性 | 20 页企业演示稿可稳定生成 HTML、PDF、PPTX 和 QA 报告 |
| 品牌中立 | 默认主题、模板、示例中不包含特定品牌信息，使用通用占位符 |
