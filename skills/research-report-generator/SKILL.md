---
name: research-report-generator
description: >-
  Generate structured research reports from raw research materials (screen-recording or
  follow-along videos, interview audio, transcripts, observation notes). Multimodal
  direct recognition first with script-based frame extraction as fallback. Ships four
  research method templates (shadowing observation, interview, survey, usability
  testing), extracts workflows, pain points and opportunities from materials, then
  delivers to local Markdown/Word, DingTalk Docs or Tencent Docs (local Markdown by
  default). Use when the user provides videos, audio, transcripts, or observation notes
  and asks to turn them into research reports, observation records, interview minutes,
  or to fill in a research form. 当用户需要基于调研素材（视频/音频/逐字稿/观察笔记）整理成
  调研报告、观察记录、访谈纪要或填写调研表时触发。
---

# 调研报告生成器（Research Report Generator）

## Overview

将调研素材（视频/音频/逐字稿）转化为结构化调研报告。流程：**多模态识别素材（直接识别优先，抽帧降级）→ 按调研方法选模板 → 组织报告内容 → 询问输出位置 → 写入并校验**。默认输出本地 Markdown。

## 触发场景

- 用户上传/引用**视频**（录屏、跟拍、演示）、**音频**（访谈录音）、**逐字稿**（txt/md/docx）、观察笔记，要求整理成调研报告、观察记录、访谈纪要
- 用户提到"调研""观察记录""访谈""逐字稿分析""跟班"等词并附素材文件
- 用户给出调研模板/在线文档（如钉钉「客服工作用户调研观察记录表」），要求按素材填充

## 工作流

### Step 1 — 素材预处理与多模态识别

**识别策略（优先级从高到低）**：

1. **多模态大模型直接识别原素材（首选，效果最好）**：若当前 AI 工具支持多模态（能直接看视频/听音频），**直接把原始视频/音频文件交给模型识别**，不要先抽帧——直接识别可保留连续动作、界面跳转、光标轨迹、声音语气、视频内字幕等抽帧会丢失的时序信息，工作流还原更准确
2. **降级——脚本抽帧/提音频**：仅当 AI 无法直接消费视频/音频（非多模态）、或文件过大超出上下文限制、或多模态识别结果不完整需逐帧核对时，才使用脚本：

```bash
python3 {SKILL_ROOT}/scripts/extract_media.py <input> <output_dir> [--interval 5] [--max-frames 240]
```

- **视频**：脚本会 ffprobe 输出元数据 + 每 5 秒抽一帧到 `frames/`。随后**用 Read 工具逐帧读取 JPG**（多模态识别界面/操作/系统），按时间轴重建工作流。优先复用当前 AI 的多模态读取能力，抽帧只是为多模态提供输入
- **音频**：脚本提取 16kHz 单声道 `audio.wav`。优先用 AI 的多模态/ASR 能力直接听辨或转写；若无转写工具，**向用户索取逐字稿**或说明仅能做音轨辅助分析
- **逐字稿/笔记**：直接读取文本即可，跳过脚本

分析时重点提取：操作步骤链、使用的系统/工具、各步骤耗时占比、异常与卡点、用户原话、业务术语（原样保留）。

> 经验：多模态直接识别原视频效果优于逐帧读图（后者有帧间隔盲区、看不清快速操作）；抽帧间隔默认 5 秒，画面密集/操作快的场景可调小（如 2 秒），长视频注意 `--max-frames` 上限。

### Step 2 — 选择调研方法模板

读取 `{SKILL_ROOT}/references/templates.md` 选择模板：

- 用户明确说了方法 → 用对应模板
- 未明确 → 按素材类型判断（见 templates.md 开头），并在报告中注明判断依据
- 跟拍/录屏类素材默认用**跟班观察法**模板（最常用，结构最完整）

### Step 3 — 生成报告内容

按模板章节组织内容，遵循 templates.md 的"通用写作规则"：保真优先、数据可溯、痛点=事实+影响、保留原术语、机会点分级、素材留痕。

若用户给了**在线文档链接**，先读取文档现状，与素材中提取的内容比对——**已有一致内容则跳过**（用户强调过"假如已经有所体现了，就忽略"），只补增量。

### Step 4 — 询问输出位置（关键决策点）

**生成报告前必须询问用户输出到哪里**，用 AskUserQuestion 提供选项：

1. 本地 Markdown 文档（默认）
2. 本地 Word (.docx) 文档
3. 钉钉文档（用户提供链接则直接填充，否则新建）
4. 腾讯文档（用户提供链接则直接填充，否则新建）

规则：
- 用户**已经给了在线文档链接**（钉钉/腾讯）→ 直接确认"是否填充到该文档？"，不必再问位置
- 用户回答**明确位置** → 照做
- 用户**未明确/跳过/超时** → **默认输出本地 Markdown**，保存到 `output/` 目录（工作区下），文件名 `YYYY-MM-DD_<主题>_调研报告.md`
- **素材留痕（强制，任何输出方式都执行）**：报告末尾附录必须有素材清单表（文件名/类型/时长/路径/内容说明）；本地输出时把源素材复制到报告同级 `output/素材/` 子目录并写相对路径（素材过大无法复制则写明原始绝对路径），保证报告与素材可相互追溯

### Step 5 — 写入与校验

#### 本地 Markdown
直接 Write 文件到 `output/` 目录，同时在 `output/素材/` 复制源素材（见 Step 4 留痕规则），完成后读取校验。

#### 本地 Word
使用 skill 自带脚本（**自包含，不依赖任何其他 skill**）：
```bash
pip install python-docx   # 首次使用需要
python {SKILL_ROOT}/scripts/md_to_docx.py <报告.md> <报告.docx>
```
脚本支持标题/表格/列表/粗体/链接与中文字体。若环境无法安装 python-docx，降级交付 Markdown（告知用户）。Word 输出同样遵循素材留痕规则（同目录 `素材/` 子目录 + 附录清单）。

#### 钉钉文档（dws CLI）
使用 `dws doc` 系列命令。**实战踩坑要点（必须遵守）**：

1. **先读现状**：`dws doc read --node <url>`，解析 `data.markdown`（顶层，不是 `data.data.markdown`）；返回空时等 10 秒重试（API 偶发抖动）
2. **表格替换用 insert+delete 模式**：`dws doc block insert`（before 旧表）插入新表 → `dws doc block delete --block-id <旧表id> --yes` 删除旧表。`block update` 不支持 table 类型，不能原地改
3. **插入前校验列数**：脚本化检查每张表所有行列数一致（曾有表头 2 列但数据行 3 列导致失败/错位的坑）；插入时每行列数必须与表头完全一致
4. **限流重试**：输出含 `rate_limit` 时指数退避（8s/16s）重试；每步操作之间 sleep 2~3 秒
5. **markdown 转义陷阱**：内容含 `+` 等字符会被转义为 `\+`，读回校验时注意；校验用关键词匹配而非精确相等
6. **块列表与读回不同步**：`block list` 与 `doc read` 两个 API 偶发视图不一致（分页/缓存），以多次读回交叉验证为准
7. **插入顺序坑**：`--index` 语义会把已有块往后推，链式插入时标题会错位；**改用 `--ref-block <锚点id> --where after` 锚定插入**，需要堆叠时按逆序插入（先插的内容会被后插的推到后面）
8. **附件（视频/音频）**：**必须走拆解流程**——(a) `dws doc media upload --node <URL> --file <path> --mime-type video/mp4 --name <名> --yes` 拿到稳定 `resourceId`；(b) `dws doc block insert --element '{"blockType":"attachment","attachment":{"resourceId":"...","name":"<显示名>","mimeType":"video/mp4"}}' --ref-block <锚块id> --where after` 插块。**不要用 `media insert` 一步式**：对 199MB+ 大视频会返回 partial success（OSS 已上传但 block 未插入正文），且 CLI 无"已知 resourceId 仅插 block"的补救接口；partial 后**切勿盲重试**（会重复上传且大概率仍失败）。attachment 块最小结构：`name` 必填（缺了报 `Argument name expected string`），`mimeType`/`viewType` 可缺省。附录章节插在文档末尾（先查最后一个块的 id 作锚点）

#### 腾讯文档
以本地 Markdown/DOCX 为最终交付物（方法见上两节）。若用户明确要求"在线腾讯文档"：优先使用**当前环境自带**的腾讯文档创建/上传能力（有就用其接口建文档并填入内容，无则降级）；若环境无此能力，交付本地文件并告知用户可自行导入腾讯文档。**不要依赖任何特定 skill 名称**——环境不同可用能力不同，一律按"先探测环境能力、无则降级本地交付"处理。

### Step 6 — 校验交付

- 本地：Read 回读报告，抽查关键内容
- 在线文档：读回全文，关键词校验（覆盖原预填信息 + 新增内容），确认原有数据未被破坏
- 用 present_files 展示报告文件（本地）或给出文档链接（在线）

## Resources

### scripts/extract_media.py
**降级方案**的媒体预处理脚本（多模态无法直接识别原素材时用）：ffprobe 元数据 + ffmpeg 抽帧/提音频。运行方式见 Step 1。

### scripts/md_to_docx.py
Markdown → Word 转换脚本（自包含，仅依赖 python-docx）。运行方式见 Step 5 本地 Word。

### references/templates.md
四种调研方法报告模板（跟班观察法/访谈法/问卷调查法/可用性测试法）+ 通用写作规则。每次生成报告前读取。

## 注意事项

- 不要臆造素材中没有的内容；素材不清晰时标注"无法确认"并向用户确认
- **识别优先级：多模态直接识别原素材优先，抽帧/提音频仅作降级或补充**（见 Step 1）；抽帧间隔默认 5 秒，画面密集/操作快的场景可调小（如 2 秒），长视频注意 `--max-frames` 上限
- 报告语言与用户交流语言一致（默认简体中文）；素材中的外文原样保留
