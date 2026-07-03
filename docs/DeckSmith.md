# DeckSmith 技术需求文档

## AI Presentation Compiler Skill

## 1. 项目基本信息

项目名称：**DeckSmith**

项目定位：**AI Presentation Compiler，面向 AI 的演示稿编译与交付引擎。**

DeckSmith 的目标不是实现一个“任意网页转 PPT”的工具，而是让 AI 在受控、可复用、兼容 PPT 输出的演示稿设计系统中生成内容与视觉结构，再统一编译为 HTML、PDF 和混合可编辑 PPTX。

DeckSmith 应避免 AI 直接操作 PowerPoint 底层对象、坐标、XML、母版和复杂形状逻辑。AI 的工作重点应放在内容逻辑、叙事结构、页面版式选择和组件填充；系统负责将这些内容转换为稳定、可预览、可交付的演示稿文件。

DeckSmith 的核心输出目录固定为：

```text
.decksmith/
```

该目录是一次演示稿构建的工作空间，存放结构化源文件、HTML 预览、PDF、PPTX、素材、截图、缓存、日志和质量检测结果。

项目代码仓库建议命名为：

```text
decksmith
```

Skill 名称建议定义为：

```text
DeckSmith — AI Presentation Compiler
```

---

## 2. 问题背景

当前 AI 直接生成 PPTX 时，通常会遇到几个核心问题。

第一，PPTX 本身是偏底层的画布式文件格式。AI 需要处理文字框坐标、形状层级、图表对象、字体兼容、图片裁切、母版、单位换算、文本溢出和页面边界等大量实现细节。这些工作与内容表达无关，但会明显降低 AI 输出质量。

第二，PPT 的自由布局能力虽然很强，但其自动排版与视觉约束能力较弱。AI 一旦直接操作 PPTX，容易生成大量位置不对齐、字号不统一、内容拥挤、元素遮挡、风格不一致的页面。

第三，HTML/CSS 是 AI 更擅长生成的表达方式。AI 对 Flex、Grid、卡片布局、图文排版、渐变、圆角、阴影、SVG、组件化结构和响应式视觉语言更熟悉。基于 HTML 进行预览和迭代，通常更容易获得较好的视觉效果。

但自由 HTML 并不能直接稳定转换为可编辑 PPTX。复杂 CSS、动画、滤镜、Canvas、WebGL、混合模式、伪元素、动态脚本和嵌套布局都难以映射为 PowerPoint 原生对象。

因此，DeckSmith 的核心方法不是“HTML First”，而是：

> **Schema First，HTML Rendered，PPTX Compiled。**

即，Slide Schema / Slide IR 是唯一可信源；HTML 是高保真预览层；PDF 是稳定交付层；PPTX 是混合可编辑交付层。

---

## 3. 产品目标

DeckSmith 应支持 AI 根据自然语言需求、已有大纲、Markdown 文档、业务数据、JSON 数据或企业模板，自动生成完整演示稿。

生成结果应同时满足以下目标。

演示稿应具有清晰的内容逻辑。每页应有明确的表达目标，避免只有主题而没有结论。

演示稿应具备一致的视觉风格。字体、颜色、间距、圆角、图表、Logo、页脚和版式必须受主题系统控制。

演示稿应可在浏览器中预览，并稳定输出 PDF。

演示稿应能输出 PPTX。标题、正文、核心指标、表格、流程节点、Logo、普通图片和基础图表应尽量保留为 PowerPoint 原生对象，便于用户后续编辑。

对于复杂视觉内容，DeckSmith 可以采用 SVG 或局部图片降级，而不是强行将所有 CSS 效果映射为 PPT 原生对象。

DeckSmith 应具备自动质量检测能力，能够识别文本溢出、元素重叠、图片缺失、内容密度过高、字体替换、PPTX 与 HTML 的视觉差异等问题。

---

## 4. 非目标范围

DeckSmith V1 不应被定义为“任意网页 URL 转 PPT”的通用爬取工具。

以下能力不属于 V1 必须范围：

* 登录态网站、内部系统页面或任意在线网页直接导出 PPTX。
* Canvas、WebGL、Three.js、复杂地图和动态图表的原生 PPT 编辑。
* 网页动画、Hover 状态、滚动效果、视频播放、交互逻辑的完整复刻。
* 完整 PowerPoint 在线编辑器。
* 用户自由拖拽所有元素的设计工具。
* 所有 CSS 样式和复杂网页效果 100% 原生可编辑还原。
* `.ppt` 老格式输出。

对于不支持的复杂视觉效果，系统应采用局部 SVG 或图片回退，保证演示稿整体可以成功交付。

---

## 5. 核心设计原则

DeckSmith 的唯一可信内容源必须是 Slide IR，而不是 HTML，也不是 PPTX。

```text
用户需求 / 文档 / 数据
        ↓
AI 内容规划
        ↓
Slide IR
        ↓
组件与主题系统
        ↓
HTML / PDF / PPTX / PNG
```

AI 不能直接生成任意自由 HTML 作为最终源文件。AI 应生成受约束的 Slide Schema，使用预定义 Layout、Component、Theme 和 Asset。

DeckSmith 不追求“所有效果都完全可编辑”，而追求以下平衡：

> 核心内容可编辑，整体视觉高保真，复杂装饰允许图像化，输出稳定可交付。

页面内容应优先通过结构、层级、留白、字号和组件组织表达，而不是依赖过多无意义的装饰、渐变、图标或复杂背景。

每页应只表达一个核心结论。内容超出页面承载能力时，应拆页或切换 Layout，而不是无限缩小字体。

---

## 6. 核心工作流程

DeckSmith 的完整工作流如下：

```text
Step 1：读取用户需求、文档或数据
Step 2：识别演示目标、受众、场景和风格要求
Step 3：生成演示稿大纲
Step 4：定义每页的核心结论与表达目标
Step 5：为每页选择 Layout 与 Component
Step 6：生成 Slide IR
Step 7：校验 Schema、内容密度与组件兼容性
Step 8：渲染 HTML 演示稿
Step 9：执行 HTML 版式 QA
Step 10：输出 PDF
Step 11：编译 PPTX
Step 12：将 PPTX 回渲为图片
Step 13：执行 HTML 与 PPTX 的视觉 QA
Step 14：自动修复可处理的问题
Step 15：写入 .decksmith/ 并输出最终文件
```

AI 在生成页面之前，必须先确定内容逻辑。不得先随机选择视觉模板，再将内容强行填入。

---

## 7. 技术架构

DeckSmith 建议采用 TypeScript / Node.js 构建。

推荐的主要依赖如下：

| 能力        | 推荐技术                               |
| --------- | ---------------------------------- |
| 主语言       | TypeScript                         |
| 运行环境      | Node.js                            |
| Schema 校验 | Zod 或 JSON Schema                  |
| HTML 渲染   | React / TSX / 模板渲染器                |
| 浏览器渲染     | Playwright                         |
| PDF 导出    | Playwright Chromium PDF            |
| PPTX 生成   | PptxGenJS                          |
| 图片处理      | Sharp                              |
| 图表        | SVG 图表生成器、PptxGenJS 原生图表           |
| 视觉对比      | Pixelmatch、Resemble.js 或自定义像素比对    |
| PPTX 回渲   | LibreOffice Headless 或 Office 渲染服务 |
| CLI       | Commander、Yargs 或类似工具              |

推荐的代码目录结构如下：

```text
decksmith/
├── SKILL.md
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── cli/
│   │   ├── create.ts
│   │   ├── build.ts
│   │   ├── preview.ts
│   │   ├── export.ts
│   │   └── qa.ts
│   ├── compiler/
│   │   ├── compilePresentation.ts
│   │   ├── validatePresentation.ts
│   │   ├── buildManifest.ts
│   │   └── createWorkspace.ts
│   ├── schema/
│   │   ├── presentation.schema.ts
│   │   ├── slide.schema.ts
│   │   ├── component.schema.ts
│   │   ├── theme.schema.ts
│   │   └── asset.schema.ts
│   ├── planner/
│   │   ├── outlinePlanner.ts
│   │   ├── slidePlanner.ts
│   │   ├── layoutSelector.ts
│   │   └── contentDensityChecker.ts
│   ├── renderers/
│   │   ├── html/
│   │   │   ├── renderHtml.ts
│   │   │   ├── renderSlide.ts
│   │   │   ├── renderTheme.ts
│   │   │   └── styles/
│   │   ├── pdf/
│   │   │   └── exportPdf.ts
│   │   └── pptx/
│   │       ├── renderPptx.ts
│   │       ├── renderText.ts
│   │       ├── renderShape.ts
│   │       ├── renderImage.ts
│   │       ├── renderTable.ts
│   │       ├── renderChart.ts
│   │       └── fallbackRasterizer.ts
│   ├── components/
│   │   ├── cover/
│   │   ├── section/
│   │   ├── agenda/
│   │   ├── kpi/
│   │   ├── comparison/
│   │   ├── process/
│   │   ├── timeline/
│   │   ├── roadmap/
│   │   ├── architecture/
│   │   ├── chart/
│   │   ├── table/
│   │   └── summary/
│   ├── qa/
│   │   ├── detectOverflow.ts
│   │   ├── detectCollision.ts
│   │   ├── detectMissingAssets.ts
│   │   ├── visualDiff.ts
│   │   ├── renderPptxPreview.ts
│   │   └── buildQaReport.ts
│   └── utils/
│       ├── units.ts
│       ├── colors.ts
│       ├── fonts.ts
│       ├── assets.ts
│       ├── fileSystem.ts
│       └── logger.ts
├── themes/
│   ├── default-light.json
│   ├── default-dark.json
│   └── zhelu-ai.json
├── templates/
│   ├── business-consulting/
│   ├── product-proposal/
│   ├── sales-deck/
│   ├── data-report/
│   ├── technical-architecture/
│   └── project-review/
└── examples/
    ├── ai-consulting-deck.json
    ├── product-solution-deck.json
    └── technical-architecture-deck.json
```

---

## 8. `.decksmith/` 输出目录规范

DeckSmith 每次构建演示稿时，必须在项目根目录或用户指定目录下创建 `.decksmith/`。

该目录是单次演示稿构建的完整工作区。所有中间产物、最终文件、素材、缓存、日志和质量报告都应写入该目录，不应散落到项目根目录。

标准目录结构如下：

```text
.decksmith/
├── presentation.json          # Slide IR，演示稿唯一结构化源文件
├── presentation.html          # HTML 演示稿预览文件
├── presentation.pdf           # 高保真 PDF 文件
├── presentation.pptx          # 混合可编辑 PPTX 文件
├── manifest.json              # 构建清单、文件版本、素材引用、输出状态
│
├── source/
│   ├── brief.md               # 原始需求、输入文档或 Prompt 快照
│   ├── outline.json           # AI 生成的大纲
│   ├── theme.json             # 当前构建使用的主题快照
│   ├── template.json          # 当前构建使用的模板快照
│   └── data.json              # 原始数据、图表数据或业务输入数据
│
├── assets/
│   ├── images/                # 图片、产品图、背景图、示意图
│   ├── icons/                 # SVG / PNG 图标
│   ├── charts/                # 图表 SVG、图表配置、图表图片
│   ├── fonts/                 # 本地字体或字体映射信息
│   └── generated/             # AI 生成的插画、背景和视觉素材
│
├── previews/
│   ├── html/                  # HTML 页面截图
│   │   ├── slide-01.png
│   │   ├── slide-02.png
│   │   └── ...
│   ├── pptx/                  # PPTX 回渲截图
│   │   ├── slide-01.png
│   │   ├── slide-02.png
│   │   └── ...
│   └── diff/                  # HTML 与 PPTX 的视觉差异图
│       ├── slide-01-diff.png
│       ├── slide-02-diff.png
│       └── ...
│
├── qa/
│   ├── qa-report.json         # 总体 QA 报告
│   ├── html-layout-report.json
│   ├── pptx-visual-diff.json
│   ├── asset-report.json
│   └── issues/                # 有问题页面的截图、差异图与局部区域图
│
├── cache/
│   ├── browser/               # 浏览器渲染缓存
│   ├── rasterized/            # 复杂组件降级后的局部图片
│   ├── fonts/                 # 字体解析或转换缓存
│   └── temp/                  # 临时构建文件
│
└── logs/
    ├── build.log
    ├── render-html.log
    ├── export-pdf.log
    ├── export-pptx.log
    └── qa.log
```

`presentation.json` 是唯一结构化源文件。HTML、PDF、PPTX 和预览图都必须由该文件生成。

`manifest.json` 应记录本次构建版本、生成时间、主题、模板、输入文件、资产列表、输出状态和 QA 状态。

示例：

```json
{
  "name": "DeckSmith Presentation Manifest",
  "version": "1.0",
  "buildId": "20260703-231500",
  "status": "success",
  "theme": "zhelu-ai",
  "template": "business-consulting",
  "outputs": {
    "html": "presentation.html",
    "pdf": "presentation.pdf",
    "pptx": "presentation.pptx"
  },
  "qa": {
    "status": "warning",
    "report": "qa/qa-report.json"
  }
}
```

`.decksmith/cache/`、`.decksmith/logs/` 和 `.decksmith/previews/` 默认不建议提交到 Git；`presentation.json`、主题快照、模板快照、业务输入和最终 PPTX/PDF 是否提交，可由项目策略决定。

建议 `.gitignore` 默认包含：

```gitignore
.decksmith/cache/
.decksmith/logs/
.decksmith/previews/
.decksmith/qa/issues/
```

---

## 9. 页面尺寸与坐标体系

DeckSmith V1 默认使用 16:9 宽屏比例。

HTML 画布固定为：

```text
1920 × 1080 px
```

PPTX 页面使用宽屏布局：

```text
13.333 × 7.5 in
```

HTML 与 PPTX 坐标使用统一换算关系：

```text
1 inch = 144 px
pptx_x = html_x / 144
pptx_y = html_y / 144
pptx_width = html_width / 144
pptx_height = html_height / 144
```

字体大小使用以下换算关系：

```text
PPT Font Size(pt) = HTML Font Size(px) × 0.75
```

例如：

| HTML 字号 | PPT 字号 |
| ------: | -----: |
|    64px |   48pt |
|    56px |   42pt |
|    48px |   36pt |
|    40px |   30pt |
|    32px |   24pt |
|    24px |   18pt |
|    20px |   15pt |
|    18px | 13.5pt |

页面安全边距默认定义为：

```text
左侧：96px
右侧：96px
顶部：72px
底部：72px
```

任何核心内容不得超出安全边距。

---

## 10. Slide IR 数据模型

Slide IR 是 DeckSmith 的核心中间表示。

演示稿结构至少包含元信息、主题、设置、资产和页面列表。

```json
{
  "version": "1.0",
  "meta": {
    "title": "企业 AI 落地方案",
    "author": "哲路AI",
    "language": "zh-CN",
    "ratio": "16:9",
    "createdAt": "2026-07-03"
  },
  "theme": "zhelu-ai",
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

单页 Slide 至少包含以下字段：

```json
{
  "id": "slide-03",
  "type": "comparison",
  "layout": "two-column-comparison",
  "title": "传统流程与 AI 协同流程的差异",
  "subtitle": "从人工经验驱动，转向结构化、可复用的业务能力",
  "themeVariant": "light",
  "components": [],
  "notes": "用于强调业务效率、标准化和可复用性的差异。",
  "qa": {
    "maxTextDensity": "medium",
    "allowRasterFallback": true
  }
}
```

Slide IR 不应保存大段任意 CSS。所有视觉表现应由 Theme、Layout、Component 和 Variant 控制。

---

## 11. 组件与布局体系

DeckSmith 的组件体系分为四层。

Layout 负责页面整体结构，例如封面、双栏、三栏、时间轴、流程图、架构图、表格页和总结页。

Content Component 负责内容表达，例如标题、正文、指标、对比项、流程节点、图表、表格和行动建议。

Visual Component 负责统一装饰，例如背景、Logo、页码、分割线、标签、图标和纹理。

Fallback Component 负责复杂视觉区域的降级，例如复杂渐变背景、插画、地图、复杂 SVG、Canvas 图表和特殊装饰。

V1 至少应支持以下 Layout：

| Layout ID        | 使用场景       |
| ---------------- | ---------- |
| `cover`          | 项目封面、品牌封面  |
| `section`        | 章节过渡页      |
| `agenda`         | 目录页        |
| `single-message` | 单一结论页      |
| `two-column`     | 双栏内容页      |
| `three-card`     | 三卡片信息页     |
| `image-text`     | 图文组合页      |
| `comparison`     | 对比分析页      |
| `kpi-dashboard`  | 指标数据页      |
| `process-flow`   | 流程图页       |
| `timeline`       | 时间轴页       |
| `roadmap`        | 实施路线图页     |
| `architecture`   | 技术架构或业务架构页 |
| `matrix`         | 四象限矩阵页     |
| `funnel`         | 漏斗模型页      |
| `table-report`   | 表格报告页      |
| `summary`        | 总结与行动项页    |
| `qa`             | 问答或结束页     |

V1 至少应支持以下组件：

| Component ID       | 说明        | PPTX 输出策略      |
| ------------------ | --------- | -------------- |
| `title`            | 页面标题      | 原生文本框          |
| `subtitle`         | 页面副标题     | 原生文本框          |
| `body-text`        | 正文段落      | 原生文本框          |
| `bullet-list`      | 要点列表      | 原生文本框          |
| `metric-card`      | 指标卡片      | 原生形状 + 文本      |
| `image`            | 图片、产品图、截图 | 原生图片           |
| `icon`             | 图标        | SVG 或 PNG      |
| `comparison-panel` | 对比卡片      | 原生形状 + 文本      |
| `process-node`     | 流程节点      | 原生形状 + 文本 + 连线 |
| `timeline-node`    | 时间轴节点     | 原生形状 + 文本      |
| `table`            | 数据表格      | 原生表格或形状组合      |
| `bar-chart`        | 柱状图       | 原生图表优先         |
| `line-chart`       | 折线图       | 原生图表优先         |
| `pie-chart`        | 饼图、环图     | 原生图表优先         |
| `quote`            | 引文、观点     | 原生文本 + 装饰形状    |
| `callout`          | 强调信息      | 原生形状 + 文本      |
| `footer`           | 页码、品牌、来源  | 原生文本 + Logo    |
| `background-art`   | 背景视觉或插画   | SVG 或图片回退      |

每个组件必须同时具备 HTML Renderer 和 PPTX Renderer。

接口建议如下：

```ts
interface PresentationComponentRenderer {
  renderHtml(
    props: ComponentProps,
    context: HtmlRenderContext
  ): string;

  renderPptx(
    props: ComponentProps,
    context: PptxRenderContext
  ): Promise<void>;

  getBoundingBox(
    props: ComponentProps,
    context: LayoutContext
  ): BoundingBox;

  validate(
    props: ComponentProps,
    context: ValidationContext
  ): ValidationResult;
}
```

---

## 12. Theme 与 Template 机制

Theme 与 Template 必须分离。

Theme 负责视觉规范，包括颜色、字体、字号、间距、圆角、边框、阴影、Logo、页脚和图表颜色。

Template 负责内容结构，包括适用场景、默认大纲、推荐页面顺序、优先 Layout、组件组合逻辑和内容密度限制。

主题示例：

```json
{
  "id": "zhelu-ai",
  "name": "哲路AI企业咨询主题",
  "colors": {
    "background": "#F7F8FA",
    "surface": "#FFFFFF",
    "primary": "#111827",
    "secondary": "#4B5563",
    "accent": "#2563EB",
    "accentSoft": "#DBEAFE",
    "positive": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "line": "#E5E7EB"
  },
  "fonts": {
    "heading": "Noto Sans SC",
    "body": "Noto Sans SC",
    "number": "Inter"
  },
  "typography": {
    "coverTitle": 56,
    "sectionTitle": 48,
    "slideTitle": 40,
    "slideSubtitle": 24,
    "bodyLarge": 28,
    "body": 22,
    "bodySmall": 18,
    "caption": 16
  },
  "spacing": {
    "pageX": 96,
    "pageY": 72,
    "grid": 24,
    "cardGap": 32,
    "sectionGap": 48
  },
  "shape": {
    "radiusSmall": 16,
    "radiusMedium": 24,
    "radiusLarge": 36
  }
}
```

V1 建议至少提供以下模板：

| Template                 | 使用场景             |
| ------------------------ | ---------------- |
| `business-consulting`    | 企业咨询、战略方案、诊断报告   |
| `product-proposal`       | 产品方案、需求汇报、立项材料   |
| `sales-deck`             | 客户提案、售前演示、商务方案   |
| `data-report`            | 经营数据、运营复盘、业务分析   |
| `technical-architecture` | 技术架构、平台方案、系统能力介绍 |
| `project-review`         | 项目复盘、阶段总结、里程碑汇报  |

企业咨询模板可采用以下默认结构：

```text
封面
项目背景与关键问题
核心结论
现状诊断
关键差距
解决方案框架
能力模块
实施路径
预期收益
下一步行动
```

---

## 13. 设计与内容约束

AI 必须使用 DeckSmith 已注册的主题、Layout 和 Component。

AI 不得在最终输出中任意新增未经支持的 CSS 结构、JavaScript 动画或不受控组件。

AI 不应让页面每次都采用三栏卡片、圆角矩形和渐变背景。布局应根据内容目的选择。

标题必须优先采用结论型表达，而不是仅描述主题。

错误示例：

```text
AI 项目现状
平台能力介绍
数据分析
产品优势
```

正确示例：

```text
当前审核流程的主要瓶颈是人工判断无法规模化
系统已具备从素材解析到风险分级的自动化闭环
平台价值不在于替代人工，而在于沉淀可复用的风险判断能力
数据回流可持续提升高风险案例的识别准确率
```

单页内容建议遵循以下约束：

| 项目     | 默认规则                       |
| ------ | -------------------------- |
| 单页核心结论 | 不超过 1 个                    |
| 正文条目   | 建议不超过 5 条                  |
| 单卡片条目  | 建议不超过 4 条                  |
| 单页卡片数量 | 建议不超过 6 个                  |
| 主要视觉区域 | 建议不超过 1 个                  |
| 正文最小字号 | HTML 18px / PPT 13.5pt     |
| 推荐正文字号 | HTML 22px / PPT 16.5pt     |
| 标题字号   | HTML 36–48px / PPT 27–36pt |
| 封面标题字号 | HTML 52–64px / PPT 39–48pt |

内容密度超出限制时，DeckSmith 应优先拆页、缩短文案或切换 Layout，不得通过无限缩小字号解决问题。

---

## 14. HTML 渲染要求

HTML 是 DeckSmith 的高保真预览层，也是 PDF 输出和视觉 QA 的基础。

HTML 必须是可独立访问、可本地打开、可稳定截图的演示稿页面。

每页必须使用固定画布，不允许依赖响应式重排导致不同设备显示不同。

每页 HTML 必须有唯一 `slide id`。

示例：

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
    <span>哲路AI</span>
    <span>03</span>
  </footer>
</section>
```

HTML 渲染阶段必须满足以下要求：

```text
所有字体加载完成后才能截图或导出 PDF。
所有图片加载完成后才能构建。
图表必须生成静态 SVG 或稳定 DOM。
关键内容不得依赖异步接口返回。
不允许最终演示稿依赖公网 CSS、字体或脚本。
所有资源必须放入 .decksmith/assets/。
```

禁止将关键文本、关键数据或核心逻辑放在 `::before`、`::after` 等伪元素中。

---

## 15. PDF 输出要求

PDF 应以 HTML 浏览器渲染结果为基础输出。

PDF 的目标是高保真、稳定、适合客户交付、打印、预览和归档。

PDF 输出必须保持与 HTML 预览基本一致，包括字体、颜色、图片、背景、SVG、图表和页面比例。

默认 PDF 输出应采用无边距、固定 16:9 页面比例，不得出现浏览器默认页眉、页脚、边距或分页异常。

PDF 输出路径固定为：

```text
.decksmith/presentation.pdf
```

---

## 16. PPTX 编译要求

PPTX 是 DeckSmith 的混合可编辑输出。

PPTX 页面必须由 Slide IR 编译，不得通过整页截图作为默认策略。

PPTX 输出策略分为三级。

第一层为 Native Editable。标题、正文、数字、表格、Logo、普通图片、流程节点、时间轴、箭头、矩形、圆角卡片和基础图表应优先使用 PowerPoint 原生对象。

第二层为 Vector Fallback。复杂图标、部分 SVG 图表、插画和装饰图形可保留为 SVG，以维持清晰度。

第三层为 Raster Fallback。复杂渐变、玻璃拟态、模糊、复杂阴影、地图、复杂背景、Canvas 图表和无法稳定映射的区域可降级为高分辨率 PNG。

PPTX 输出必须遵循以下原则：

```text
标题、正文和核心指标不得整体截图。
核心内容必须优先保留为独立对象。
Logo 必须作为独立图片对象。
表格必须优先原生表格或形状组合。
基础柱状图、折线图和饼图优先原生图表。
背景和复杂装饰允许图片化。
复杂视觉区域图片化时，必须保留关键标题和数据标签为文本对象。
```

PPTX 输出路径固定为：

```text
.decksmith/presentation.pptx
```

---

## 17. 不支持样式与降级策略

以下能力不得作为关键内容表现形式：

```text
filter: blur()
backdrop-filter
mix-blend-mode
clip-path
mask-image
CSS 3D Transform
WebGL
Canvas 承载核心正文
动态脚本生成关键文字或数据
伪元素承载核心内容
复杂浏览器私有 CSS
```

这些效果允许存在于 HTML 预览中，但在 PPTX 编译时必须具备降级方案。

降级优先级如下：

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

示例错误提示：

```text
Slide slide-07 中的 heatmap-chart 暂不支持原生 PPTX 输出，
已自动降级为 SVG 图像。标题、图例与关键数值仍保留为可编辑文本。
```

---

## 18. 图表与数据组件要求

图表不应只是视觉装饰，必须传达明确结论。

每张图表必须包含标题，必要时包含数据来源、时间范围、单位和关键结论。

DeckSmith V1 应支持以下图表：

```text
柱状图
横向条形图
折线图
面积图
饼图
环图
漏斗图
堆叠柱状图
简单散点图
四象限矩阵
趋势指标卡
```

基础图表应优先使用 PPTX 原生图表输出。

复杂图表，如热力图、桑基图、关系网络、复杂地图和自定义仪表盘，可使用 SVG 或 PNG 输出，但其标题、图例、关键标签和关键数值应尽量保留为原生文本。

---

## 19. 资产处理要求

所有图片、图标、Logo、字体、SVG、图表和 AI 生成素材必须纳入统一资产管理流程。

所有资源必须写入：

```text
.decksmith/assets/
```

资产清单应记录在 `manifest.json` 中。

示例：

```json
{
  "assets": [
    {
      "id": "logo-zhelu-ai",
      "type": "image",
      "path": "assets/images/zhelu-ai-logo.png",
      "usage": ["cover", "footer"]
    },
    {
      "id": "hero-visual",
      "type": "image",
      "path": "assets/generated/hero-visual.png",
      "usage": ["slide-01"]
    }
  ]
}
```

默认禁止在最终演示稿中直接加载任意公网资源。

如需使用在线图片或在线图标，必须经过允许域名校验、下载、本地缓存和格式转换，再写入 `.decksmith/assets/`。

图片组件必须支持以下裁切策略：

```text
contain
cover
stretch
crop-focus-center
crop-focus-top
crop-focus-left
crop-focus-right
```

默认不得拉伸变形。

---

## 20. 自动质量检测

DeckSmith 必须包含自动 QA 流程。

HTML 阶段应检查：

```text
文本溢出
元素重叠
页面越界
图片缺失
字体加载失败
图标缺失
内容密度过高
文字对比度不足
关键内容遮挡
```

PPTX 阶段应执行以下流程：

```text
生成 PPTX
        ↓
将 PPTX 回渲为 PDF 或 PNG
        ↓
与 HTML 页面截图比对
        ↓
生成视觉差异图
        ↓
输出 QA 报告
```

QA 报告示例：

```json
{
  "presentationId": "ai-consulting-deck",
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
        },
        {
          "type": "pptx-visual-difference",
          "severity": "low",
          "componentId": "background-art",
          "message": "复杂渐变已降级为图片背景。"
        }
      ]
    }
  ]
}
```

QA 文件统一写入：

```text
.decksmith/qa/
```

视觉差异图统一写入：

```text
.decksmith/previews/diff/
```

自动修复顺序如下：

```text
压缩冗余文本
        ↓
调整组件布局
        ↓
切换更适合的 Layout
        ↓
拆分页面
        ↓
在不低于最小字号的前提下微调字号
        ↓
对复杂区域启用 SVG 或图片回退
```

禁止默认采用“缩小整页”或“将全页文字转图片”作为修复方式。

---

## 21. AI 生成行为规范

DeckSmith Skill 中的 AI 必须遵循以下原则。

AI 必须先规划大纲，再生成页面。

AI 必须为每页定义一个核心结论或表达目标。

AI 必须根据内容选择 Layout，不得平均地将所有页面生成为卡片页。

AI 应避免重复使用渐变背景、三栏卡片、无意义图标、泛化插画和低信息密度文案。

AI 不能为了填满页面而增加无价值内容。

AI 必须优先使用结论式标题。

AI 必须在图表页明确说明结论，而不是只展示图表。

AI 必须将复杂内容拆成多页，而不是压缩到一页。

AI 必须通过已注册的 Component 输出内容，而不是直接手写自由 HTML 或 CSS。

---

## 22. Skill 指令文件要求

项目根目录必须包含 `SKILL.md`。

`SKILL.md` 用于指导执行 AI 如何使用 DeckSmith，并应包含以下内容：

```md
# DeckSmith — AI Presentation Compiler

## Purpose

Create enterprise-grade presentations using Slide IR, controlled layouts,
components, themes, and assets. Export HTML, PDF, and hybrid-editable PPTX.

## Mandatory Workflow

1. Read the user request and identify the presentation objective.
2. Define audience, scenario, tone, and desired output type.
3. Build a slide outline before designing slides.
4. Define one key message for every slide.
5. Choose approved layouts and components only.
6. Generate Slide IR as the canonical source.
7. Validate schema, density, asset references, and component compatibility.
8. Render HTML preview into .decksmith/presentation.html.
9. Run HTML layout QA.
10. Export PDF into .decksmith/presentation.pdf.
11. Export PPTX into .decksmith/presentation.pptx.
12. Render PPTX preview images.
13. Run visual QA and write reports into .decksmith/qa/.
14. Fix blocking issues before final delivery.

## Design Rules

- Do not use arbitrary HTML as the source of truth.
- Use Slide IR as the canonical source.
- Use registered layouts and components only.
- Keep key text, metrics, tables, and process nodes editable in PPTX.
- Use SVG or image fallback only for complex decorative regions.
- Do not reduce font size below the theme minimum.
- Split slides when content density is too high.
- Use conclusion-driven slide titles.
- Keep one key message per slide.
- Do not add decoration without semantic value.

## Output Workspace

All outputs must be written to:

.decksmith/

Required output files:

- .decksmith/presentation.json
- .decksmith/presentation.html
- .decksmith/presentation.pdf
- .decksmith/presentation.pptx
- .decksmith/manifest.json
- .decksmith/qa/qa-report.json
```

---

## 23. CLI 设计

DeckSmith 应提供 CLI，供 Skill、Agent、脚本和人工调用。

创建演示稿：

```bash
decksmith create \
  --input ./brief.md \
  --theme zhelu-ai \
  --template business-consulting \
  --output ./.decksmith
```

基于 Slide IR 构建：

```bash
decksmith build \
  --input .decksmith/presentation.json \
  --output ./.decksmith \
  --export html,pdf,pptx \
  --qa true
```

启动 HTML 预览：

```bash
decksmith preview \
  --workspace ./.decksmith
```

单独导出指定格式：

```bash
decksmith export \
  --workspace ./.decksmith \
  --format pdf,pptx
```

执行质量检测：

```bash
decksmith qa \
  --workspace ./.decksmith
```

清理缓存：

```bash
decksmith clean \
  --workspace ./.decksmith \
  --cache-only
```

---

## 24. 核心程序接口

核心编译函数建议如下：

```ts
async function compilePresentation(
  input: CompilePresentationInput
): Promise<CompilePresentationResult> {
  const workspace = await createWorkspace(input.outputDir);

  const presentation = await buildPresentationSchema(input);

  const schemaValidation = validatePresentation(presentation);
  if (!schemaValidation.valid) {
    throw new Error(schemaValidation.message);
  }

  await writePresentationSource(workspace, presentation);

  const htmlResult = await renderHtml(presentation, workspace);
  const htmlQaResult = await runHtmlQa(htmlResult, workspace);

  const pdfResult = await exportPdf(htmlResult, workspace);

  const pptxResult = await renderPptx(presentation, workspace);
  const pptxPreviewResult = await renderPptxPreview(pptxResult, workspace);

  const visualQaResult = await runVisualQa(
    htmlResult.previewImages,
    pptxPreviewResult.images,
    workspace
  );

  const qaReport = mergeQaResults(
    schemaValidation,
    htmlQaResult,
    visualQaResult
  );

  await writeQaReport(workspace, qaReport);
  await writeManifest(workspace, presentation, qaReport);

  return {
    workspace,
    presentation,
    htmlResult,
    pdfResult,
    pptxResult,
    qaReport
  };
}
```

---

## 25. 错误处理要求

单个组件、图片、字体或复杂图表失败时，不得导致整份演示稿构建失败。

错误处理应遵循以下规则：

```text
优先尝试原生对象输出
        ↓
尝试 SVG 输出
        ↓
尝试 PNG 输出
        ↓
保留页面结构并写入 QA 警告
        ↓
仅在关键内容无法呈现时标记该页面失败
```

示例错误信息：

```text
slide-08 的 custom-map 组件无法生成原生 PPTX 图形，
已自动使用 SVG 回退。标题、图例和关键数据仍保留为可编辑对象。
```

字体缺失时，应采用主题中定义的 fallback 字体，并在 QA 报告中记录字体替换。

资源加载失败时，应在 HTML、PDF、PPTX 三个输出中统一使用占位符或错误状态组件，不得出现空白区域且不记录问题。

---

## 26. 安全要求

DeckSmith 不应直接访问任意 URL、内网地址、云元数据地址或用户未授权文件路径。

外部资源必须经过明确的资源加载策略，包括域名白名单、文件类型校验、文件大小限制、下载超时、格式转换和本地缓存。

不允许 HTML 中执行用户提供的任意 JavaScript。

不允许通过 HTML 渲染器访问本机敏感路径。

不允许在 PPTX 或 PDF 中注入未经校验的外部链接、宏、脚本或可执行文件。

---

## 27. V1 最小可行范围

DeckSmith V1 应优先服务于企业咨询、产品方案、售前提案、项目汇报、技术架构说明和数据复盘等场景。

V1 至少应具备以下能力：

```text
支持 Markdown、JSON 和自然语言需求作为输入。
支持 Slide IR JSON 作为唯一结构化源。
支持 16:9 演示稿。
支持至少 5 套主题。
支持至少 6 套模板。
支持至少 18 个 Layout。
支持至少 20 个基础组件。
支持 HTML 预览。
支持高保真 PDF 输出。
支持混合可编辑 PPTX 输出。
支持图片、图标、表格、流程图、时间轴和基础图表。
支持本地资产管理。
支持 HTML 与 PPTX 的视觉 QA。
支持 CLI 和 Skill 调用。
所有输出统一写入 .decksmith/。
```

V1 明确不做以下能力：

```text
自由拖拽编辑器
在线多人协作
完整 PowerPoint 母版编辑
复杂动画编辑
任意网页 URL 一键导入
任意 CSS 100% 可编辑映射
复杂 WebGL、Canvas 和交互图表编辑
```

---

## 28. 验收标准

DeckSmith V1 完成后，应满足以下验收标准。

| 验收项     | 标准                                                    |
| ------- | ----------------------------------------------------- |
| 工作目录    | 所有构建产物统一输出到 `.decksmith/`                             |
| 结构化源    | 每份演示稿必须存在 `.decksmith/presentation.json`              |
| HTML 输出 | 可本地打开，页面无明显错位、溢出、图片缺失                                 |
| PDF 输出  | 与 HTML 基本一致，无默认浏览器页眉页脚                                |
| PPTX 输出 | 可在 PowerPoint、Keynote、LibreOffice 或 Google Slides 中打开 |
| 可编辑性    | 标题、正文、核心数据、Logo、流程节点和基础表格保持独立对象                       |
| 视觉一致性   | 基础组件在 HTML 与 PPTX 中保持较高一致性                            |
| 降级能力    | 复杂背景和不支持组件可使用 SVG 或 PNG 回退                            |
| 字体处理    | 字体缺失时应有 fallback 与 QA 警告                              |
| 内容密度    | 不允许依靠无限缩小字号塞入内容                                       |
| QA 报告   | 每次构建必须生成 `.decksmith/qa/qa-report.json`               |
| 错误恢复    | 单个组件失败不得导致整份 PPT 构建失败                                 |
| 运行稳定性   | 20 页企业演示稿可稳定生成 HTML、PDF、PPTX 和 QA 报告                  |

---

## 29. 最终定位

DeckSmith 不是单纯的“HTML 转 PPT 工具”，也不是一个只会将网页截图塞进 PPT 的导出器。

DeckSmith 的定位应定义为：

> **AI Presentation Compiler：将 AI 生成的结构化演示内容，编译为高质量 HTML、PDF 和混合可编辑 PPTX 的演示稿交付引擎。**

DeckSmith 的核心价值在于建立一套 AI 可理解、企业可复用、视觉可控、格式可交付的演示稿设计语言。

最终形成以下闭环：

```text
AI 内容理解
        ↓
演示逻辑规划
        ↓
Slide IR 结构化表达
        ↓
受控组件化设计
        ↓
HTML 高保真预览
        ↓
PDF 稳定交付
        ↓
PPTX 混合可编辑输出
        ↓
自动视觉 QA
        ↓
企业主题与模板持续沉淀
```
