"""Task 71 independent probe: PDF boundary behaviours NOT already asserted in
app/tests/test_document_ocr.py (which already covers rotation + pixel-budget
rejection before bitmap allocation, so those are deliberately not repeated here).

Every input is a small synthetic file written under the probe's own scratch dir.
No production parser file is modified. Each case records the outcome class:

  AppError(code) -> a deliberate, user-facing rejection
  other exception -> the caller would see an unhandled failure (500)
  sections       -> accepted

Also records where the character limit is enforced, since the card names it.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

SCRATCH = Path(os.environ["T71_SCRATCH"])
SCRATCH.mkdir(parents=True, exist_ok=True)

import fitz  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.exceptions import AppError  # noqa: E402
from app.tools.document_parser import parse_document  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def _slow_parse(path: Path, mime_type: str) -> list:
    """Module-level so run_isolated can pickle it to the worker process."""
    import time

    time.sleep(5)
    return []


def record(case: str, outcome: str, detail: str = "") -> None:
    RESULTS.append((case, outcome, detail))
    print(f"[{outcome}] {case}" + (f" :: {detail}" if detail else ""))


def classify(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, AppError):
        code = getattr(exc, "code", None)
        return f"AppError(code={code})", f"{type(exc).__name__}: {exc}"
    return "UNHANDLED", f"{type(exc).__name__}: {str(exc)[:160]}"


def run(case: str, path: Path, mime: str) -> None:
    try:
        sections = parse_document(path, mime)
        record(case, "accepted", f"sections={len(sections)}")
    except BaseException as exc:  # noqa: BLE001 - classifying is the point
        outcome, detail = classify(exc)
        record(case, outcome, detail)


def make_text_pdf(path: Path, pages: int = 1, text: str = "示例正文") -> None:
    with fitz.open() as document:
        for index in range(pages):
            page = document.new_page()
            page.insert_text((72, 100), f"{text} {index + 1}")
        document.save(path)


def main() -> int:
    print(f"fitz={fitz.__doc__} settings: ocr_enabled={settings.ocr_enabled} "
          f"ocr_max_pages={settings.ocr_max_pages} "
          f"ocr_max_image_pixels={settings.ocr_max_image_pixels} "
          f"max_document_characters={settings.max_document_characters}")

    # 1. Zero pages: no text, no page to OCR. PyMuPDF refuses to *write* such a
    #    document, so the minimal structure is assembled by hand.
    empty_pages = SCRATCH / "zero-pages.pdf"
    empty_pages.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
        b"%%EOF\n"
    )
    run("zero-page PDF", empty_pages, "application/pdf")

    # 2. Text PDF above the character limit: must the parser reject it, or does
    #    the limit only apply downstream? Build it so the extracted text really is
    #    over the limit, and verify that before parsing.
    over_chars = SCRATCH / "over-characters.pdf"
    huge = "A" * (settings.max_document_characters + 5_000)
    with fitz.open() as document:
        remaining = huge
        while remaining:
            page = document.new_page()
            chunk, remaining = remaining[:60_000], remaining[60_000:]
            page.insert_textbox(fitz.Rect(20, 20, 580, 820), chunk, fontsize=2)
        document.save(over_chars)
    with fitz.open(over_chars) as check:
        extracted = sum(len(p.get_text("text").strip()) for p in check)
        page_count = check.page_count
    print(
        f"over-limit PDF extracted characters={extracted} "
        f"(limit={settings.max_document_characters}, pages={page_count})"
    )
    run("text PDF above max_document_characters", over_chars, "application/pdf")

    # 3. Encrypted PDF (user password set): can it be opened and iterated?
    encrypted = SCRATCH / "encrypted.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), "机密正文")
        document.save(
            encrypted,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    run("encrypted PDF (user password)", encrypted, "application/pdf")

    # 4. Corrupted PDF: valid header, garbage body.
    corrupted = SCRATCH / "corrupted.pdf"
    corrupted.write_bytes(b"%PDF-1.7\n" + b"\x00\xff" * 4096 + b"\n%%EOF\n")
    run("corrupted PDF", corrupted, "application/pdf")

    # 5. Non-PDF file renamed to .pdf.
    fake = SCRATCH / "notreally.pdf"
    fake.write_bytes(b"this is plainly not a pdf\n" * 20)
    run("plain text renamed to .pdf", fake, "application/pdf")

    # 6. Corrupted DOCX: zip with junk.
    bad_docx = SCRATCH / "bad.docx"
    bad_docx.write_bytes(b"PK\x03\x04" + b"\x00" * 512)
    run("corrupted DOCX", bad_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # 7. Zero-byte PDF.
    zero = SCRATCH / "zero-byte.pdf"
    zero.write_bytes(b"")
    run("zero-byte PDF", zero, "application/pdf")

    # 8. Page-count semantics: OCR only runs on empty-text pages and only while
    #    ocr_pages < ocr_max_pages. Show the arithmetic without rendering anything.
    pages = 12
    limit = settings.ocr_max_pages
    print(
        f"\npage-count semantics: a {pages}-page all-scanned PDF with "
        f"ocr_max_pages={limit} would OCR at most {min(pages, limit)} pages and "
        f"leave {pages - min(pages, limit)} pages without OCR text."
    )

    # 9. Native worker timeout cleanup: a long sleep inside run_isolated must
    #    raise the 4026 timeout AppError rather than hang the caller. The callable
    #    must be module-level to be picklable to the worker process.
    from app.services.task_runner import run_isolated

    async def probe_worker() -> None:
        try:
            await run_isolated(_slow_parse, zero, "application/pdf", timeout_seconds=1)
            record("isolated worker timeout", "accepted", "worker returned instead of timing out")
        except BaseException as exc:  # noqa: BLE001
            outcome, detail = classify(exc)
            record("isolated worker timeout", outcome, detail)

    asyncio.run(probe_worker())

    # 10. Where is max_document_characters actually enforced?
    backend_root = Path(os.environ["PYTHONPATH"].split(os.pathsep)[0])
    scanned = backend_root / "app"
    print(f"\nenforcement of max_document_characters (scanning {scanned}):")
    hits = 0
    for path in scanned.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "max_document_characters" in line:
                hits += 1
                print(f"  {path.relative_to(backend_root)}:{number}: {line.strip()}")
    if not hits:
        print("  (none found)")

    print("\n--- summary ---")
    for case, outcome, detail in RESULTS:
        print(f"{outcome:22} | {case} | {detail}")
    unhandled = [r for r in RESULTS if r[1] == "UNHANDLED"]
    print(f"unhandled cases: {len(unhandled)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
