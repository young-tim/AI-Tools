# PPTX-First Native Delivery with officecli

Use this reference only after the content plan is confirmed, unless the user
explicitly requested a no-confirmation PPTX-native build. The goal is a strong,
editable, visually reliable `.pptx` built entirely with officecli.

## Decision Rule

Use `pptx-native` for all builds: first confirm the content plan, then produce
the formal PPTX with native editable objects via officecli. `pptx-native` is required when any
of these are true:

- The user says the final goal is a beautiful or usable PPTX.
- The deck contains service loops, roadmaps, process flows, scenario matrices, value cards, or other visuals that need deliberate native PPTX composition.
- The deck should be client-facing, reusable, or suitable for repeated editing.

If the user explicitly requests no-confirmation generation or a quick structural
check, still generate PPTX-native output via officecli and document the assumptions.

## Visual Source Of Truth

Native PPTX is the visual source. PDF/PNG renders via officecli exist only for QA and review.

## Authoring Pattern

After confirmation and before drawing slides:

1. Keep a content source: Slide IR, outline JSON, or a concise source brief.
2. Rewrite visible slide copy for presentation use: shorter titles, fewer bullets, one message per slide.
3. Define a small design system: colors, typography, margins, card styles, footer, dividers, and number badges.
4. Choose 4-6 reusable native constructs such as card, metric card, process node, pill, connector, and footer.
5. Build the PPTX directly with officecli using native text, shapes, lines, tables, and simple charts. Do not make full-slide screenshots.

Use officecli for the full PPTX authoring chain with:

- Fixed 16:9 layout (13.333x7.5 in / 33.867x19.05 cm).
- A token object for colors and spacing.
- Shared helpers for title, footer, cards, chips, metric cards, process nodes, and connectors.
- Text boxes sized for expected Chinese/English wrapping.
- Use `officecli batch` for efficient multi-slide creation.

### Basic officecli PPTX Commands

```bash
# 创建新 PPTX
officecli create presentation.pptx

# 添加幻灯片
officecli add presentation.pptx / --type slide --prop title="Slide Title" --prop background=FFFFFF

# 添加文本形状
officecli add presentation.pptx '/slide[1]' --type shape \
  --prop text="Hello World" \
  --prop x=2cm --prop y=3cm \
  --prop w=20cm --prop h=2cm \
  --prop font=Arial --prop size=24pt \
  --prop color=333333

# 添加图片
officecli add presentation.pptx '/slide[1]' --type picture \
  --prop src=assets/images/example.png \
  --prop x=2cm --prop y=5cm --prop w=10cm --prop h=7cm

# 添加表格
officecli add presentation.pptx '/slide[1]' --type table \
  --prop rows=3 --prop cols=2 \
  --prop x=2cm --prop y=8cm --prop w=25cm --prop h=8cm

# 查看大纲
officecli view presentation.pptx outline

# 验证 PPTX
officecli validate presentation.pptx

# 检查问题
officecli view presentation.pptx issues

# 渲染 PDF
officecli view presentation.pptx pdf -o qa/rendered/presentation.pdf

# 渲染单页截图
officecli view presentation.pptx screenshot --page 1 -o qa/rendered/page-1.png
```

### Batch Operations

For building multiple slides efficiently, use officecli's batch mode:

```bash
# 创建 batch 命令文件
cat > build-commands.json << 'EOF'
[
  {"command":"add","path":"/","type":"slide","props":{"title":"Cover"}},
  {"command":"add","path":"/slide[1]","type":"shape","props":{"text":"Q4 Business Review","x":"3cm","y":"5cm","w":"28cm","h":"3cm","font":"Arial","size":"36pt","color":"1A1A2E","bold":"true"}},
  {"command":"add","path":"/","type":"slide","props":{"title":"Agenda"}},
  {"command":"add","path":"/slide[2]","type":"shape","props":{"text":"• Review\n• Plans\n• Q&A","x":"3cm","y":"4cm","w":"28cm","h":"10cm","font":"Arial","size":"20pt","color":"333333"}}
]
EOF

# 执行批量命令
officecli batch presentation.pptx --input build-commands.json
```

### SVG Assets

For SVG assets (like Lucide icons), use officecli `add --type picture` with the localized SVG file:

```bash
# 下载 Lucide 图标到工作空间
# 然后添加到幻灯片
officecli add presentation.pptx '/slide[1]' --type picture \
  --prop src=assets/icons/check.svg \
  --prop x=2cm --prop y=3cm --prop w=1cm --prop h=1cm
```

Keep the original SVG under the deck workspace `assets/` directory and record its source metadata in Slide IR and `assets/ATTRIBUTIONS.md`.

## Content And Design Rules

- Prefer direct claims over section labels.
- Shorten copy before lowering font size.
- Avoid repeated same-shape card grids across every slide; vary cover, matrix, loop, process, and summary structures.
- Use native connectors behind nodes in process and loop diagrams.
- Use decorative shapes only where they support hierarchy; they must not carry critical meaning.
- Keep core text and data editable wherever possible.
- If a complex visual area must be rasterized, keep key labels and numbers as native text and record the fallback.

## Property Reference

When unsure about property names, use officecli help:

```bash
officecli help pptx                    # 列出所有 PPT 元素
officecli help pptx shape              # 形状属性详情
officecli help pptx add                # add 命令用法
officecli help pptx set                # set 命令用法
```

Common shape properties:
- Position: `x`, `y` (in cm, in, pt, or px)
- Size: `w`, `h`
- Text: `text`, `font` (font.latin, font.ea for CJK), `size`, `color`, `bold`, `italic`
- Fill: `fill` (hex color)
- Line: `line.color`, `line.width`
- Alignment: `align` (left, center, right), `valign` (top, mid, bottom)

## QA Checklist

Run these checks before delivery:

1. Confirm the PPTX slide count matches the requested page limit:
   ```bash
   officecli view presentation.pptx outline
   ```

2. Run PptSmith helper QA:
   ```bash
   bash {SKILL_ROOT}/scripts/pptsmith.sh qa --workspace .pptsmith/decks/<deck-slug> --render required
   ```

   The helper writes `qa/qa-report.json` and `qa/pptx-qa-report.json`, runs officecli validate, checks stats/issues, and renders PDF/PNG screenshots via officecli. It produces evidence; it does not certify visual quality by itself.

3. officecli has built-in rendering capabilities. No external tools like LibreOffice, Poppler, or WPS Office are required.

4. Verify with `officecli validate` and `officecli view issues`.

5. Treat structural QA as a separate result, not as visual QA. A valid ZIP package, slide count, and text extraction prove the PPTX is structurally readable; they do not prove layout, clipping, overlap, or rendering quality.

6. If `qa/pptx-qa-report.json` has `visualQa.status` of `rendered` and the current model/session supports image understanding, inspect the rendered pages in `qa/rendered-pages/` at full size as the primary QA method. At minimum check cover, most text-dense slide, most visually dense slide, and closing slide; add process/architecture or scenario/value slides when those layouts exist.

7. Inspect fine-detail layout visually on rendered pages: text stays inside cards and callouts, cards align to a clear grid, buttons do not overlap footer/contact/page-number areas, icons and badges do not hide labels, charts/tables stay inside safe margins, connectors meet their nodes, and repeated elements have consistent spacing and alignment.

8. Use `officecli view issues` output as supporting evidence when visual inspection is available. If visual inspection is unavailable, explicitly downgrade to script detection, disclose that the result is heuristic. Resolve or explicitly justify warnings for out-of-bounds content, edge-clipping risk, text overflow, body text below the minimum size, and large overlaps between content elements.

9. If the report has `visualQa.status` of `pdf-rendered`, inspect the PDF directly and disclose that PNG page screenshots were not produced.

10. If the report has `visualQa.status` of `blocked`, stop and state the blocker. Offer the user a choice: provide screenshots, or accept structural-only QA with the explicit limitation.

11. Verify no obvious clipping, overlap, broken connectors, tiny body text, missing labels, position drift, formatting disorder, or container overflow.

12. Inspect the `.pptx` package when editability matters. A PPTX-first native build should not rely on full-slide images unless the fallback is intentional and documented.

13. Update `manifest.json` and `qa/qa-report.json` to reflect the actual delivery route, QA evidence, layout warnings, fixes, and any fallbacks.

## When To Fall Back

Use raster or image fallback only when:

- The visual cannot reasonably be represented with native PPTX objects via officecli.
- The user accepts lower editability.
- Key content remains available as native title, labels, or summary text.

## OfficeCLI Loaded Skills

For specialized PPTX tasks, you can load officecli's built-in skills:

```bash
officecli load_skill pptx          # 通用演示稿
officecli load_skill pitch-deck    # 融资演示稿
officecli load_skill morph-ppt     # Morph 动画演示稿
```

Follow the rules printed by the loaded skill for that specific deck type.
