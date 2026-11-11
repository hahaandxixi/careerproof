"""Task 72 step 2: read every fixture with ONE reader and emit JSON.

Invoked twice with a different interpreter, because the two readers live in
different environments:

  runtime python  (pypdfium2 5.14.0)  -> --reader pdfium
  backend .venv   (PyMuPDF 1.26.4)   -> --reader pymupdf

The same fixture files are used for both, and the fixture sha256 is copied into the
output so a reader can never silently see different bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
FIXTURES = OUT / "fixtures"
HARNESS55 = OUT.parent / "20261015-harness55-pdfium-prototype" / "prototype.py"
BACKEND = OUT.parents[2] / "backend"


def load_prototype():
    spec = importlib.util.spec_from_file_location("harness55_prototype", HARNESS55)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolve their annotations through sys.modules[cls.__module__],
    # so the module must be registered before execution.
    sys.modules["harness55_prototype"] = module
    spec.loader.exec_module(module)
    return module


def sections_pymupdf(path: Path) -> tuple[list[dict], str]:
    import fitz

    rows: list[dict] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document):
            text = page.get_text("text").strip()
            if text:
                rows.append({"type": "page", "page": index + 1, "text": text})
    return rows, ""


def sections_pdfium(path: Path) -> tuple[list[dict], str]:
    prototype = load_prototype()
    adapter = prototype.PdfiumPdfAdapter(
        recognizer=lambda _png: prototype.OcrResult("", 0.0, 0),
        ocr_enabled=True,
        ocr_max_pages=10,
    )
    try:
        sections = adapter.parse(path)
    except Exception as exc:  # noqa: BLE001 - the adapter's own error class is expected
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    return (
        [
            {"type": s.section_type, "page": s.page_number, "text": s.content}
            for s in sections
        ],
        "",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", choices=["pymupdf", "pdfium"], required=True)
    args = parser.parse_args()

    manifest = json.loads((OUT / "fixtures-manifest.json").read_text(encoding="utf-8"))
    reader = sections_pymupdf if args.reader == "pymupdf" else sections_pdfium

    results = []
    for entry in manifest:
        path = FIXTURES / entry["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows, error = reader(path)
        joined = "\n".join(row["text"] for row in rows)
        results.append(
            {
                "fixture": entry["fixture"],
                "note": entry["note"],
                "file_sha256": digest,
                "bytes": entry["bytes"],
                "error": error,
                "section_count": len(rows),
                "page_numbers": [row["page"] for row in rows],
                "types": [row["type"] for row in rows],
                "total_chars": sum(len(row["text"]) for row in rows),
                "sha256_of_joined_text": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
                "first_120": joined[:120],
            }
        )
        print(
            f"{args.reader:8} {entry['fixture']:20} sections={len(rows):4} "
            f"pages={[r['page'] for r in rows][:6]} chars={results[-1]['total_chars']:7} "
            f"err={error[:40]!r}"
        )

    target = OUT / f"read-{args.reader}.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
