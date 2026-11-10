# 产出物、保存与续跑

初始化前确定场景和位置，交付前再读取本文件核对实际成果。辅助命令需要 Node.js 18+，无第三方依赖；它们管理文件，不会自动搜集证据或完成商业判断。

## 位置与命名

默认 `{RUN_DIR} = <调用时当前目录>/.bor/<研究主题>/`。固定调用时目录，临时切换目录不改变产出位置。主题可由一句话问题提炼，允许中文，移除分隔符、控制字符等无效字符；不写入 Skill 安装目录。

```bash
node "{SKILL_ROOT}/scripts/init_research.mjs" --topic "小型商家运营工具" --question "这个工具值得做吗？" --scenario idea
node "{SKILL_ROOT}/scripts/init_research.mjs" --topic "技术降本" --scenario technology,entry --max-rounds 4
node "{SKILL_ROOT}/scripts/init_research.mjs" --topic "主题" --output "/absolute/explicit-research-directory"
node "{SKILL_ROOT}/scripts/init_research.mjs" --resume "/absolute/existing-research-directory"
```

- `--output` 指本次研究目录本身，不再追加主题目录；尊重用户显式位置。已经存在则拒绝新建，续跑使用 `--resume`。
- 默认新建遇到重名时使用 `<主题>-2` 等序号；不覆盖既有文件。默认 `.bor` 为符号链接时拒绝写入，核实实际位置后可显式指定输出位置。
- `--resume` 只检查基础文件并返回位置，不改动文件。续跑先读原始问题、全部轮次、证据、约束和剩余额度；不能把中断当作新一轮预算。
- 不同研究不可仅凭“最新目录”自动合并；目标不能唯一确定时只问一个定位问题。
- 若默认位置不可写，交付到当前环境可写、可下载的任务目录，明确告知位置和原因，不声称仍保存于默认位置。

## 通用交付包

```text
.bor/<研究主题>/
├── README.md
├── report.md
├── action-plan.md
├── evidence.csv
├── research-log.md
├── artifacts/       # 按需创建
└── sources/         # 按需保存原始材料或计算输入
```

| 文件 | 交付要求 |
| --- | --- |
| `README.md` | 原始问题、实际场景、更新时间、证据阶段、决策状态、停止原因、所有实际产物相对链接及完成／部分完成／跳过状态；未生成项只列原因 |
| `report.md` | 必含决策摘要、研究范围与方法、证据与不确定性、行动建议；需求、市场、竞争、经济性、因果效果按场景裁剪；关键判断引用证据编号 |
| `action-plan.md` | 优先级、动作与目的、负责人角色、时间、资源／预算、前置证据、成功／停止阈值和下一决策点；未知项写待定，终止时说明重启条件 |
| `evidence.csv` | 可复核证据台账，字段见下文；无证据时允许仅有表头，但报告必须明确“待验证”及缺口 |
| `research-log.md` | 固定原始问题、场景、绝对目录和研究上限，逐轮追加方法与理由、证据、反证、结论、门禁、失效结论和额度；最后汇总当前状态 |

所有结束状态均交付通用包，包括反证否定、数据不可得、预算或轮数耗尽。草稿文件只表示初始化，不计为已完成研究；完成后移除 `BOR_DRAFT` 注释和占位说明，更新实际状态。

所有写入以初始化返回的绝对 `run_dir` 为基准。轮次只能追加到该主题内的 `research-log.md`。保留模板中的“固定任务信息／当前状态／轮次记录”结构和数值字段：最大轮次、连续无增量停止阈值、累计轮次、连续无增量轮次、剩余轮次。每轮使用 `### 第 N 轮` 标题，从 1 连续编号；当前计数须与记录数一致，剩余＝最大−累计。最终交付至少有一轮真实的取证或缺口检查记录，不能仅移除初始化标记就声称完成。若用户调整额度，先在固定信息与变更记录中写清新上限及依据。

## 场景专项映射

初始化可用 `--scenario <id>`，混合场景用逗号分隔。生成的专项文件仍为草稿；条件性文件不会由初始化器自动生成。场景变更在记录和索引同步体现，不删除历史证据。

| ID／场景 | 必须交付的专项文件 | 条件性文件／边界 |
| --- | --- | --- |
| `idea`／验证新想法 | `artifacts/idea-validation.md` | 人群、问题、替代、关键假设与试点条件 |
| `needs`／未满足需求 | `artifacts/needs-map.md` | 有适配真实调查数据才生成 `artifacts/odi-results.csv` |
| `trends`／趋势机会 | `artifacts/opportunity-map.md` | 区分信号、影响机制、候选机会和情景假设 |
| `technology`／技术降本 | `artifacts/value-chain.md` | 成本输入或可检验估算可得时增加 `artifacts/economics-model.csv`；标明实测与估算 |
| `entry`／地区或渠道进入 | `artifacts/entry-assessment.md` | 适用市场、准入、渠道、成本差异与本地验证 |
| `comparison`／方向比较 | `artifacts/opportunity-comparison.csv` | 可采用定性比较，未知值写待验证；主报告解释排序或暂不排序的原因 |
| `diagnosis`／业务诊断 | `artifacts/diagnosis.md` | 指标、竞争性原因假设与排查；无数据只交付检查计划，不写确定根因 |
| `pilot`／试点复盘 | `artifacts/pilot-review.md` | 原阈值、设计、实际结果、经济性、产能和下一决策；缺数据时为复盘与补证计划 |

映射的机器可读来源为 `{SKILL_ROOT}/templates/scenarios.json`。Markdown 模板在 `{SKILL_ROOT}/templates/`，按需读取对应文件。主报告解释决策，专项文件保存分析明细，避免全文重复。默认 Markdown、CSV；用户需要时再添加电子表格或图表。

## 证据台账与量化文件

### evidence.csv

表头必须保持：

```csv
evidence_id,source,source_date,collected_at,locator,excerpt_or_value,population_scope,claim_ids,limitations,conflicts
```

- `evidence_id`：唯一编号 `E001`、`E002` 等。报告、计划、记录和专项文件引用同一编号。
- `source`：公开原始链接或可读取文件位置；`source_date` 为发布日期，未知可空并说明；`collected_at` 为采集时间，注明时区。
- `locator`：页码、段落、数据表、行列或访问定位；`excerpt_or_value` 为短摘录或观测值，不能以模型观点冒充原始记录。
- `population_scope`：人群、地区、时间、样本或适用边界；`claim_ids` 记录支持或反对的结论编号，如 `C001`。
- `limitations`、`conflicts`：局限、同源转载、估算属性及冲突信息。引用不自动代表充分支持结论。
- 含逗号、换行或双引号的字段按 CSV 规则加双引号，内部双引号写两次。原始材料可保存于 `sources/`，也可引用已有位置，不强制复制大文件。

### odi-results.csv（条件满足才生成）

```csv
outcome_id,outcome,segment,sample_size,importance,satisfaction,opportunity_score,scale_max,evidence_ids
```

使用同一细分样本与一致口径的真实重要度、满意度数据；披露原调查量表、顶端两档定义、有效分母、缺失处理和权重。本文件按 Top-2-box 比例的 10 倍保存：`importance = 10 × 重要度顶两档占比`，`satisfaction = 10 × 满意度顶两档占比`，两者范围 0～10，`scale_max = 10`；`opportunity_score = importance + max(importance - satisfaction, 0)`，范围 0～20。这是比例版本的线性缩放，不是原始问卷评分均值，也不是成功概率。`sample_size` 为该结果有效回答数，`evidence_ids` 指向真实数据来源。计算前读取相关方法卡；无法取得适用题项和比例数据时不计算该分数。

检查脚本验证计算一致性，不设通用样本量或自动证明代表性。没有适配样本时不生成本文件，在需求地图与计划中保留调查设计。

### economics-model.csv（条件满足才生成）

推荐字段：`variable,value,unit,scenario,assumption_or_fact,evidence_ids,notes`。输入须可追溯；估计明确标记且可检验。公式、时间窗、货币、规模、遗漏成本及敏感性在报告或价值链说明中列明。不将估算利润写为实际业绩。

### opportunity-comparison.csv

默认字段：`direction,value_or_revenue,cost,resources,risks,evidence_strength,priority,evidence_ids,assumptions_and_gaps`。各方向使用相同口径；允许定性与“待验证”，不为得到排序而编造收入、权重或分数。数据不足时优先级可表达“先补证”，不能只有表头。

## 证据深度与最终检查

初筛用已有资料提出假设和验证计划；有适配调查、经营或公开数据再做范围内的定量评估；有真实行为、交易或实验数据再判断实际结果。商业机会状态（建议试点／调整方向／停止投入／待验证）与文件完成度分别记录。依赖缺失数据的量化文件跳过并说明，定性文件仍交付已有发现、局限与最小补证路径。

```bash
node "{SKILL_ROOT}/scripts/check_research.mjs" "/absolute/research-directory" --scenario needs
```

传入本次全部实际场景，检查通用及对应必需专项文件、草稿标记、轮次与额度一致性、本地链接、证据编号、CSV 和 ODI 计算。脚本不会联网，不检查 PDF、电子表格或原始材料正文，不证明样本真实、结论正确或已获外部行动授权。

最后回读实际成品，人工或由 agent 复核门禁与建议的一致性；交付入口、主报告、行动计划的真实绝对路径或下载链接。检查不通过则修复或明确交付受限，禁止仅把初始化骨架称为完成报告。
