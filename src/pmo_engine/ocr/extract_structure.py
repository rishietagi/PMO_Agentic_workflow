"""Layout-aware OCR + structure extraction for the (scanned) RITA PDF.

Primary engine: marker-pdf (local, free) which does layout-aware OCR and
emits a structured block tree with heading levels, tables, and equations
intact. We run it once via its CLI in JSON mode, then normalize the block
tree into a flat, ordered list of `StructuredElement`s that the hierarchical
chunker (Phase 2) consumes. We also render a human-readable Markdown file to
data/processed/ for spot-checking against the rasterized originals.

Fallback: per-page PyMuPDF render + Tesseract OCR for pages marker mangles
(see `ocr_page_fallback`). Used surgically, not as the default path.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StructuredElement:
    """One ordered piece of the book, normalized from marker's block tree."""
    order: int
    page: int                 # 0-based page index as reported by marker
    block_type: str           # marker block type (SectionHeader, Table, ...)
    heading_level: int | None  # 1/2/3.. for headings, else None
    text: str                 # plain text (HTML stripped)
    html: str = ""           # original html (kept for tables/formulas)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Block types marker emits that we care about, mapped to coarse roles.
_HEADING_TYPES = {"SectionHeader", "Title"}
_TABLE_TYPES = {"Table", "TableGroup"}
_FORMULA_TYPES = {"Equation"}
_SKIP_TYPES = {"PageHeader", "PageFooter", "Figure", "Picture",
               "TableOfContents"}


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    # keep table structure readable: turn cell/row tags into separators first
    raw = re.sub(r"</t[hd]>", " | ", raw, flags=re.I)
    raw = re.sub(r"</tr>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", raw)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _page_from_id(block_id: str) -> int | None:
    """marker block ids look like '/page/3/Block/12' -> page 3."""
    if not block_id:
        return None
    m = re.search(r"/page/(\d+)", block_id)
    return int(m.group(1)) if m else None


def _heading_level(block: dict[str, Any]) -> int | None:
    btype = block.get("block_type", "")
    if btype not in _HEADING_TYPES:
        return None
    lvl = block.get("heading_level")
    if isinstance(lvl, int) and lvl > 0:
        return min(lvl, 6)
    if btype == "Title":
        return 1
    return 2  # unspecified SectionHeader -> treat as major section


def _walk(node: dict[str, Any], current_page: int,
          out: list[StructuredElement], counter: list[int]) -> None:
    """Depth-first walk of marker's JSON block tree in reading order."""
    page = _page_from_id(node.get("id", ""))
    if page is not None:
        current_page = page

    btype = node.get("block_type", "")
    children = node.get("children") or []

    # Tables/formulas: take the whole subtree as one atomic element, don't
    # descend (we never want to split a table across elements).
    if btype in _TABLE_TYPES or btype in _FORMULA_TYPES:
        html_raw = node.get("html", "")
        text = _strip_html(html_raw)
        if text:
            out.append(StructuredElement(
                order=counter[0], page=current_page, block_type=btype,
                heading_level=None, text=text, html=html_raw))
            counter[0] += 1
        return

    if btype in _SKIP_TYPES:
        return

    # Leaf text-bearing block (no children, or a heading/paragraph).
    hlevel = _heading_level(node)
    if not children:
        text = _strip_html(node.get("html", ""))
        if text:
            out.append(StructuredElement(
                order=counter[0], page=current_page, block_type=btype or "Text",
                heading_level=hlevel, text=text, html=node.get("html", "")))
            counter[0] += 1
        return

    # Heading container that also has children: emit the heading itself first.
    if hlevel is not None:
        text = _strip_html(node.get("html", ""))
        if text:
            out.append(StructuredElement(
                order=counter[0], page=current_page, block_type=btype,
                heading_level=hlevel, text=text, html=node.get("html", "")))
            counter[0] += 1

    for child in children:
        _walk(child, current_page, out, counter)


def normalize_marker_json(doc: dict[str, Any]) -> list[StructuredElement]:
    out: list[StructuredElement] = []
    counter = [0]
    _walk(doc, current_page=0, out=out, counter=counter)
    return out


def _find_marker_cli() -> str | None:
    # 1) PATH lookup
    for name in ("marker_single", "marker_single.exe"):
        path = shutil.which(name)
        if path:
            return path
    # 2) next to the running interpreter (the env's Scripts/bin dir is often
    #    not on PATH when invoked from a subprocess, e.g. our finisher chain)
    import sys
    base = Path(sys.executable).parent
    for cand in (base / "marker_single.exe", base / "marker_single",
                 base / "Scripts" / "marker_single.exe",
                 base / "bin" / "marker_single"):
        if cand.exists():
            return str(cand)
    return None


def run_marker(pdf_path: Path, out_dir: Path, max_pages: int | None = None,
               force_ocr: bool = True) -> Path:
    """Run marker_single in JSON mode. Returns path to the produced .json.

    force_ocr is on by default because the source has no text layer.
    """
    import os
    from pmo_engine import config

    cli = _find_marker_cli()
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [cli or "marker_single", str(pdf_path),
           "--output_dir", str(out_dir),
           "--output_format", "json"]
    if force_ocr:
        cmd.append("--force_ocr")
    if max_pages is not None:
        cmd += ["--page_range", f"0-{max_pages - 1}"]

    # GPU when available; cap surya batch sizes so 4 GB VRAM doesn't OOM.
    env = os.environ.copy()
    device = config.resolve_device()
    env["TORCH_DEVICE"] = device
    if device == "cuda":
        env.update(config.SURYA_GPU_BATCH)
    logger.info("Running marker on %s: %s", device, " ".join(cmd))
    # marker can take a long time on a scanned book; no timeout.
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error("marker failed (rc=%s):\n%s", result.returncode,
                     result.stderr[-2000:])
        raise RuntimeError(f"marker_single failed: {result.stderr[-500:]}")

    # marker writes <out_dir>/<sanitized_stem>/<sanitized_stem>.json — the
    # folder/file name may differ from the original (spaces sanitized), so
    # match any produced .json (excluding the *_meta.json sidecar) and pick the
    # largest, which is the content document.
    candidates = [c for c in out_dir.glob("**/*.json")
                  if not c.name.endswith("_meta.json")]
    if not candidates:
        raise FileNotFoundError(f"marker produced no JSON under {out_dir}")
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def elements_to_markdown(elements: list[StructuredElement]) -> str:
    """Render normalized elements back to Markdown for human spot-checking."""
    lines: list[str] = []
    for el in elements:
        if el.heading_level:
            lines.append("\n" + "#" * el.heading_level + " " + el.text + "\n")
        elif el.block_type in _TABLE_TYPES:
            lines.append(f"\n<!-- table p.{el.page} -->\n{el.text}\n")
        elif el.block_type in _FORMULA_TYPES:
            lines.append(f"\n$$ {el.text} $$\n")
        else:
            lines.append(el.text + "\n")
    return "\n".join(lines)


def ocr_page_fallback(pdf_path: Path, page_index: int, dpi: int = 300) -> str:
    """PyMuPDF render -> Tesseract OCR for a single mangled page.

    Degrades gracefully (returns "") if PyMuPDF/Tesseract aren't available so
    the primary marker path is never blocked by a missing fallback binary.
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        import io
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallback OCR deps unavailable (%s); skipping page %s",
                       exc, page_index)
        return ""
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tesseract fallback failed on page %s: %s",
                       page_index, exc)
        return ""


def save_elements(elements: list[StructuredElement], json_path: Path,
                  md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in elements], f, ensure_ascii=False,
                  indent=1)
    md_path.write_text(elements_to_markdown(elements), encoding="utf-8")
    logger.info("Saved %d elements -> %s (+ markdown %s)",
                len(elements), json_path.name, md_path.name)


def load_elements(json_path: Path) -> list[StructuredElement]:
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return [StructuredElement(**d) for d in data]
