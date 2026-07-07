#!/usr/bin/env python3
"""PPTX QA helper for DeckSmith.

This script provides deterministic structural checks and, when LibreOffice is
already available, PPTX-to-PDF/PNG render checks. It intentionally does not
install software and does not use WPS Office, whose macOS binary opens a GUI and
is not reliable for headless conversion.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import unescape


EMU_PER_INCH = 914400
SLIDE_WIDE = (13.333, 7.5)
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
MIN_BODY_FONT_PT = 13.5
SAFE_MARGIN_IN = 0.05
OVERLAP_WARN_AREA_RATIO = 0.08
MIN_BODY_TEXT_LENGTH = 18
FOOTER_BAND_IN = 0.55


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run structural and optional render QA for a PPTX file.")
    parser.add_argument("pptx", help="Path to the PPTX file to inspect.")
    parser.add_argument("--workspace", help="Deck workspace, e.g. .decksmith/decks/<slug>.")
    parser.add_argument("--report", help="Report path. Defaults to <workspace>/qa/pptx-qa-report.json.")
    parser.add_argument(
        "--render",
        choices=["auto", "off", "required"],
        default="auto",
        help="auto renders when tools exist; required exits non-zero if visual render is blocked.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="LibreOffice conversion timeout in seconds.")
    return parser.parse_args()


def natural_slide_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def default_workspace(pptx: Path) -> Path:
    parts = pptx.resolve().parts
    if ".decksmith" in parts and "decks" in parts:
        decks_idx = parts.index("decks")
        if decks_idx + 1 < len(parts):
            return Path(*parts[: decks_idx + 2])
    return pptx.resolve().parent.parent if pptx.parent.name == "output" else pptx.resolve().parent


def decode_text(xml: str) -> list[str]:
    values = re.findall(r"<a:t>(.*?)</a:t>", xml, flags=re.S)
    return [unescape(re.sub(r"\s+", " ", value)).strip() for value in values if value.strip()]


def emu_to_in(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return int(value) / EMU_PER_INCH
    except ValueError:
        return 0.0


def slide_size(archive: zipfile.ZipFile) -> tuple[float, float]:
    try:
        xml = archive.read("ppt/presentation.xml")
        root = ET.fromstring(xml)
        size = root.find("p:sldSz", NS)
        if size is not None:
            width = emu_to_in(size.get("cx"))
            height = emu_to_in(size.get("cy"))
            if width > 0 and height > 0:
                return width, height
    except Exception:
        pass
    return SLIDE_WIDE


def extract_shape_text(element: ET.Element) -> str:
    text_parts = []
    for text in element.findall(".//a:t", NS):
        if text.text:
            text_parts.append(re.sub(r"\s+", " ", text.text).strip())
    return " ".join(part for part in text_parts if part)


def extract_font_size_pt(element: ET.Element) -> float | None:
    sizes: list[float] = []
    for run_props in element.findall(".//a:rPr", NS) + element.findall(".//a:defRPr", NS):
        value = run_props.get("sz")
        if value:
            try:
                sizes.append(int(value) / 100)
            except ValueError:
                continue
    return min(sizes) if sizes else None


def extract_bbox(element: ET.Element) -> dict[str, float] | None:
    xfrm = element.find(".//a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    bbox = {
        "x": emu_to_in(off.get("x")),
        "y": emu_to_in(off.get("y")),
        "w": emu_to_in(ext.get("cx")),
        "h": emu_to_in(ext.get("cy")),
    }
    if bbox["w"] <= 0 or bbox["h"] <= 0:
        return None
    return bbox


def element_kind(element: ET.Element) -> str:
    tag = element.tag.rsplit("}", 1)[-1]
    return {"sp": "shape", "pic": "picture", "graphicFrame": "graphicFrame"}.get(tag, tag)


def content_density_estimate(text: str, bbox: dict[str, float], font_pt: float | None) -> dict[str, Any]:
    if not text:
        return {"status": "not-text"}
    font = font_pt or 16.0
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_chars = len(text) - cjk_chars
    text_units = cjk_chars + latin_chars * 0.55
    chars_per_line = max(1.0, (bbox["w"] * 72) / max(font * 0.68, 1))
    estimated_lines = max(1, int((text_units / chars_per_line) + 0.999))
    line_height_in = font * 1.25 / 72
    required_height = estimated_lines * line_height_in
    return {
        "status": "estimated",
        "fontPt": round(font, 2),
        "estimatedLines": estimated_lines,
        "requiredHeightIn": round(required_height, 3),
        "heightRatio": round(required_height / bbox["h"], 2) if bbox["h"] else None,
    }


def is_body_text(text: str, bbox: dict[str, float], slide_height: float) -> bool:
    if len(text.strip()) < MIN_BODY_TEXT_LENGTH:
        return False
    if bbox["y"] > slide_height - FOOTER_BAND_IN:
        return False
    return True


def rect_area(bbox: dict[str, float]) -> float:
    return max(0.0, bbox["w"]) * max(0.0, bbox["h"])


def rect_intersection(a: dict[str, float], b: dict[str, float]) -> dict[str, float] | None:
    left = max(a["x"], b["x"])
    top = max(a["y"], b["y"])
    right = min(a["x"] + a["w"], b["x"] + b["w"])
    bottom = min(a["y"] + a["h"], b["y"] + b["h"])
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def inspect_layout(archive: zipfile.ZipFile, slide_names: list[str]) -> dict[str, Any]:
    width, height = slide_size(archive)
    report: dict[str, Any] = {
        "slideSizeIn": {"width": round(width, 3), "height": round(height, 3)},
        "status": "passed",
        "slides": [],
        "warnings": [],
        "errors": [],
        "notes": [
            "Layout QA is heuristic. It catches geometry, overlap, boundary, and text-capacity risks before manual rendered-page inspection."
        ],
    }

    for slide_index, slide_name in enumerate(slide_names, start=1):
        root = ET.fromstring(archive.read(slide_name))
        candidates = root.findall(".//p:sp", NS) + root.findall(".//p:pic", NS) + root.findall(".//p:graphicFrame", NS)
        elements: list[dict[str, Any]] = []
        slide_warnings: list[str] = []

        for order, element in enumerate(candidates, start=1):
            bbox = extract_bbox(element)
            if not bbox:
                continue
            text = extract_shape_text(element)
            kind = element_kind(element)
            font_pt = extract_font_size_pt(element)
            is_content = bool(text) or kind in {"picture", "graphicFrame"}
            item = {
                "order": order,
                "kind": kind,
                "bboxIn": {key: round(value, 3) for key, value in bbox.items()},
                "textPreview": text[:80],
                "textLength": len(text),
                "isContent": is_content,
            }
            if font_pt:
                item["minFontPt"] = round(font_pt, 2)

            if is_content:
                out_left = bbox["x"] < -SAFE_MARGIN_IN
                out_top = bbox["y"] < -SAFE_MARGIN_IN
                out_right = bbox["x"] + bbox["w"] > width + SAFE_MARGIN_IN
                out_bottom = bbox["y"] + bbox["h"] > height + SAFE_MARGIN_IN
                if out_left or out_top or out_right or out_bottom:
                    issue = (
                        f"Element {order} extends outside slide bounds "
                        f"(x={bbox['x']:.2f}, y={bbox['y']:.2f}, w={bbox['w']:.2f}, h={bbox['h']:.2f})."
                    )
                    item.setdefault("warnings", []).append(issue)
                    slide_warnings.append(issue)

                near_edge = (
                    bbox["x"] < SAFE_MARGIN_IN
                    or bbox["y"] < SAFE_MARGIN_IN
                    or bbox["x"] + bbox["w"] > width - SAFE_MARGIN_IN
                    or bbox["y"] + bbox["h"] > height - SAFE_MARGIN_IN
                )
                if text and near_edge:
                    issue = f"Text element {order} sits on the slide edge; verify it is not clipped."
                    item.setdefault("warnings", []).append(issue)
                    slide_warnings.append(issue)

            if text:
                density = content_density_estimate(text, bbox, font_pt)
                item["textFitEstimate"] = density
                if font_pt and font_pt < MIN_BODY_FONT_PT and is_body_text(text, bbox, height):
                    issue = f"Text element {order} uses {font_pt:.1f}pt, below the {MIN_BODY_FONT_PT:.1f}pt body minimum."
                    item.setdefault("warnings", []).append(issue)
                    slide_warnings.append(issue)
                if density.get("heightRatio") and density["heightRatio"] > 1.08:
                    issue = (
                        f"Text element {order} likely overflows its box "
                        f"(estimated height {density['requiredHeightIn']:.2f}in vs box {bbox['h']:.2f}in)."
                    )
                    item.setdefault("warnings", []).append(issue)
                    slide_warnings.append(issue)

            item["_bbox"] = bbox
            elements.append(item)

        content_elements = [element for element in elements if element["isContent"]]
        for left_idx, left in enumerate(content_elements):
            for right in content_elements[left_idx + 1 :]:
                if not (left["textLength"] or right["textLength"]):
                    continue
                intersection = rect_intersection(left["_bbox"], right["_bbox"])
                if not intersection:
                    continue
                min_area = min(rect_area(left["_bbox"]), rect_area(right["_bbox"]))
                ratio = rect_area(intersection) / min_area if min_area else 0.0
                if ratio >= OVERLAP_WARN_AREA_RATIO:
                    issue = (
                        f"Elements {left['order']} and {right['order']} overlap by {ratio:.0%} of the smaller box; "
                        "verify this is an intentional overlay and not hidden text or misalignment."
                    )
                    left.setdefault("warnings", []).append(issue)
                    right.setdefault("warnings", []).append(issue)
                    slide_warnings.append(issue)

        for item in elements:
            item.pop("_bbox", None)

        slide_report = {
            "index": slide_index,
            "file": slide_name,
            "contentElementCount": len(content_elements),
            "warnings": sorted(set(slide_warnings)),
            "elementsWithWarnings": [item for item in elements if item.get("warnings")],
        }
        if slide_warnings:
            report["warnings"].append(f"Slide {slide_index}: {len(set(slide_warnings))} layout risk(s).")
        report["slides"].append(slide_report)

    if report["warnings"]:
        report["status"] = "warning"
    return report


def inspect_package(pptx: Path) -> tuple[dict[str, Any], bool]:
    report: dict[str, Any] = {
        "path": str(pptx),
        "exists": pptx.exists(),
        "sizeBytes": pptx.stat().st_size if pptx.exists() else 0,
        "zipValid": False,
        "slideCount": 0,
        "slides": [],
        "mediaCount": 0,
        "mediaFiles": [],
        "warnings": [],
        "errors": [],
    }

    if not pptx.exists():
        report["errors"].append("PPTX file does not exist.")
        return report, False

    try:
        with zipfile.ZipFile(pptx) as archive:
            bad_member = archive.testzip()
            if bad_member:
                report["errors"].append(f"Corrupt ZIP member: {bad_member}")
                return report, False

            names = archive.namelist()
            slides = sorted(
                [name for name in names if re.match(r"ppt/slides/slide\d+\.xml$", name)],
                key=natural_slide_key,
            )
            media = sorted([name for name in names if name.startswith("ppt/media/") and not name.endswith("/")])
            report["zipValid"] = True
            report["slideCount"] = len(slides)
            report["mediaCount"] = len(media)
            report["mediaFiles"] = [Path(name).name for name in media]

            if not slides:
                report["errors"].append("No slide XML files found.")

            for index, slide_name in enumerate(slides, start=1):
                xml = archive.read(slide_name).decode("utf-8", errors="replace")
                texts = decode_text(xml)
                pictures = len(re.findall(r"<p:pic[\s>]", xml))
                shapes = len(re.findall(r"<p:sp[\s>]", xml))
                graphic_frames = len(re.findall(r"<p:graphicFrame[\s>]", xml))
                slide_report = {
                    "index": index,
                    "file": slide_name,
                    "textBlockCount": len(texts),
                    "textPreview": texts[:8],
                    "pictureCount": pictures,
                    "shapeCount": shapes,
                    "graphicFrameCount": graphic_frames,
                    "warnings": [],
                }
                if len(texts) == 0 and pictures == 0 and graphic_frames == 0:
                    slide_report["warnings"].append("Slide appears empty.")
                if pictures > 0 and len(texts) <= 2:
                    slide_report["warnings"].append(
                        "Slide is image-heavy; verify editability and full-slide raster fallback intent."
                    )
                report["slides"].append(slide_report)

            if media:
                report["warnings"].append("Media files are present; verify raster fallback intent and editability.")

            report["layoutQa"] = inspect_layout(archive, slides)
    except zipfile.BadZipFile:
        report["errors"].append("PPTX is not a valid ZIP package.")
    except Exception as exc:  # pragma: no cover - defensive report path
        report["errors"].append(f"Package inspection failed: {exc}")

    return report, not report["errors"]


def find_soffice() -> str | None:
    """在 macOS/Linux 上稳定查找 LibreOffice soffice 可执行文件。

    查找顺序：
    1. PATH 中的 soffice（Linux 常用路径、brew 安装等）
    2. macOS 标准 /Applications/LibreOffice.app
    3. macOS 下用户目录的 LibreOffice（如 TRAE 内置、homebrew --cask 自定义位置）
    4. Spotlight (mdfind) 搜索 LibreOffice bundle
    5. 常见的 Linux 安装路径
    """
    candidates: list[str | None] = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]

    home = Path.home()
    macos_user_candidates = [
        home / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice",
        home / "Library" / "Application Support" / "TRAE SOLO CN" / "ModularData"
        / "ai-agent" / "vm" / "tools" / "opt" / "libreoffice" / "LibreOffice.app"
        / "Contents" / "MacOS" / "soffice",
        home / "Library" / "Application Support" / "TRAE" / "ModularData"
        / "ai-agent" / "vm" / "tools" / "opt" / "libreoffice" / "LibreOffice.app"
        / "Contents" / "MacOS" / "soffice",
    ]
    candidates.extend(str(p) for p in macos_user_candidates)

    linux_candidates = [
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/usr/local/bin/soffice",
        "/opt/libreoffice/program/soffice",
        "/snap/bin/libreoffice",
    ]
    candidates.extend(linux_candidates)

    for candidate in candidates:
        if candidate and Path(candidate).exists() and Path(candidate).is_file():
            return str(candidate)

    if shutil.which("mdfind"):
        try:
            result = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == 'org.libreoffice.script'"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            for line in result.stdout.strip().splitlines():
                bundle = Path(line.strip())
                if not bundle:
                    continue
                soffice_path = bundle / "Contents" / "MacOS" / "soffice"
                if soffice_path.exists() and soffice_path.is_file():
                    return str(soffice_path)
        except Exception:
            pass

    return None


def run_command(command: list[str], timeout: int) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout[-4000:]


def render_with_soffice(pptx: Path, workspace: Path, timeout: int) -> dict[str, Any]:
    render_dir = workspace / "qa" / "rendered-pages"
    profile_dir = workspace / "cache" / "libreoffice-profile"
    render_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    visual: dict[str, Any] = {
        "status": "blocked",
        "renderer": "LibreOffice soffice",
        "pdf": None,
        "pngPages": [],
        "warnings": [],
        "errors": [],
    }

    soffice = find_soffice()
    if not soffice:
        visual["errors"].append(
            "LibreOffice soffice was not found. Visual PPTX QA is blocked; structural QA is not a substitute."
        )
        return visual

    command = [
        soffice,
        f"-env:UserInstallation=file://{profile_dir.resolve()}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(render_dir),
        str(pptx.resolve()),
    ]
    try:
        code, output = run_command(command, timeout)
    except subprocess.TimeoutExpired:
        visual["errors"].append(f"LibreOffice conversion timed out after {timeout} seconds.")
        return visual

    visual["convertCommand"] = command
    visual["convertOutput"] = output
    if code != 0:
        visual["errors"].append(f"LibreOffice conversion failed with exit code {code}.")
        return visual

    pdf = render_dir / f"{pptx.stem}.pdf"
    if not pdf.exists():
        pdf_candidates = sorted(render_dir.glob("*.pdf"), key=lambda item: item.stat().st_mtime, reverse=True)
        pdf = pdf_candidates[0] if pdf_candidates else pdf
    if not pdf.exists():
        visual["errors"].append("LibreOffice reported success but no PDF was produced.")
        return visual

    visual["pdf"] = str(pdf)
    png_pages = render_pdf_to_png(pdf, render_dir, timeout)
    visual["pngPages"] = [str(path) for path in png_pages]
    if png_pages:
        visual["status"] = "rendered"
    else:
        visual["status"] = "pdf-rendered"
        visual["warnings"].append("PDF was produced, but PNG page rendering tools were not available.")
    return visual


def select_representative_pages(package_report: dict[str, Any], visual_report: dict[str, Any]) -> list[dict[str, Any]]:
    slides = package_report.get("slides") or []
    if not slides:
        return []

    selected: list[tuple[str, int]] = [("cover", 1)]
    densest_text = max(slides, key=lambda slide: slide.get("textBlockCount", 0))
    densest_shapes = max(
        slides,
        key=lambda slide: slide.get("shapeCount", 0) + slide.get("graphicFrameCount", 0) + slide.get("pictureCount", 0),
    )
    selected.extend(
        [
            ("most-text-dense", int(densest_text["index"])),
            ("most-visual-elements", int(densest_shapes["index"])),
            ("closing", int(slides[-1]["index"])),
        ]
    )

    png_pages = visual_report.get("pngPages") or []
    unique: list[dict[str, Any]] = []
    seen: set[int] = set()
    for reason, page_index in selected:
        if page_index in seen:
            continue
        seen.add(page_index)
        entry: dict[str, Any] = {"reason": reason, "page": page_index}
        if 0 < page_index <= len(png_pages):
            entry["png"] = png_pages[page_index - 1]
        unique.append(entry)
    return unique


def render_pdf_to_png(pdf: Path, render_dir: Path, timeout: int) -> list[Path]:
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        prefix = render_dir / "page"
        command = [pdftoppm, "-png", "-r", "140", str(pdf), str(prefix)]
        code, _ = run_command(command, timeout)
        if code == 0:
            return sorted(render_dir.glob("page-*.png"))

    if importlib.util.find_spec("fitz"):
        import fitz  # type: ignore

        pages: list[Path] = []
        doc = fitz.open(pdf)
        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(140 / 72, 140 / 72), alpha=False)
            path = render_dir / f"page-{idx:02d}.png"
            pix.save(path)
            pages.append(path)
        doc.close()
        return pages

    return []


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    pptx = Path(args.pptx)
    workspace = Path(args.workspace) if args.workspace else default_workspace(pptx)
    report_path = Path(args.report) if args.report else workspace / "qa" / "pptx-qa-report.json"

    package_report, package_ok = inspect_package(pptx)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "pptx": package_report,
        "visualQa": {"status": "skipped", "errors": [], "warnings": []},
    }

    if args.render != "off":
        report["visualQa"] = render_with_soffice(pptx, workspace, args.timeout)
        report["visualQa"]["representativePages"] = select_representative_pages(package_report, report["visualQa"])

    write_report(report_path, report)

    print(f"PPTX QA report: {report_path}")
    print(f"Structural QA: {'ok' if package_ok else 'failed'}")
    print(f"Visual QA: {report['visualQa']['status']}")
    for page in report["visualQa"].get("representativePages", []):
        target = page.get("png") or f"page {page['page']}"
        print(f"Inspect {page['reason']}: {target}")

    if not package_ok:
        return 1
    if args.render == "required" and report["visualQa"]["status"] not in {"rendered", "pdf-rendered"}:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
