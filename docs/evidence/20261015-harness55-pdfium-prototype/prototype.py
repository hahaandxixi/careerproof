#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""harness55: executable PDFium (pypdfium2) adapter prototype + synthetic adversarial tests.

What this is
------------
A standalone prototype of the PDF reading path of ``backend/app/tools/document_parser.py``
rewritten on pypdfium2/PDFium instead of PyMuPDF, plus a self-contained adversarial test
harness that builds every input PDF in memory. It imports nothing from the application, so
it proves the behaviour of the *idea* without touching production code.

Hard rules encoded in the prototype (mirroring the production contract)
----------------------------------------------------------------------
* native English/CJK text is extracted as text and never rendered or OCR'd;
* blank / scanned / mixed pages keep 1-based page numbers (``index + 1``), exactly like
  ``parse_document`` does today;
* the number of OCR calls is capped by ``ocr_max_pages`` (same semantics as the current
  ``ocr_pages < settings.ocr_max_pages`` budget);
* the pixel budget is refused **before** any bitmap is allocated: the guard computes
  ``ceil(w * scale) * ceil(h * scale)`` from ``page.get_size()`` and only then may
  ``page.render()`` run (the current PyMuPDF code allocates the pixmap first and checks
  afterwards);
* corrupt and encrypted PDFs produce explicit, classified errors instead of a raw
  exception leaking out of the parser; corruption and encryption are distinguishable;
* ``PdfDocument`` / ``PdfPage`` / ``PdfTextPage`` / ``PdfBitmap`` are closed promptly,
  including on every failure path (only ``PdfDocument`` is a context manager in
  pypdfium2 5.14.0, so everything else needs ``try/finally``);
* OCR is an **explicit injected callback** fed with PNG bytes. No real OCR engine, no
  model, no network. With ``recognizer=None`` the prototype behaves like production with
  OCR disabled;
* PDFium is documented as not thread-safe, so this prototype only ever isolates by
  process and never adds a parsing thread: it refuses to be used from a second thread
  instead of pretending to be safe.

Usage
-----
    python prototype.py                       # run the checks, print log + results.json
    python prototype.py --no-persist-fixtures # skip the attempt to write fixtures
    python prototype.py --verify-log <file>   # verify a transcribed run log
    python prototype.py --verify-results <file> --expected-sha256 <hex>

Writes: nothing except an *attempt* to drop the synthetic fixtures into the sanctioned
directory (``backend/.tmp/pdfium55-fixtures``). Fixtures are otherwise kept in memory, and
the outcome of that attempt is recorded in the results JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "backend" / ".tmp" / "pdfium55-fixtures"

LOG_MARKER_PREFIX = "===== PDFIUM55 "
CJK_FONT_NAME = "STSong-Light"
OCR_IMAGE_MARKER = "[OCR识别文本"

# Production codes (backend/app/core/exceptions.py + document_parser.py) reused verbatim,
# so the migration diff stays about behaviour and not about error numbering.
CODE_UNSUPPORTED = 4020
CODE_NO_TEXT = 4024
CODE_OCR_UNAVAILABLE = 4025
CODE_LIMIT = 4026


# --------------------------------------------------------------------------------------
# Contract types (mirrors of app.tools.document_parser / app.tools.ocr, no app import)
# --------------------------------------------------------------------------------------
class PdfParseError(Exception):
    """Stand-in for app.core.exceptions.AppError(message, code=...) plus a reason tag."""

    def __init__(self, message: str, *, code: int = CODE_NO_TEXT, reason: str = "pdf_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.reason = reason

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}/{self.reason}] {self.message}"


@dataclass(frozen=True, slots=True)
class DocumentSection:
    section_type: str
    content: str
    page_number: int | None


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    average_confidence: float | None
    line_count: int


def marked_ocr_text(result: OcrResult) -> str:
    """Copy of app.tools.ocr.marked_ocr_text so OCR output stays marked as unverified."""
    confidence = (
        f"{result.average_confidence:.0%}" if result.average_confidence is not None else "未提供"
    )
    return f"{OCR_IMAGE_MARKER}｜平均置信度 {confidence}｜请对照原图复核]\n{result.text}"


# --------------------------------------------------------------------------------------
# Instrumentation: count real pypdfium2 lifecycle events without changing behaviour
# --------------------------------------------------------------------------------------
_KIND_BY_CLASS = {
    "PdfDocument": "document",
    "PdfPage": "page",
    "PdfTextPage": "textpage",
    "PdfBitmap": "bitmap",
}


class _Counted:
    """Transparent proxy that counts open/close/render/text events on real objects."""

    def __init__(self, target: Any, kind: str, ledger: "CountingPdfium") -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_ledger", ledger)
        object.__setattr__(self, "_closed", False)

    # container protocol so `len(doc)` / `doc[i]` / `for page in doc` keep working
    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_target"))

    def __getitem__(self, index: int) -> Any:
        ledger = object.__getattribute__(self, "_ledger")
        return ledger.wrap(object.__getattribute__(self, "_target")[index])

    def __iter__(self) -> Iterable[Any]:
        for index in range(len(self)):
            yield self[index]

    def __getattr__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_target")
        ledger = object.__getattribute__(self, "_ledger")
        kind = object.__getattribute__(self, "_kind")
        attr = getattr(target, name)
        if not callable(attr):
            return attr
        if name == "close":
            def close(*args, **kwargs):
                if not object.__getattribute__(self, "_closed"):
                    object.__setattr__(self, "_closed", True)
                    ledger.closed[kind] += 1
                return attr(*args, **kwargs)

            return close
        if name == "render":
            def render(*args, **kwargs):
                ledger.render_calls += 1
                result = attr(*args, **kwargs)
                return ledger.wrap(result)

            return render
        if name == "get_textpage":
            def get_textpage(*args, **kwargs):
                return ledger.wrap(attr(*args, **kwargs))

            return get_textpage
        if name == "get_text_range":
            def get_text_range(*args, **kwargs):
                ledger.text_calls += 1
                return attr(*args, **kwargs)

            return get_text_range
        return attr


class CountingPdfium:
    """Module proxy: forwards everything, counts resources and the render/text entry points."""

    def __init__(self, real_module: Any) -> None:
        self._real = real_module
        self.opened: dict[str, int] = {kind: 0 for kind in _KIND_BY_CLASS.values()}
        self.closed: dict[str, int] = {kind: 0 for kind in _KIND_BY_CLASS.values()}
        self.render_calls = 0
        self.text_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def wrap(self, obj: Any) -> Any:
        kind = _KIND_BY_CLASS.get(type(obj).__name__)
        if kind is None:
            return obj
        self.opened[kind] += 1
        return _Counted(obj, kind, self)

    def PdfDocument(self, *args: Any, **kwargs: Any) -> Any:  # noqa: N802 - mirrors pypdfium2
        document = self._real.PdfDocument(*args, **kwargs)  # may raise: not counted as opened
        self.opened["document"] += 1
        return _Counted(document, "document", self)

    def balanced(self) -> bool:
        return self.opened == self.closed

    def snapshot(self) -> dict[str, Any]:
        return {
            "opened": dict(self.opened),
            "closed": dict(self.closed),
            "render_calls": self.render_calls,
            "text_calls": self.text_calls,
            "balanced": self.balanced(),
        }


# --------------------------------------------------------------------------------------
# The prototype adapter
# --------------------------------------------------------------------------------------
@dataclass
class ParseStats:
    pages_total: int = 0
    native_text_pages: int = 0
    ocr_pages: int = 0
    ocr_skipped_pages: int = 0
    scanned_pages: int = 0
    predicted_pixels: list[int] = field(default_factory=list)
    render_calls: int = 0
    recognizer_calls: int = 0
    recognizer_payload_bytes: list[int] = field(default_factory=list)


class PdfiumPdfAdapter:
    """Standalone PDF reader: PDFium backend, injected OCR recognizer, explicit guards."""

    def __init__(
        self,
        *,
        pdfium_module: Any = None,
        recognizer: Callable[[bytes], OcrResult] | None = None,
        ocr_enabled: bool = True,
        ocr_max_pages: int = 10,
        ocr_min_confidence: float = 0.5,
        ocr_max_image_pixels: int = 20_000_000,
        render_scale: float = 2.0,
        password: str | None = None,
        thread_guard: bool = True,
    ) -> None:
        if pdfium_module is None:
            import pypdfium2 as pdfium_module  # local import: keeps the module import lazy

        self._pdfium = CountingPdfium(pdfium_module)
        self.recognizer = recognizer
        self.ocr_enabled = ocr_enabled
        self.ocr_max_pages = ocr_max_pages
        self.ocr_min_confidence = ocr_min_confidence
        self.ocr_max_image_pixels = ocr_max_image_pixels
        self.render_scale = render_scale
        self.password = password
        self.thread_guard = thread_guard
        self._owner_thread: int | None = None
        self.stats = ParseStats()

    # -- helpers -----------------------------------------------------------------
    @property
    def ledger(self) -> CountingPdfium:
        return self._pdfium

    def _claim_thread(self) -> None:
        """PDFium is not thread-safe; refuse a second thread instead of racing."""
        if not self.thread_guard:
            return
        current = threading.get_ident()
        if self._owner_thread is None:
            self._owner_thread = current
        elif current != self._owner_thread:
            raise PdfParseError(
                "PDFium非线程安全，解析只能在绑定的单一进程/线程中执行",
                code=CODE_OCR_UNAVAILABLE,
                reason="pdf_thread_affinity",
            )

    def _classify_open_error(self, exc: BaseException) -> PdfParseError:
        raw = getattr(self._pdfium, "raw", None)
        err_password = getattr(raw, "FPDF_ERR_PASSWORD", 4)
        err_format = getattr(raw, "FPDF_ERR_FORMAT", 3)
        err_file = getattr(raw, "FPDF_ERR_FILE", 2)
        err_code = getattr(exc, "err_code", None)
        if err_code == err_password:
            return PdfParseError(
                "PDF已加密，需要密码才能解析，请提供密码或上传未加密的导出件",
                code=CODE_NO_TEXT,
                reason="pdf_encrypted",
            )
        if err_code in (err_format, err_file):
            return PdfParseError(
                "PDF文件损坏或格式不受支持，请重新导出后再上传",
                code=CODE_NO_TEXT,
                reason="pdf_corrupt",
            )
        return PdfParseError(
            "PDF无法读取，请确认文件完整后重试", code=CODE_NO_TEXT, reason="pdf_unreadable"
        )

    def _open(self, target: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if self.password is not None:
            kwargs["password"] = self.password
        try:
            return self._pdfium.PdfDocument(target, **kwargs)
        except PdfParseError:
            raise
        except BaseException as exc:  # pypdfium2 raises PdfiumError (RuntimeError subclass)
            error = self._classify_open_error(exc)
            error.detail = f"{type(exc).__name__}: {exc}"  # type: ignore[attr-defined]
            raise error from exc

    def _predicted_pixels(self, page: Any) -> int:
        """Pixels render() would allocate; computed from geometry, never by allocating."""
        width_pt, height_pt = page.get_size()
        if not (width_pt > 0 and height_pt > 0):
            raise PdfParseError(
                "PDF页面尺寸异常，无法安全解析", code=CODE_NO_TEXT, reason="pdf_bad_geometry"
            )
        return math.ceil(width_pt * self.render_scale) * math.ceil(height_pt * self.render_scale)

    def _render_png(self, page: Any) -> bytes:
        """Render to a PNG the OCR contract can consume; bitmap and PIL image are closed."""
        bitmap = page.render(scale=self.render_scale)
        try:
            image = bitmap.to_pil()
            try:
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()
            finally:
                image.close()
        finally:
            bitmap.close()

    def _recognize(self, png: bytes) -> OcrResult:
        if self.recognizer is None:
            raise PdfParseError(
                "当前环境未启用OCR，请上传文字版PDF、DOCX或TXT",
                code=CODE_OCR_UNAVAILABLE,
                reason="ocr_unavailable",
            )
        self.stats.recognizer_calls += 1
        self.stats.recognizer_payload_bytes.append(len(png))
        try:
            return self.recognizer(png)
        except PdfParseError:
            raise
        except BaseException as exc:
            raise PdfParseError(
                "OCR识别失败，请上传更清晰的原图或文字版文档",
                code=CODE_OCR_UNAVAILABLE,
                reason="ocr_failed",
            ) from exc

    # -- entry points ------------------------------------------------------------
    def parse(self, path: str | Path) -> list[DocumentSection]:
        resolved = Path(path)
        if not resolved.exists():
            raise PdfParseError(
                "文件不存在或已被移除，请重新上传", code=CODE_NO_TEXT, reason="pdf_missing"
            )
        return self._parse(resolved, str(resolved))

    def parse_source(self, source: bytes | bytearray | io.BytesIO, *, name: str = "<memory>") -> list[DocumentSection]:
        if isinstance(source, (bytes, bytearray)):
            payload: Any = bytes(source)
        elif isinstance(source, io.BytesIO):
            payload = source
        else:
            raise PdfParseError(
                "仅支持PDF文件输入", code=CODE_UNSUPPORTED, reason="pdf_bad_source"
            )
        return self._parse(payload, name)

    def _parse(self, target: Any, display: str) -> list[DocumentSection]:
        self._claim_thread()
        self.stats = ParseStats()
        document = self._open(target)
        sections: list[DocumentSection] = []
        try:
            try:
                pages_total = len(document)
            except BaseException as exc:
                raise self._classify_open_error(exc) from exc
            self.stats.pages_total = pages_total
            for index in range(pages_total):
                page_number = index + 1
                section = self._parse_page(document, index, page_number)
                if section is not None:
                    sections.append(section)
            if not sections:
                raise PdfParseError(
                    "PDF未提取或识别到可分析文字，请上传清晰扫描件或文字版文档",
                    code=CODE_NO_TEXT,
                    reason="pdf_no_text",
                )
            return sections
        finally:
            document.close()
            self.stats.render_calls = self._pdfium.render_calls

    def _parse_page(self, document: Any, index: int, page_number: int) -> DocumentSection | None:
        page = document[index]
        try:
            try:
                textpage = page.get_textpage()
                try:
                    text = (textpage.get_text_range() or "").strip()
                finally:
                    textpage.close()
            except PdfParseError:
                raise
            except BaseException as exc:
                raise PdfParseError(
                    "PDF页面内容无法读取，请重新导出后再上传",
                    code=CODE_NO_TEXT,
                    reason="pdf_page_error",
                ) from exc

            if text:
                self.stats.native_text_pages += 1
                return DocumentSection("page", text, page_number)

            # Blank / scanned / image-only page: this is the only path that may OCR.
            self.stats.scanned_pages += 1
            if not self.ocr_enabled or self.stats.ocr_pages >= self.ocr_max_pages:
                self.stats.ocr_skipped_pages += 1
                return None

            predicted = self._predicted_pixels(page)  # BEFORE render(): no bitmap yet
            self.stats.predicted_pixels.append(predicted)
            if predicted > self.ocr_max_image_pixels:
                raise PdfParseError(
                    "PDF页面像素过大，无法安全进行OCR识别",
                    code=CODE_LIMIT,
                    reason="pdf_pixel_budget",
                )
            png = self._render_png(page)
            result = self._recognize(png)
            self.stats.ocr_pages += 1
            if result.text:
                return DocumentSection("ocr_page", marked_ocr_text(result), page_number)
            return None
        finally:
            page.close()


# --------------------------------------------------------------------------------------
# Synthetic fixtures (all in memory; the sanctioned directory is only ever attempted)
# --------------------------------------------------------------------------------------
def _register_cjk_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if CJK_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT_NAME))
    return CJK_FONT_NAME


def _scan_image():
    from PIL import Image, ImageDraw

    image = Image.new("L", (600, 800), 255)
    draw = ImageDraw.Draw(image)
    for row, y in enumerate(range(60, 740, 40)):
        draw.rectangle([60, y, 60 + (480 if row % 3 == 0 else 300), y + 14], fill=0)
    return image


def _build_pdf(specs: list[dict], *, pagesize=(595.276, 841.89), rotate: int = 0, encrypt: Any = None) -> bytes:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    buffer = io.BytesIO()
    kwargs: dict[str, Any] = {"pagesize": pagesize, "pageCompression": 1}
    if encrypt is not None:
        kwargs["encrypt"] = encrypt
    pdf = rl_canvas.Canvas(buffer, **kwargs)
    if rotate:
        pdf.setPageRotation(rotate)
    for spec in specs:
        kind = spec["kind"]
        if kind in ("text_en", "text_cn"):
            font = "Helvetica" if kind == "text_en" else _register_cjk_font()
            size = spec.get("font_size", 14)
            pdf.setFont(font, size)
            y = pagesize[1] - 72
            for line in spec["lines"]:
                pdf.drawString(72, y, line)
                y -= size * 1.6
        elif kind == "scan":
            image = _scan_image()
            pdf.drawImage(
                ImageReader(image), 40, 40, width=pagesize[0] - 80, height=pagesize[1] - 80
            )
        elif kind == "blank":
            pass
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown fixture page kind: {kind}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_fixtures() -> dict[str, bytes]:
    from reportlab import rl_config
    from reportlab.lib.pdfencrypt import StandardEncryption

    # Fixed timestamps and producer string: the synthetic fixtures are byte-stable, so the
    # hashes recorded in results.json can be re-derived by anyone re-running this file.
    rl_config.invariant = 1

    mixed = _build_pdf(
        [
            {"kind": "text_en", "lines": ["Native FastAPI resume", "Backend engineer, 5 years"]},
            {"kind": "scan"},
            {"kind": "text_cn", "lines": ["个人简历 数据库备份恢复记录", "项目经历：用户调研 20份访谈"]},
            {"kind": "scan"},
        ]
    )
    tail_text = _build_pdf(
        [
            {"kind": "blank"},
            {"kind": "blank"},
            {"kind": "scan"},
            {"kind": "scan"},
            {"kind": "text_en", "lines": ["Native text only on page five"]},
        ]
    )
    return {
        "native_en.pdf": _build_pdf([{"kind": "text_en", "lines": ["Native FastAPI resume", "second line"]}]),
        "native_cn.pdf": _build_pdf([{"kind": "text_cn", "lines": ["个人简历 数据库备份恢复记录 项目经历"]}]),
        "mixed_4p.pdf": mixed,
        "scanned_3p.pdf": _build_pdf([{"kind": "scan"}, {"kind": "scan"}, {"kind": "scan"}]),
        "text_on_page5.pdf": tail_text,
        "huge_page_6000x5000pt.pdf": _build_pdf(
            [{"kind": "scan"}], pagesize=(6000.0, 5000.0)
        ),
        "small_page_1000x900pt.pdf": _build_pdf(
            [{"kind": "scan"}], pagesize=(1000.0, 900.0)
        ),
        "rotated_90_400x700pt.pdf": _build_pdf(
            [{"kind": "scan"}], pagesize=(400.0, 700.0), rotate=90
        ),
        "encrypted_userpw55.pdf": _build_pdf(
            [{"kind": "text_en", "lines": ["Encrypted native text"]}],
            encrypt=StandardEncryption("userpw55", "ownerpw55", canPrint=1, canModify=0, strength=128),
        ),
        "corrupt_garbage.bin": "this is not a pdf at all — harness55 synthetic corruption".encode("utf-8"),
        "corrupt_header_nul.bin": b"%PDF-1.7\n" + b"\x00" * 512,
        "corrupt_truncated.pdf": _build_pdf([{"kind": "text_en", "lines": ["will be truncated"]}])[:200],
        "corrupt_empty.bin": b"",
    }


def persist_fixtures(fixture_dir: Path, fixtures: dict[str, bytes]) -> dict:
    """Attempt the sanctioned write target; never fall back to another directory."""
    outcome: dict[str, Any] = {
        "directory": str(fixture_dir),
        "allowed_write_target": True,
        "created_directory": False,
        "written": [],
        "failed": [],
        "persisted": False,
        "on_failure": "fixtures stay in memory only; no synthetic PDF is written anywhere else",
    }
    try:
        fixture_dir.mkdir(parents=True, exist_ok=True)
        outcome["created_directory"] = True
    except OSError as exc:
        outcome["directory_error"] = f"{type(exc).__name__}: {exc}"
        outcome["blocked_by_environment"] = True
        return outcome
    for name, payload in fixtures.items():
        try:
            (fixture_dir / name).write_bytes(payload)
            outcome["written"].append({"name": name, "bytes": len(payload), "sha256": sha256(payload)})
        except OSError as exc:
            outcome["failed"].append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
    outcome["persisted"] = bool(outcome["written"]) and not outcome["failed"]
    if outcome["failed"]:
        outcome["blocked_by_environment"] = True
    return outcome


# --------------------------------------------------------------------------------------
# Synthetic recognizers (explicit callbacks; never a real OCR engine or model)
# --------------------------------------------------------------------------------------
class ScriptedRecognizer:
    """Deterministic OCR stand-in; records every payload and replies per call index."""

    def __init__(self, replies: list[OcrResult | BaseException]) -> None:
        self.replies = replies
        self.calls: list[bytes] = []

    def __call__(self, image: bytes) -> OcrResult:
        index = len(self.calls)
        self.calls.append(image)
        reply = self.replies[min(index, len(self.replies) - 1)]
        if isinstance(reply, BaseException):
            raise reply
        return reply


def constant_recognizer(text: str, confidence: float = 0.9, lines: int = 1) -> ScriptedRecognizer:
    return ScriptedRecognizer([OcrResult(text, confidence, lines)])


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------
def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def section_view(sections: list[DocumentSection]) -> list[dict[str, Any]]:
    """Structural view only: type/page/marked stay stable regardless of text layout."""
    return [
        {
            "type": s.section_type,
            "page": s.page_number,
            "marked": s.content.startswith(OCR_IMAGE_MARKER),
        }
        for s in sections
    ]


def png_pixel_count(png: bytes) -> int:
    """Measure the real bitmap that render() produced, via the PNG handed to the recognizer."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.size[0] * image.size[1]


def _adapter(**kwargs: Any) -> PdfiumPdfAdapter:
    kwargs.setdefault("recognizer", constant_recognizer("合成识别文本 A\n合成识别文本 B", 0.9, 2))
    return PdfiumPdfAdapter(**kwargs)


def _expect_error(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        value = fn()
    except PdfParseError as exc:
        return {"raised": True, "message": exc.message, "code": exc.code, "reason": exc.reason}
    except BaseException as exc:  # noqa: BLE001 - an unexpected type is itself a finding
        return {
            "raised": True,
            "unexpected": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().strip().splitlines()[-2:],
        }
    return {"raised": False, "value": value}


def run_checks(
    fixtures: dict[str, bytes], fixture_dir: Path, fixtures_on_disk: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Adversarial checks from first principles; every check returns a verdict, never raises."""
    checks: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}

    def record(
        cid: str,
        intent: str,
        expected: Any,
        observed_fn: Callable[[], Any],
        *,
        detail_fn: Callable[[], Any] | None = None,
    ) -> None:
        try:
            observed = observed_fn()
            verdict = "pass" if observed == expected else "fail"
            detail = detail_fn() if detail_fn else None
            checks.append(
                {
                    "id": cid,
                    "intent": intent,
                    "expected": expected,
                    "observed": observed,
                    "verdict": verdict,
                    "detail": detail,
                }
            )
        except BaseException as exc:  # noqa: BLE001 - a broken check is a failed check
            checks.append(
                {
                    "id": cid,
                    "intent": intent,
                    "expected": expected,
                    "observed": None,
                    "verdict": "fail",
                    "detail": {
                        "check_error": f"{type(exc).__name__}: {exc}",
                        "trace_tail": traceback.format_exc().strip().splitlines()[-4:],
                    },
                }
            )

    # --- C01 native English text: no render, no OCR -----------------------------------
    def c01() -> Any:
        adapter = _adapter()
        sections = adapter.parse_source(fixtures["native_en.pdf"], name="native_en.pdf")
        payloads["c01"] = {"content": sections[0].content, "ledger": adapter.ledger.snapshot()}
        return {
            "sections": section_view(sections),
            "render_calls": adapter.ledger.render_calls,
            "recognizer_calls": adapter.stats.recognizer_calls,
            "has_text": "Native FastAPI resume" in sections[0].content,
            "text_verbatim": sections[0].content,
        }

    record(
        "C01",
        "native English text is extracted without render/OCR",
        {
            "sections": [{"type": "page", "page": 1, "marked": False}],
            "render_calls": 0,
            "recognizer_calls": 0,
            "has_text": True,
            "text_verbatim": "Native FastAPI resume\r\nsecond line",
        },
        c01,
    )

    # --- C02 native Chinese text: no render, no OCR -----------------------------------
    def c02() -> Any:
        adapter = _adapter()
        sections = adapter.parse_source(fixtures["native_cn.pdf"], name="native_cn.pdf")
        payloads["c02"] = {"content": sections[0].content}
        return {
            "type": sections[0].section_type,
            "page": sections[0].page_number,
            "cjk_roundtrip": "数据库备份恢复记录" in sections[0].content,
            "ocr": adapter.stats.recognizer_calls,
            "render": adapter.ledger.render_calls,
        }

    record(
        "C02",
        "native CJK text is extracted without render/OCR (no OCR engine involved)",
        {"type": "page", "page": 1, "cjk_roundtrip": True, "ocr": 0, "render": 0},
        c02,
    )

    # --- C03 mixed 4 pages: 1-based page numbers, only blank pages OCR'd --------------
    def c03() -> Any:
        recognizer = constant_recognizer("数据库备份恢复记录", 0.88, 1)
        adapter = _adapter(recognizer=recognizer)
        sections = adapter.parse_source(fixtures["mixed_4p.pdf"], name="mixed_4p.pdf")
        payloads["c03"] = {
            "sections": section_view(sections),
            "ledger": adapter.ledger.snapshot(),
            "stats": adapter.stats.__dict__,
        }
        return {
            "sections": section_view(sections),
            "recognizer_calls": len(recognizer.calls),
            "render_calls": adapter.ledger.render_calls,
            "ocr_skipped": adapter.stats.ocr_skipped_pages,
        }

    record(
        "C03",
        "mixed native/scan PDF keeps 1-based page numbers and OCRs only the scanned pages",
        {
            "sections": [
                {"type": "page", "page": 1, "marked": False},
                {"type": "ocr_page", "page": 2, "marked": True},
                {"type": "page", "page": 3, "marked": False},
                {"type": "ocr_page", "page": 4, "marked": True},
            ],
            "recognizer_calls": 2,
            "render_calls": 2,
            "ocr_skipped": 0,
        },
        c03,
    )

    # --- C04 scanned-only 3 pages ------------------------------------------------------
    def c04() -> Any:
        adapter = _adapter()
        sections = adapter.parse_source(fixtures["scanned_3p.pdf"], name="scanned_3p.pdf")
        return {"types": [s.section_type for s in sections], "pages": [s.page_number for s in sections]}

    record(
        "C04",
        "scanned-only PDF yields one OCR section per page with 1-based numbering",
        {"types": ["ocr_page"] * 3, "pages": [1, 2, 3]},
        c04,
    )

    # --- C05 OCR call budget -----------------------------------------------------------
    def c05() -> Any:
        recognizer = constant_recognizer("扫描页识别文本", 0.8, 1)
        adapter = _adapter(recognizer=recognizer, ocr_max_pages=1)
        sections = adapter.parse_source(fixtures["scanned_3p.pdf"], name="scanned_3p.pdf")
        payloads["c05"] = {"ocr_skipped": adapter.stats.ocr_skipped_pages}
        return {
            "recognizer_calls": len(recognizer.calls),
            "pages": [s.page_number for s in sections],
            "render_calls": adapter.ledger.render_calls,
            "ocr_skipped": adapter.stats.ocr_skipped_pages,
        }

    record(
        "C05",
        "ocr_max_pages caps OCR calls and the skipped scanned pages are counted",
        {"recognizer_calls": 1, "pages": [1], "render_calls": 1, "ocr_skipped": 2},
        c05,
    )

    # --- C06 OCR disabled: native text still parses, no OCR at all ---------------------
    def c06() -> Any:
        recognizer = constant_recognizer("should never run", 0.9, 1)
        adapter = _adapter(recognizer=recognizer, ocr_enabled=False)
        sections = adapter.parse_source(fixtures["mixed_4p.pdf"], name="mixed_4p.pdf")
        return {
            "pages": [s.page_number for s in sections],
            "recognizer_calls": len(recognizer.calls),
            "render_calls": adapter.ledger.render_calls,
            "ocr_skipped": adapter.stats.ocr_skipped_pages,
        }

    record(
        "C06",
        "with OCR disabled the native pages still parse and nothing is rendered",
        {"pages": [1, 3], "recognizer_calls": 0, "render_calls": 0, "ocr_skipped": 2},
        c06,
    )

    # --- C07 pixel cap refuses a huge page before allocating a bitmap -------------------
    def c07() -> Any:
        adapter = _adapter(ocr_max_image_pixels=20_000_000)
        outcome = _expect_error(
            lambda: adapter.parse_source(fixtures["huge_page_6000x5000pt.pdf"], name="huge")
        )
        payloads["c07"] = {
            "predicted_pixels": adapter.stats.predicted_pixels,
            "ledger": adapter.ledger.snapshot(),
        }
        return {
            "error": {k: outcome.get(k) for k in ("code", "reason", "unexpected")},
            "render_calls": adapter.ledger.render_calls,
            "bitmap_opened": adapter.ledger.opened["bitmap"],
            "predicted": adapter.stats.predicted_pixels,
        }

    record(
        "C07",
        "a 6000x5000pt page is refused by the pixel budget before any bitmap allocation",
        {
            "error": {"code": CODE_LIMIT, "reason": "pdf_pixel_budget", "unexpected": None},
            "render_calls": 0,
            "bitmap_opened": 0,
            "predicted": [120_000_000],
        },
        c07,
    )

    # --- C08 pre-flight math equals the real bitmap, both reject and accept ------------
    def c08_actual() -> int:
        """Real rendered pixel count, measured from the PNG the recognizer receives."""
        seen: dict[str, int] = {}

        def measuring_recognizer(png: bytes) -> OcrResult:
            seen["actual"] = png_pixel_count(png)
            return OcrResult("小页识别", 0.9, 1)

        adapter = _adapter(recognizer=measuring_recognizer, ocr_max_image_pixels=4_000_000)
        adapter.parse_source(fixtures["small_page_1000x900pt.pdf"], name="small")
        return seen.get("actual", -1)

    def c08() -> Any:
        rejected = _adapter(ocr_max_image_pixels=3_500_000)
        reject_outcome = _expect_error(
            lambda: rejected.parse_source(fixtures["small_page_1000x900pt.pdf"], name="small")
        )
        accepted = _adapter(ocr_max_image_pixels=4_000_000)
        sections = accepted.parse_source(fixtures["small_page_1000x900pt.pdf"], name="small")
        payloads["c08"] = {
            "reject_ledger": rejected.ledger.snapshot(),
            "accept_ledger": accepted.ledger.snapshot(),
        }
        return {
            "reject": {
                "code": reject_outcome.get("code"),
                "reason": reject_outcome.get("reason"),
                "render_calls": rejected.ledger.render_calls,
                "bitmap_opened": rejected.ledger.opened["bitmap"],
                "predicted": rejected.stats.predicted_pixels,
            },
            "accept": {
                "sections": len(sections),
                "predicted": accepted.stats.predicted_pixels,
                "actual_pixels": payloads["c08_actual"],
            },
        }

    payloads["c08_actual"] = c08_actual()

    record(
        "C08",
        "pre-flight pixel math matches the real bitmap exactly (reject at 3.5M, accept at 4M)",
        {
            "reject": {
                "code": CODE_LIMIT,
                "reason": "pdf_pixel_budget",
                "render_calls": 0,
                "bitmap_opened": 0,
                "predicted": [3_600_000],
            },
            "accept": {"sections": 1, "predicted": [3_600_000], "actual_pixels": 3_600_000},
        },
        c08,
    )

    # --- C09 rotated page: geometry (and therefore the guard) accounts for rotation ----
    def c09_actual() -> int:
        seen: dict[str, int] = {}

        def measuring_recognizer(png: bytes) -> OcrResult:
            seen["actual"] = png_pixel_count(png)
            return OcrResult("旋转页识别", 0.9, 1)

        adapter = _adapter(recognizer=measuring_recognizer, ocr_max_image_pixels=1_130_000)
        adapter.parse_source(fixtures["rotated_90_400x700pt.pdf"], name="rot90")
        return seen.get("actual", -1)

    def c09() -> Any:
        rejected = _adapter(ocr_max_image_pixels=1_119_000)
        reject_outcome = _expect_error(
            lambda: rejected.parse_source(fixtures["rotated_90_400x700pt.pdf"], name="rot90")
        )
        accepted = _adapter(ocr_max_image_pixels=1_130_000)
        sections = accepted.parse_source(fixtures["rotated_90_400x700pt.pdf"], name="rot90")
        return {
            "reject": {
                "code": reject_outcome.get("code"),
                "reason": reject_outcome.get("reason"),
                "render_calls": rejected.ledger.render_calls,
                "bitmap_opened": rejected.ledger.opened["bitmap"],
                "predicted": rejected.stats.predicted_pixels,
            },
            "accept": {
                "sections": len(sections),
                "predicted": accepted.stats.predicted_pixels,
                "actual_pixels": payloads["c09_actual"],
            },
        }

    payloads["c09_actual"] = c09_actual()

    record(
        "C09",
        "a 90-degree rotated page is measured with swapped dimensions (800x1400 at scale 2)",
        {
            "reject": {
                "code": CODE_LIMIT,
                "reason": "pdf_pixel_budget",
                "render_calls": 0,
                "bitmap_opened": 0,
                "predicted": [1_120_000],
            },
            "accept": {"sections": 1, "predicted": [1_120_000], "actual_pixels": 1_120_000},
        },
        c09,
    )

    # --- C10 corrupt inputs are classified, not leaked ---------------------------------
    def c10() -> Any:
        results = {}
        for name in (
            "corrupt_garbage.bin",
            "corrupt_header_nul.bin",
            "corrupt_truncated.pdf",
            "corrupt_empty.bin",
        ):
            adapter = _adapter()
            outcome = _expect_error(lambda name=name: adapter.parse_source(fixtures[name], name=name))
            results[name] = {
                "code": outcome.get("code"),
                "reason": outcome.get("reason"),
                "unexpected": outcome.get("unexpected"),
                "doc_balanced": adapter.ledger.opened["document"] == adapter.ledger.closed["document"],
            }
        return results

    record(
        "C10",
        "corrupt/truncated/empty input raises an explicit classified ParseError and leaks no document",
        {
            name: {"code": CODE_NO_TEXT, "reason": "pdf_corrupt", "unexpected": None, "doc_balanced": True}
            for name in (
                "corrupt_garbage.bin",
                "corrupt_header_nul.bin",
                "corrupt_truncated.pdf",
                "corrupt_empty.bin",
            )
        },
        c10,
    )

    # --- C11 missing path is a distinct, explicit failure ------------------------------
    def c11() -> Any:
        adapter = _adapter()
        outcome = _expect_error(lambda: adapter.parse(REPO_ROOT / "backend" / ".tmp" / "missing-55.pdf"))
        return {
            "code": outcome.get("code"),
            "reason": outcome.get("reason"),
            "doc_opened": adapter.ledger.opened["document"],
        }

    record(
        "C11",
        "a missing file is reported as pdf_missing and never reaches PDFium",
        {"code": CODE_NO_TEXT, "reason": "pdf_missing", "doc_opened": 0},
        c11,
    )

    # --- C12 encrypted PDF: classified, and openable with the right password -----------
    def c12() -> Any:
        no_password = _adapter()
        sealed = _expect_error(
            lambda: no_password.parse_source(fixtures["encrypted_userpw55.pdf"], name="enc")
        )
        wrong = _adapter(password="nope55")
        wrong_outcome = _expect_error(
            lambda: wrong.parse_source(fixtures["encrypted_userpw55.pdf"], name="enc")
        )
        right = _adapter(password="userpw55")
        sections = right.parse_source(fixtures["encrypted_userpw55.pdf"], name="enc")
        return {
            "no_password": {"code": sealed.get("code"), "reason": sealed.get("reason")},
            "wrong_password": {"reason": wrong_outcome.get("reason")},
            "right_password": {
                "sections": len(sections),
                "type": sections[0].section_type,
                "page": sections[0].page_number,
                "ocr": right.stats.recognizer_calls,
                "text": "Encrypted native text" in sections[0].content,
            },
            "distinct_from_corrupt": sealed.get("reason") != "pdf_corrupt",
        }

    record(
        "C12",
        "encryption is classified separately from corruption and works with the right password",
        {
            "no_password": {"code": CODE_NO_TEXT, "reason": "pdf_encrypted"},
            "wrong_password": {"reason": "pdf_encrypted"},
            "right_password": {"sections": 1, "type": "page", "page": 1, "ocr": 0, "text": True},
            "distinct_from_corrupt": True,
        },
        c12,
    )

    # --- C13 resource ledger balanced on the success path ------------------------------
    def c13() -> Any:
        adapter = _adapter()
        adapter.parse_source(fixtures["mixed_4p.pdf"], name="mixed")
        return adapter.ledger.snapshot()

    expected_ledger = {
        "opened": {"document": 1, "page": 4, "textpage": 4, "bitmap": 2},
        "closed": {"document": 1, "page": 4, "textpage": 4, "bitmap": 2},
        "render_calls": 2,
        "text_calls": 4,
        "balanced": True,
    }
    record(
        "C13",
        "every document/page/textpage/bitmap opened by a mixed parse is closed",
        expected_ledger,
        c13,
    )

    # --- C14 failure inside the recognizer still closes everything ---------------------
    def c14() -> Any:
        recognizer = ScriptedRecognizer(
            [OcrResult("ok", 0.9, 1), RuntimeError("synthetic recognizer explosion")]
        )
        adapter = _adapter(recognizer=recognizer)
        outcome = _expect_error(
            lambda: adapter.parse_source(fixtures["scanned_3p.pdf"], name="scanned_3p.pdf")
        )
        return {
            "code": outcome.get("code"),
            "reason": outcome.get("reason"),
            "ledger": adapter.ledger.snapshot(),
            "recognizer_calls": len(recognizer.calls),
            "render_calls": adapter.ledger.render_calls,
        }

    record(
        "C14",
        "a recognizer failure aborts the parse, closes all PDFium objects and stops early",
        {
            "code": CODE_OCR_UNAVAILABLE,
            "reason": "ocr_failed",
            "ledger": {
                "opened": {"document": 1, "page": 2, "textpage": 2, "bitmap": 2},
                "closed": {"document": 1, "page": 2, "textpage": 2, "bitmap": 2},
                "render_calls": 2,
                "text_calls": 2,
                "balanced": True,
            },
            "recognizer_calls": 2,
            "render_calls": 2,
        },
        c14,
    )

    # --- C15 thread affinity guard: process isolation only, no parsing threads ---------
    def c15() -> Any:
        adapter = _adapter()
        adapter.parse_source(fixtures["native_en.pdf"], name="native_en.pdf")
        before_threads = threading.active_count()
        outcome: dict[str, Any] = {}
        ledger_before = adapter.ledger.snapshot()

        def other_thread() -> None:
            outcome.update(
                _expect_error(lambda: adapter.parse_source(fixtures["native_en.pdf"], name="thread2"))
            )

        worker = threading.Thread(target=other_thread, name="harness55-illegal-thread")
        worker.start()
        worker.join()
        return {
            "reason": outcome.get("reason"),
            "unexpected": outcome.get("unexpected"),
            "render_calls_before": ledger_before["render_calls"],
            "render_calls_after": adapter.ledger.render_calls,
            "documents_opened": adapter.ledger.opened["document"],
            "threads_before": before_threads,
            "threads_after": threading.active_count(),
        }

    record(
        "C15",
        "using the adapter from a second thread is refused before PDFium is touched",
        {
            "reason": "pdf_thread_affinity",
            "unexpected": None,
            "render_calls_before": 0,
            "render_calls_after": 0,
            "documents_opened": 1,
            "threads_before": 1,
            "threads_after": 1,
        },
        c15,
    )

    # --- C16 the OCR callback receives a real, non-blank PNG ---------------------------
    def c16() -> Any:
        from PIL import Image

        recognizer = constant_recognizer("扫描页", 0.75, 1)
        adapter = _adapter(recognizer=recognizer)
        adapter.parse_source(fixtures["scanned_3p.pdf"], name="scanned_3p.pdf")
        payload = recognizer.calls[0]
        with Image.open(io.BytesIO(payload)) as image:
            size = image.size
            extrema = image.convert("L").getextrema()
        return {
            "calls": len(recognizer.calls),
            "png_signature": payload[:8] == b"\x89PNG\r\n\x1a\n",
            "size": list(size),
            "non_blank": extrema[0] < 250,
            "expected_size": [
                math.ceil(595.276 * 2),
                math.ceil(841.89 * 2),
            ],
        }

    record(
        "C16",
        "the injected recognizer gets real rendered PNG bytes (not a stub, not a real engine)",
        {
            "calls": 3,
            "png_signature": True,
            "size": [1191, 1684],
            "non_blank": True,
            "expected_size": [1191, 1684],
        },
        c16,
    )

    # --- C17 no OCR/model/framework is imported; bytes and BytesIO agree ----------------
    def c17() -> Any:
        forbidden = [
            name
            for name in ("rapidocr", "onnxruntime", "torch", "paddle", "paddleocr", "tensorflow")
            if name in sys.modules
        ]
        by_buffer = _adapter().parse_source(fixtures["mixed_4p.pdf"], name="mixed_4p.pdf")
        by_stream = _adapter().parse_source(io.BytesIO(fixtures["mixed_4p.pdf"]), name="mixed_4p.pdf")
        return {
            "forbidden_modules": forbidden,
            "bytes_matches_bytesio": section_view(by_buffer) == section_view(by_stream),
            "sections": section_view(by_buffer),
        }

    record(
        "C17",
        "no OCR/model package is imported and bytes/BytesIO input behave identically",
        {
            "forbidden_modules": [],
            "bytes_matches_bytesio": True,
            "sections": [
                {"type": "page", "page": 1, "marked": False},
                {"type": "ocr_page", "page": 2, "marked": True},
                {"type": "page", "page": 3, "marked": False},
                {"type": "ocr_page", "page": 4, "marked": True},
            ],
        },
        c17,
    )

    # --- C18 1-based page numbering survives when native text starts at page 5 ---------
    def c18() -> Any:
        adapter = _adapter(ocr_max_pages=0)
        sections = adapter.parse_source(fixtures["text_on_page5.pdf"], name="text_on_page5.pdf")
        return {
            "sections": section_view(sections),
            "ocr_skipped": adapter.stats.ocr_skipped_pages,
            "render_calls": adapter.ledger.render_calls,
        }

    record(
        "C18",
        "native text on page 5 keeps page_number 5 while earlier blank pages are skipped",
        {
            "sections": [{"type": "page", "page": 5, "marked": False}],
            "ocr_skipped": 4,
            "render_calls": 0,
        },
        c18,
    )

    # --- C19 path input vs buffer input (only when the fixture directory is writable) --
    if fixtures_on_disk:
        def c19() -> Any:
            on_disk = fixture_dir / "mixed_4p.pdf"
            by_path = _adapter().parse(on_disk)
            by_buffer = _adapter().parse_source(fixtures["mixed_4p.pdf"], name="mixed_4p.pdf")
            return {
                "path_exists": on_disk.exists(),
                "matches_buffer": section_view(by_path) == section_view(by_buffer),
            }

        record(
            "C19",
            "a successful path-based parse equals the buffer parse",
            {"path_exists": True, "matches_buffer": True},
            c19,
        )
    else:
        checks.append(
            {
                "id": "C19",
                "intent": "a successful path-based parse equals the buffer parse",
                "expected": {"path_exists": True, "matches_buffer": True},
                "observed": None,
                "verdict": "skipped",
                "detail": {
                    "reason": "sanctioned fixture directory is not writable by this process, "
                    "so no fixture can exist on disk; buffer input is exercised instead",
                },
            }
        )

    return checks, payloads


# --------------------------------------------------------------------------------------
# Runner / reporting
# --------------------------------------------------------------------------------------
def canonical_json(payload: Any) -> str:
    """Single-line canonical form: the exact bytes that are hashed and shipped."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


CHUNK_SIZE = 1000


def chunk_hashes(text: str) -> list[str]:
    return [
        hashlib.sha256(text[index:index + CHUNK_SIZE].encode("utf-8")).hexdigest()
        for index in range(0, len(text), CHUNK_SIZE)
    ]


def run(fixture_dir: Path, persist: bool) -> tuple[str, dict[str, Any]]:
    log: list[str] = []

    def emit(line: str = "") -> None:
        log.append(line)

    import pypdfium2 as pdfium

    threads_before = threading.active_count()
    fixtures = build_fixtures()
    persist_outcome = (
        persist_fixtures(fixture_dir, fixtures)
        if persist
        else {"directory": str(fixture_dir), "persisted": False, "skipped": True}
    )
    checks, raw_evidence = run_checks(fixtures, fixture_dir, bool(persist_outcome.get("persisted")))
    threads_after = threading.active_count()

    passed = sum(1 for c in checks if c["verdict"] == "pass")
    failed = [c["id"] for c in checks if c["verdict"] == "fail"]
    skipped = [c["id"] for c in checks if c["verdict"] == "skipped"]

    emit("harness55 传智杯55 PDFium 隔离替换原型 — 独立适配器 + 合成对抗测试")
    emit(f"repo_root={REPO_ROOT}")
    emit(f"python={sys.version.split()[0]} pypdfium2={pdfium.PYPDFIUM_INFO} pdfium={pdfium.PDFIUM_INFO}")
    emit(f"fixture_dir={fixture_dir} persist_attempted={persist} persisted={persist_outcome.get('persisted')}")
    if persist_outcome.get("directory_error"):
        emit(f"fixture_dir_error={persist_outcome['directory_error']}")
    for name, payload in sorted(fixtures.items()):
        emit(f"[FIXTURE] {name} bytes={len(payload)} sha256={sha256(payload)}")
    emit("")
    for check in checks:
        emit(f"[CHECK] {check['id']} verdict={check['verdict']} :: {check['intent']}")
        emit(f"        expected={canonical_json(check['expected'])}")
        emit(f"        observed={canonical_json(check['observed'])}")
    emit("")
    emit(f"[SUMMARY] total={len(checks)} passed={passed} failed={len(failed)} failed_ids={failed}")
    emit(f"[SKIPPED] {skipped}")
    emit(f"[THREADS] before={threads_before} after={threads_after} created={threads_after - threads_before}")
    emit(f"[THREADS_NAMES] {sorted(t.name for t in threading.enumerate())}")

    results: dict[str, Any] = {
        "schema": "harness55-pdfium55-prototype/1",
        "task": "传智杯55 PDFium隔离替换原型（仅调查/原型，不改生产）",
        "runtime": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "platform": sys.platform,
            "pypdfium2": str(pdfium.PYPDFIUM_INFO),
            "pdfium": str(pdfium.PDFIUM_INFO),
            "reportlab": _pkg_version("reportlab"),
            "pillow": _pkg_version("pillow"),
            "pypdf": _pkg_version("pypdf"),
            "rapidocr": _pkg_version("rapidocr"),
        },
        "design_rules": [
            "native text pages are never rendered or OCR'd",
            "page_number is always index+1 (1-based) for native, scanned and mixed documents",
            "OCR calls are capped by ocr_max_pages; skipped scanned pages are counted, not silently lost",
            "pixel budget is evaluated from page.get_size() before page.render() allocates a bitmap",
            "corrupt (FPDF_ERR_FORMAT/FILE) and encrypted (FPDF_ERR_PASSWORD) input raise classified errors",
            "PdfDocument/PdfPage/PdfTextPage/PdfBitmap are closed in finally blocks on every path",
            "OCR is an injected callback; no real OCR engine, no model, no network",
            "PDFium is not thread-safe: process isolation only, zero parsing threads, second thread refused",
        ],
        "fixtures": {
            "persistence": persist_outcome,
            "items": [
                {"name": name, "bytes": len(payload), "sha256": sha256(payload)}
                for name, payload in sorted(fixtures.items())
            ],
        },
        "checks": checks,
        "raw_evidence": raw_evidence,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": len(failed),
            "failed_ids": failed,
            "skipped_ids": skipped,
            "verdict": "pass" if not failed else "fail",
        },
        "threads": {
            "before": threads_before,
            "after": threads_after,
            "created": threads_after - threads_before,
            "note": "the prototype creates no thread; run_isolated() process isolation is unchanged",
        },
        "unverified": [
            "real RapidOCR engine integration and confidence filtering (app/tools/ocr.py untouched, engine absent here)",
            "extraction fidelity against real uploaded PDFs (storage/client data deliberately not read)",
            "app.services.task_runner.run_isolated process isolation, 90s timeout and worker crash behaviour",
            "A/B text-extraction equality with PyMuPDF (order, \\r\\n vs \\n, column layout, ligatures, tables)",
            "the 500k max_document_characters budget interaction and downstream AI prompt impact",
            "native crash / CVE robustness comparison against PyMuPDF (no vulnerability or fuzz evidence gathered)",
            "behaviour on other pypdfium2/PDFium versions and platforms (only bundled CPython 3.12 on Windows here)",
            "license/legal compliance of shipping PDFium (see license_observation; not a legal conclusion)",
        ],
        "integration_gaps": [
            "the prototype runs in-process; production parsing runs in a separate process via run_isolated(), so the thread guard here is a stand-in, not a substitute",
            "production has no password input path for encrypted PDFs; the adapter supports password= but the API/upload flow does not",
            "PyMuPDF currently stays installed for DOCX-adjacent tests and other call sites; removing it is a separate, unmeasured packaging change",
            "pypdfium2 ships a native binary per platform; wheel availability, CI images and the deployment matrix were not evaluated",
            "recognize_image() expects the same PNG bytes, but RapidOCR was never invoked, so end-to-end OCR quality is unproven",
            "the app currently checks the pixel cap after page.get_pixmap(); the prototype moves the check earlier, which changes when the 4026 error is raised but not its code/message contract",
        ],
        "license_observation": {
            "source": "local wheel metadata only (no network in this task)",
            "metadata_License": "BSD-3-Clause, Apache-2.0, dependency licenses",
            "license_files_in_wheel": [
                "pypdfium2-5.14.0.dist-info/licenses/LICENSES/Apache-2.0.txt",
                "pypdfium2-5.14.0.dist-info/licenses/LICENSES/BSD-3-Clause.txt",
                "pypdfium2-5.14.0.dist-info/licenses/LICENSES/CC-BY-4.0.txt",
                "pypdfium2-5.14.0.dist-info/licenses/data/windows_x64/BUILD_LICENSES/pdfium.txt",
                "pypdfium2-5.14.0.dist-info/licenses/data/windows_x64/BUILD_LICENSES/{freetype,icu,libjpeg_turbo,libpng,libopenjpeg,zlib,abseil,agg23,fast_float,lcms,llvm-libc,simdutf,pdfium-binaries}.txt",
            ],
            "conclusion": "wrapper is Apache-2.0/BSD-3-Clause per Codex's check; PDFium and its transitive licenses must still be retained and shipped. Replacement is NOT legal compliance by itself, and this task does not give legal advice.",
        },
    }
    return "".join(line + "\n" for line in log), results


def _pkg_version(name: str) -> str | None:
    try:
        import importlib.metadata as md

        return md.version(name)
    except Exception:  # noqa: BLE001
        return None


def emit_run(fixture_dir: Path, persist: bool, print_json_only: bool = False) -> int:
    log_text, results = run(fixture_dir, persist)
    json_text = canonical_json(results)
    log_hash = hashlib.sha256(log_text.encode("utf-8")).hexdigest()
    json_hash = hashlib.sha256(json_text.encode("utf-8")).hexdigest()
    if print_json_only:
        sys.stdout.write(json_text + "\n")
    else:
        sys.stdout.write(log_text)
        sys.stdout.write(f"{LOG_MARKER_PREFIX}LOG SHA256: {log_hash} =====\n")
        sys.stdout.write(f"{LOG_MARKER_PREFIX}JSON SHA256: {json_hash} =====\n")
        sys.stdout.write(f"{LOG_MARKER_PREFIX}LOG CHUNKS: {len(chunk_hashes(log_text))} =====\n")
        for index, digest in enumerate(chunk_hashes(log_text)):
            sys.stdout.write(f"logchunk_{index:03d}={digest}\n")
        sys.stdout.write(f"{LOG_MARKER_PREFIX}JSON CHUNKS: {len(chunk_hashes(json_text))} =====\n")
        for index, digest in enumerate(chunk_hashes(json_text)):
            sys.stdout.write(f"chunk_{index:03d}={digest}\n")
    return 0 if results["summary"]["verdict"] == "pass" else 1


def parse_log(text: str) -> tuple[str, dict[str, Any]]:
    """Split a run log into (log_text, declared hashes) without trusting either."""
    log_marker = f"{LOG_MARKER_PREFIX}LOG SHA256: "
    if log_marker not in text:
        raise ValueError("LOG SHA256 declaration missing")
    log_text, _, tail = text.partition(log_marker)
    lines = [line for line in tail.splitlines() if line.strip()]
    declared: dict[str, Any] = {"log": lines[0].replace(" =====", "").strip(), "json": None,
                                "log_chunks": [], "json_chunks": []}
    section = None
    for line in lines[1:]:
        if "JSON SHA256: " in line:
            declared["json"] = line.split("JSON SHA256: ", 1)[1].replace(" =====", "").strip()
            section = None
        elif line.startswith(f"{LOG_MARKER_PREFIX}LOG CHUNKS:"):
            section = "log"
        elif line.startswith(f"{LOG_MARKER_PREFIX}JSON CHUNKS:"):
            section = "json"
        elif line.startswith("logchunk_") and section == "log":
            declared["log_chunks"].append(line.split("=", 1)[1].strip())
        elif line.startswith("chunk_") and section == "json":
            declared["json_chunks"].append(line.split("=", 1)[1].strip())
    return log_text, declared


def verify_log(path: Path, results_path: Path | None = None) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        log_text, declared = parse_log(text)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 2
    ok = hashlib.sha256(log_text.encode("utf-8")).hexdigest() == declared["log"]
    log_chunk_mismatches = [
        index
        for index, (declared_hash, actual) in enumerate(
            zip(declared["log_chunks"], chunk_hashes(log_text))
        )
        if declared_hash != actual
    ]
    print(f"log_sha256_declared={declared['log']}")
    print(f"log_sha256_recomputed={hashlib.sha256(log_text.encode('utf-8')).hexdigest()}")
    print(f"log_bytes={len(log_text.encode('utf-8'))} log_chunks={len(declared['log_chunks'])}")
    print(f"log_chunk_mismatches={log_chunk_mismatches}")
    print(f"json_sha256_declared={declared['json']}")
    if results_path is not None:
        raw_text = results_path.read_text(encoding="utf-8").rstrip("\n")
        payload = json.loads(raw_text)
        canonical = canonical_json(payload)
        mismatches = [
            index
            for index, (declared_hash, actual) in enumerate(
                zip(declared["json_chunks"], chunk_hashes(canonical))
            )
            if declared_hash != actual
        ]
        print(f"json_sha256_recomputed={hashlib.sha256(canonical.encode('utf-8')).hexdigest()}")
        print(f"raw_text_equals_canonical={raw_text == canonical}")
        print(f"json_chunk_mismatches={mismatches}")
        print(f"results_summary={canonical_json(payload.get('summary'))}")
        ok = ok and not log_chunk_mismatches and canonical == raw_text
        ok = ok and hashlib.sha256(canonical.encode("utf-8")).hexdigest() == declared["json"]
        ok = ok and not mismatches
    print(f"VERDICT={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def verify_results(path: Path, expected_sha256: str) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    recomputed = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    ok = recomputed == expected_sha256.strip().lower()
    print(f"expected={expected_sha256.strip().lower()}")
    print(f"recomputed={recomputed}")
    print(f"summary={canonical_json(payload.get('summary'))}")
    print(f"VERDICT={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="harness55 PDFium adapter prototype")
    parser.add_argument("--fixture-dir", default=str(DEFAULT_FIXTURE_DIR))
    parser.add_argument("--no-persist-fixtures", action="store_true")
    parser.add_argument("--print-json", action="store_true", help="print only the canonical results JSON")
    parser.add_argument(
        "--dump-json-wrapped",
        action="store_true",
        help="print the canonical JSON sliced every 1000 chars (newline-free slices, for reading/transcription)",
    )
    parser.add_argument("--verify-log")
    parser.add_argument("--verify-results")
    parser.add_argument("--results", help="results.json to cross-check while verifying a log")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)

    if args.verify_log:
        return verify_log(
            Path(args.verify_log), Path(args.results) if args.results else None
        )
    if args.verify_results:
        if not args.expected_sha256:
            parser.error("--verify-results requires --expected-sha256")
        return verify_results(Path(args.verify_results), args.expected_sha256)
    if args.dump_json_wrapped:
        _, results = run(Path(args.fixture_dir), not args.no_persist_fixtures)
        text = canonical_json(results)
        for index in range(0, len(text), CHUNK_SIZE):
            sys.stdout.write(text[index:index + CHUNK_SIZE] + "\n")
        return 0
    return emit_run(Path(args.fixture_dir), not args.no_persist_fixtures, args.print_json)


if __name__ == "__main__":
    raise SystemExit(main())
