#!/usr/bin/env python3
"""PPTX QA helper for DeckSmith.

This script provides deterministic structural checks and, when LibreOffice is
already available, PPTX-to-PDF/PNG render checks. It intentionally does not
install software and does not use WPS Office, whose macOS binary opens a GUI and
is not reliable for headless conversion.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


EMU_PER_INCH = 914400
SLIDE_WIDE = (13.333, 7.5)


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
    return [html.unescape(re.sub(r"\s+", " ", value)).strip() for value in values if value.strip()]


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
    except zipfile.BadZipFile:
        report["errors"].append("PPTX is not a valid ZIP package.")
    except Exception as exc:  # pragma: no cover - defensive report path
        report["errors"].append(f"Package inspection failed: {exc}")

    return report, not report["errors"]


def find_soffice() -> str | None:
    candidates = [
        shutil.which("soffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
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
    preview_dir = workspace / "previews" / "pptx"
    profile_dir = workspace / "cache" / "libreoffice-profile"
    preview_dir.mkdir(parents=True, exist_ok=True)
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
        str(preview_dir),
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

    pdf = preview_dir / f"{pptx.stem}.pdf"
    if not pdf.exists():
        pdf_candidates = sorted(preview_dir.glob("*.pdf"), key=lambda item: item.stat().st_mtime, reverse=True)
        pdf = pdf_candidates[0] if pdf_candidates else pdf
    if not pdf.exists():
        visual["errors"].append("LibreOffice reported success but no PDF was produced.")
        return visual

    visual["pdf"] = str(pdf)
    png_pages = render_pdf_to_png(pdf, preview_dir, timeout)
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


def render_pdf_to_png(pdf: Path, preview_dir: Path, timeout: int) -> list[Path]:
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        prefix = preview_dir / "page"
        command = [pdftoppm, "-png", "-r", "140", str(pdf), str(prefix)]
        code, _ = run_command(command, timeout)
        if code == 0:
            return sorted(preview_dir.glob("page-*.png"))

    if importlib.util.find_spec("fitz"):
        import fitz  # type: ignore

        pages: list[Path] = []
        doc = fitz.open(pdf)
        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(140 / 72, 140 / 72), alpha=False)
            path = preview_dir / f"page-{idx:02d}.png"
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
