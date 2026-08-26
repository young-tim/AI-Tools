#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_docx.py — 将 Markdown 调研报告转换为 Word (.docx)

用法:
  python md_to_docx.py <input.md> <output.docx>

依赖: pip install python-docx （本脚本自包含，不依赖任何 skill/CLI）
支持: 标题(#~######)、表格(| 语法)、无序/有序列表、粗体、行内代码、链接、段落。
中文字体默认"微软雅黑"，环境无该字体时 Word 会自动回退。
"""

import re
import sys

try:
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn
except ImportError:
    sys.exit("缺少 python-docx，请先安装: pip install python-docx")

CN_FONT = "微软雅黑"


def set_cn_font(run):
    run.font.name = CN_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)


def strip_md(txt):
    txt = re.sub(r"\*\*(.+?)\*\*", r"\1", txt)   # 粗体
    txt = re.sub(r"`(.+?)`", r"\1", txt)          # 行内代码
    txt = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", txt) # 链接保留文字
    return txt


def add_para(doc, text, style=None):
    p = doc.add_paragraph()
    if style:
        p.style = style
    parts = re.split(r"(\*\*.+?\*\*)", text)  # 仅识别粗体
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2])
            r.bold = True
            set_cn_font(r)
        else:
            r = p.add_run(strip_md(part))
            set_cn_font(r)
    return p


def add_table(doc, rows):
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        for j in range(ncols):
            cell = table.cell(i, j)
            txt = strip_md(row[j]) if j < len(row) else ""
            cell.text = ""
            p = cell.paragraphs[0]
            r = p.add_run(txt)
            set_cn_font(r)
            if i == 0:
                r.bold = True
    doc.add_paragraph()  # 表后空行


def main():
    if len(sys.argv) != 3:
        sys.exit("用法: python md_to_docx.py <input.md> <output.docx>")
    src, dst = sys.argv[1], sys.argv[2]

    with open(src, encoding="utf-8") as f:
        lines = f.read().splitlines()

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = CN_FONT
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    normal.font.size = Pt(10.5)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue

        # 表格：当前行是 | 开头，下一行是分隔行 |---|
        if (line.lstrip().startswith("|")
                and i + 1 < len(lines)
                and re.match(r"^\s*\|[\s:\-|]+\|?\s*$", lines[i + 1])):
            rows = [[c.strip() for c in line.strip().strip("|").split("|")]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            add_table(doc, rows)
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = min(len(m.group(1)), 6)
            p = doc.add_heading(level=level)
            r = p.add_run(m.group(2))
            set_cn_font(r)
            i += 1
            continue

        # 无序/有序列表
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            style = "List Bullet" if m.group(2) in ("-", "*") else "List Number"
            indent = len(m.group(1))
            if indent > 0:
                style = "List Bullet 2" if style == "List Bullet" else "List Number 2"
            add_para(doc, m.group(3), style=style)
            i += 1
            continue

        # 普通段落
        add_para(doc, line)
        i += 1

    doc.save(dst)
    print("[OK] 已生成: %s" % dst)


if __name__ == "__main__":
    main()
