"""Render the sample SOW markdown into a clean multi-page PDF (PyMuPDF Story).

One-off helper used to produce sample/AI_Future_Operating_Model_SOW.pdf so the
app's PDF-upload flow has a realistic SOW to demo with.
"""
from __future__ import annotations

import html as _html
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sample" / "AI_Future_Operating_Model_SOW.md"
OUT = ROOT / "sample" / "AI_Future_Operating_Model_SOW.pdf"


def md_to_html(md: str) -> str:
    out: list[str] = []
    list_mode: str | None = None  # 'ul' | 'ol' | None

    def close_list():
        nonlocal list_mode
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None

    def inline(t: str) -> str:
        t = _html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
        return t

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        if line.startswith("---"):
            close_list()
            out.append("<hr/>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_list()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if list_mode != "ul":
                close_list(); out.append("<ul>"); list_mode = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if list_mode != "ol":
                close_list(); out.append("<ol>"); list_mode = "ol"
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue
        close_list()
        out.append(f"<p>{inline(line)}</p>")
    close_list()

    css = """
      h1 { font-size: 19px; color: #1a2452; margin: 0 0 6px; }
      h2 { font-size: 14px; color: #2b3a7a; margin: 14px 0 4px;
           border-bottom: 1px solid #c9d2f0; padding-bottom: 2px; }
      h3 { font-size: 12px; color: #3a4a8a; margin: 10px 0 3px; }
      h4 { font-size: 11px; color: #444; margin: 8px 0 2px; }
      p, li { font-size: 10.5px; line-height: 1.5; color: #1c2230; }
      ul, ol { margin: 2px 0 6px 16px; }
      hr { border: none; border-top: 1px solid #c9d2f0; margin: 10px 0; }
    """
    return f"<html><head><style>{css}</style></head><body>{''.join(out)}</body></html>"


def main() -> int:
    if not SRC.exists():
        print("missing", SRC); return 1
    html = md_to_html(SRC.read_text(encoding="utf-8"))
    story = fitz.Story(html=html)
    writer = fitz.DocumentWriter(str(OUT))
    media = fitz.paper_rect("a4")
    where = media + (54, 54, -54, -60)
    more = 1
    pages = 0
    while more:
        dev = writer.begin_page(media)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        pages += 1
    writer.close()
    print(f"Wrote {OUT} ({pages} pages, {OUT.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
