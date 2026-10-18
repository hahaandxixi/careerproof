"""Unreadable-input boundaries for the document parser.

These pin down which failures are *input rejections* and which must keep propagating.
Before the narrow conversion in ``document_parser``, a corrupt, empty, renamed or
password-protected file escaped as a library exception, so the caller could not tell
"this file is unreadable" from a defect in our own code.

Deliberately not covered here (already asserted elsewhere or out of scope):
  * rotation / pixel-budget rejection before bitmap allocation -> test_document_ocr.py
  * isolated-worker process failure and timeout -> task_runner tests (process protocol)
"""

from __future__ import annotations

import fitz
import pytest

from app.core.exceptions import AppError
from app.tools.document_parser import parse_document

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# open/close counters for documents the parser touches during one test
_close_calls: dict[str, int] = {"n": 0}
_open_calls: dict[str, int] = {"n": 0}


@pytest.fixture(autouse=True)
def track_document_close(monkeypatch):
    """Count explicit ``Document.close`` calls while the test runs.

    A ``path.unlink()`` after the failure is not a sufficient check: CPython's
    reference counting closes the handle when the function returns, so a leaked
    document still looks releasable. Counting close() calls is deterministic and
    covers both the context-manager and the explicit-close paths.
    """
    _close_calls["n"] = 0
    _open_calls["n"] = 0
    import app.tools.document_parser as parser_module

    real_open = parser_module.fitz.open

    def counting_open(*args, **kwargs):
        _open_calls["n"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(parser_module.fitz, "open", counting_open)
    real_close = fitz.Document.close

    def counting_close(self):
        _close_calls["n"] += 1
        return real_close(self)

    monkeypatch.setattr(fitz.Document, "close", counting_close)
    yield _close_calls
    _close_calls["n"] = 0


def _encrypted_pdf(path):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), "confidential body")
        document.save(
            path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    return path


def _corrupt_pdf(path):
    path.write_bytes(b"%PDF-1.7\n" + b"\x00\xff" * 2048 + b"\n%%EOF\n")
    return path


def _renamed_text(path):
    path.write_bytes(b"this is plainly not a pdf\n" * 10)
    return path


def _zero_byte(path):
    path.write_bytes(b"")
    return path


def _corrupt_docx(path):
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 256)
    return path


# ---------------------------------------------------------------------------
# Expected input rejections: each must surface as a user-readable AppError(4024).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "builder", [_corrupt_pdf, _renamed_text, _zero_byte], ids=["corrupt", "renamed", "empty"]
)
def test_unreadable_pdf_is_rejected_as_a_user_error(tmp_path, builder):
    path = builder(tmp_path / "broken.pdf")
    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")
    assert error.value.code == 4024
    assert "PDF" in str(error.value)


def test_password_protected_pdf_is_rejected_as_a_user_error(tmp_path):
    path = _encrypted_pdf(tmp_path / "locked.pdf")
    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")
    assert error.value.code == 4024
    # The message must tell the user the file may need a password, not blame corruption only.
    assert "密码" in str(error.value)


def test_corrupt_docx_is_rejected_as_a_user_error(tmp_path):
    path = _corrupt_docx(tmp_path / "broken.docx")
    with pytest.raises(AppError) as error:
        parse_document(path, DOCX_MIME)
    assert error.value.code == 4024


def test_existing_no_text_rejection_keeps_its_own_message(tmp_path):
    """A readable PDF without text must not be relabelled as 'corrupt'."""
    path = tmp_path / "no-text.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path)
    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")
    assert error.value.code == 4024
    assert "未提取或识别到可分析文字" in str(error.value)


def test_pixel_budget_rejection_still_reports_its_own_code(tmp_path, monkeypatch):
    """The 4026 pixel guard must survive the new conversion instead of becoming 4024."""
    from app.core.config import settings

    path = tmp_path / "huge-page.pdf"
    with fitz.open() as document:
        page = document.new_page(width=600, height=600)
        page.set_rotation(0)
        document.save(path)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_max_image_pixels", 1_000_000)

    def forbidden(*_args, **_kwargs):
        pytest.fail("over-budget page must be rejected before allocating a bitmap")

    monkeypatch.setattr(fitz.Page, "get_pixmap", forbidden)
    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")
    assert error.value.code == 4026


# ---------------------------------------------------------------------------
# Must keep propagating: a programming error or a missing module is not an unreadable
# file, and must never be hidden behind AppError.
# ---------------------------------------------------------------------------
def test_programming_error_is_not_converted_to_an_input_rejection(tmp_path, monkeypatch):
    def boom(_root):
        raise RuntimeError("internal defect, not an input problem")

    monkeypatch.setattr("app.tools.document_parser._docx_text", boom)
    path = tmp_path / "valid.docx"
    with fitz.open() as document:  # any payload; _docx_text is replaced before it is used
        document.new_page()
        document.save(tmp_path / "scratch.pdf")
    # Build a minimal real .docx so Document() succeeds and _docx_text is reached.
    import docx

    document = docx.Document()
    document.add_paragraph("real content")
    document.save(path)

    with pytest.raises(RuntimeError, match="internal defect"):
        parse_document(path, DOCX_MIME)


def test_missing_ocr_dependency_still_propagates(tmp_path, monkeypatch):
    """An uninstalled OCR stack must not be reported as a corrupt upload."""

    def missing_engine(_png):
        raise ModuleNotFoundError("No module named 'rapidocr'")

    monkeypatch.setattr("app.tools.document_parser.recognize_image", missing_engine)
    path = tmp_path / "scanned.pdf"
    with fitz.open() as document:
        page = document.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
        pix.clear_with(255)
        page.insert_image(fitz.Rect(10, 10, 200, 200), pixmap=pix)
        document.save(path)

    with pytest.raises(ModuleNotFoundError):
        parse_document(path, "application/pdf")


def test_memory_exhaustion_is_not_reported_as_a_corrupt_file(tmp_path, monkeypatch):
    """MemoryError must reach the caller, not be relabelled as an unreadable upload."""
    import app.tools.document_parser as parser_module

    original_open = parser_module.fitz.open

    def exploding_open(*args, **kwargs):
        raise MemoryError("cannot allocate bitmap")

    monkeypatch.setattr(parser_module.fitz, "open", exploding_open)
    path = tmp_path / "any.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n")
    try:
        with pytest.raises(MemoryError):
            parse_document(path, "application/pdf")
    finally:
        monkeypatch.setattr(parser_module.fitz, "open", original_open)


def test_converted_error_keeps_the_original_cause_for_diagnostics(tmp_path):
    """The user sees a fixed message; the library error stays reachable via __cause__."""
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"\x00\xff" * 512 + b"\n%%EOF\n")
    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")

    assert error.value.__cause__ is not None, "original library error must be preserved"
    assert not isinstance(error.value.__cause__, AppError)
    # The user-facing message must not disclose the server path or the raw library text.
    message = str(error.value)
    assert str(path) not in message
    assert str(tmp_path) not in message
    assert type(error.value.__cause__).__name__ not in message


@pytest.mark.parametrize(
    "case,opens_document",
    [("encrypted", True), ("corrupt", False), ("docx-corrupt", False)],
    ids=["encrypted", "corrupt", "docx"],
)
def test_document_handle_is_released_after_a_failed_parse(tmp_path, case, opens_document):
    """A rejected document must not keep a handle open.

    Two distinct failure shapes, both must leave nothing dangling:
      * the document opens but the failure comes later (encrypted PDF): the handle was
        opened, so it must be closed exactly as many times as it was opened;
      * the file never opens at all (corrupt PDF/DOCX): there is no handle to close,
        and the parser must not invent one.
    """
    if case == "encrypted":
        path = _encrypted_pdf(tmp_path / "locked.pdf")
        mime = "application/pdf"
    elif case == "corrupt":
        path = _corrupt_pdf(tmp_path / "broken.pdf")
        mime = "application/pdf"
    else:
        path = _corrupt_docx(tmp_path / "broken.docx")
        mime = DOCX_MIME

    with pytest.raises(AppError):
        parse_document(path, mime)

    if opens_document:
        # The parser opened exactly one document; it must have closed it exactly once.
        # Limitation, stated so this test is not over-read: PyMuPDF also closes on
        # garbage collection, so an equality check here cannot distinguish an explicit
        # ``with``-driven close from a finaliser-driven one. It does catch a parser that
        # opens a document and never releases it in any way.
        assert _close_calls["n"] == _open_calls["n"] >= 1, (
            f"opened {_open_calls['n']} document(s) but closed {_close_calls['n']}"
        )
        # The file must also be deletable now.
        path.unlink()
        assert not path.exists()
    else:
        assert _close_calls["n"] == 0, (
            "no document could be opened, so nothing should have been closed"
        )


def test_document_handle_is_released_when_ocr_raises_after_opening(tmp_path, monkeypatch):
    """A failure raised mid-iteration must still close the document."""

    def failing_recognizer(_png):
        raise RuntimeError("ocr exploded")

    monkeypatch.setattr("app.tools.document_parser.recognize_image", failing_recognizer)
    path = tmp_path / "scanned.pdf"
    with fitz.open() as document:
        page = document.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
        pix.clear_with(255)
        page.insert_image(fitz.Rect(10, 10, 200, 200), pixmap=pix)
        document.save(path)

    with pytest.raises(RuntimeError, match="ocr exploded"):
        parse_document(path, "application/pdf")

    assert _close_calls["n"] >= 1, (
        "an exception during page iteration escaped without closing the document"
    )


# ---------------------------------------------------------------------------
# Internal failures must not be reclassified as an unreadable upload.
# Only opening the file is an input problem; reading and OCR are our own code.
# ---------------------------------------------------------------------------
class _FakeBounds:
    width = 10
    height = 10


class _FakeRect:
    def __mul__(self, _other):
        return self

    @property
    def irect(self):
        return _FakeBounds()


class _FakePixmap:
    width = 10
    height = 10

    def tobytes(self, _fmt: str) -> bytes:
        return b"\x89PNG\r\n\x1a\n fake"


class _FakePage:
    def __init__(self, *, raises: bool = False):
        self.rect = _FakeRect()
        self._raises = raises

    def get_text(self, _kind: str) -> str:
        if self._raises:
            raise ValueError("internal read defect")
        return ""

    def get_pixmap(self, **_kwargs):
        return _FakePixmap()


class _FakePdfDocument:
    """Only the attribute/context surface ``parse_document`` actually uses."""

    needs_pass = 0

    def __init__(self, *, raises_on_page: bool = False):
        self._raises = raises_on_page

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        yield _FakePage(raises=self._raises)


def test_internal_value_error_from_page_read_propagates(tmp_path, monkeypatch):
    """A ValueError from our own page read is a defect, not a corrupt upload."""
    import app.tools.document_parser as parser_module

    monkeypatch.setattr(
        parser_module.fitz, "open", lambda *a, **k: _FakePdfDocument(raises_on_page=True)
    )
    path = tmp_path / "any.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n")

    with pytest.raises(ValueError, match="internal read defect"):
        parse_document(path, "application/pdf")


def test_value_error_from_ocr_propagates(tmp_path, monkeypatch):
    """An OCR failure is not evidence that the uploaded file is corrupt."""

    def failing_recognizer(_png):
        raise ValueError("ocr decode defect")

    monkeypatch.setattr("app.tools.document_parser.recognize_image", failing_recognizer)
    import app.tools.document_parser as parser_module

    monkeypatch.setattr(parser_module.fitz, "open", lambda *a, **k: _FakePdfDocument())
    path = tmp_path / "scanned.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n")

    with pytest.raises(ValueError, match="ocr decode defect"):
        parse_document(path, "application/pdf")


@pytest.mark.parametrize(
    "exc", [ValueError("internal docx walk defect"), KeyError("internal docx key defect")]
)
def test_internal_docx_walk_error_propagates(tmp_path, monkeypatch, exc):
    """Our own OOXML traversal keeps its exceptions; only opening the package is input."""
    import app.tools.document_parser as parser_module

    def failing_text(_root):
        raise exc

    monkeypatch.setattr(parser_module, "_docx_text", failing_text)
    import docx

    path = tmp_path / "real.docx"
    document = docx.Document()
    document.add_paragraph("real content")
    document.save(path)

    with pytest.raises(type(exc)):
        parse_document(path, DOCX_MIME)


def test_password_protected_pdf_is_detected_without_an_exception(tmp_path, monkeypatch):
    """Encryption is an explicit check on the document, not a caught ValueError."""
    import app.tools.document_parser as parser_module

    class _Encrypted(_FakePdfDocument):
        needs_pass = 1

    monkeypatch.setattr(parser_module.fitz, "open", lambda *a, **k: _Encrypted())
    path = tmp_path / "locked.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n")

    with pytest.raises(AppError) as error:
        parse_document(path, "application/pdf")
    assert error.value.code == 4024
    assert "密码" in str(error.value)
