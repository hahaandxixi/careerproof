"""Task 72 step 1: write synthetic A/B fixtures to disk.

No single interpreter has both PDF libraries (PyMuPDF is only in the backend .venv,
pypdfium2 only in the runtime python), so fixture creation is split by the library
that is actually available:

  --part reportlab  reportlab-only fixtures  -> runtime python
  --part pymupdf    PyMuPDF-built fixtures   -> backend .venv

Both parts append to the same manifest, keyed by SHA256 of the written bytes, so the
readers later prove they consumed identical inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
FIXTURES = OUT / "fixtures"
FIXTURES.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT / "fixtures-manifest.json"


def load_manifest() -> list[dict]:
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return []


def write(name: str, payload: bytes, note: str) -> None:
    path = FIXTURES / f"{name}.pdf"
    path.write_bytes(payload)
    manifest = [row for row in load_manifest() if row["fixture"] != name]
    manifest.append(
        {
            "fixture": name,
            "file": path.name,
            "note": note,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    manifest.sort(key=lambda row: row["fixture"])
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name:22} bytes={len(payload):8} {note}")


def part_reportlab() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    def cjk() -> str:
        if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 760, "FastAPI health endpoint returns status ok")
    c.drawString(72, 740, "second line for citation offsets")
    c.showPage()
    c.save()
    write("english_text", buf.getvalue(), "2 text lines, 1 page")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont(cjk(), 12)
    c.drawString(72, 760, "中文简历：使用 FastAPI 编写健康检查接口")
    c.drawString(72, 740, "第二行用于字符计数对照")
    c.showPage()
    c.save()
    write("chinese_text", buf.getvalue(), "CJK CID font, 2 lines")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for index, line in enumerate(["line one", "line two", "line three"]):
        c.drawString(72, 760 - index * 20, line)
    c.showPage()
    c.save()
    write("plain_lines", buf.getvalue(), "3 separated text lines")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for index in range(3):
        c.drawString(72, 760, f"page body {index + 1}")
        c.showPage()
    c.save()
    write("multi_page", buf.getvalue(), "3 pages, page number in text")


def part_pymupdf() -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "rotated ninety degrees")
    page.set_rotation(90)
    write("rotated_90", doc.tobytes(), "1 page, /Rotate 90")
    doc.close()

    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 60), 0)
    pix.clear_with(255)
    page.insert_image(fitz.Rect(60, 60, 480, 180), pixmap=pix)
    write("scanned_image_only", doc.tobytes(), "image-only page, no text layer")
    doc.close()

    doc = fitz.open()
    line = "A" * 200
    for _ in range(3000):
        page = doc.new_page()
        page.insert_text((20, 30), line, fontsize=4)
    write("over_char_cap", doc.tobytes(), "3000 pages x 200 chars")
    doc.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["reportlab", "pymupdf"], required=True)
    args = parser.parse_args()
    if args.part == "reportlab":
        part_reportlab()
    else:
        part_pymupdf()
    print(f"\nmanifest now has {len(load_manifest())} fixtures: {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
