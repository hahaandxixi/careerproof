"""Deterministic resource-release assertions for the production PDF parser.

The previous attempt counted ``Document.close`` calls, which cannot distinguish an
explicit ``with``-driven exit from a garbage-collection finaliser: PyMuPDF also closes on
finalisation, so a leaked document still produced a ``close`` call. This module removes
that ambiguity by substituting the object ``parse_document`` obtains from ``fitz.open``
with a fake that:

  * defines ``__enter__`` / ``__exit__`` / ``close`` and records their order;
  * defines **no** ``__del__``, so nothing depends on the interpreter finalising it;
  * touches no real file, so nothing can be closed "for free" by the OS;
  * is kept alive by a strong reference until the assertions finish.

``parse_document`` is used unmodified. The regression proof lives in
``probe_release_test_double.py``: it runs this same file against a temporary copy of the
parser whose context management is removed, and expects a failure.
"""

from __future__ import annotations

import pytest

import app.tools.document_parser as parser_module
from app.tools.document_parser import DocumentSection, parse_document


class _Bounds:
    width = 10
    height = 10


class _FakeRect:
    def __mul__(self, _other):
        return self

    @property
    def irect(self):
        return _Bounds()


class FakePage:
    """Minimal page object carrying deterministic text."""

    def __init__(self, text: str | None):
        self._text = text
        self.rect = _FakeRect()

    def get_text(self, _kind: str) -> str:
        return self._text or ""


class RecordingDocument:
    """Context-manager double with no __del__: release can only happen explicitly."""

    # Mirrors the real PyMuPDF attribute the parser consults for password protection.
    needs_pass = 0

    def __init__(self, pages, *, fail_on_iteration: bool = False):
        self._pages = pages
        self._fail_on_iteration = fail_on_iteration
        self.events: list[str] = []

    def __enter__(self) -> RecordingDocument:
        self.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        name = exc_type.__name__ if exc_type else "none"
        self.events.append(f"exit({name})")
        return False  # never suppress the parser's own exception

    def close(self) -> None:  # must never be needed on these paths
        self.events.append("close")

    def __iter__(self):
        if self._fail_on_iteration:
            raise ValueError("document closed or encrypted")
        yield from self._pages


@pytest.fixture
def install_document(monkeypatch):
    """Hand the parser a recording double instead of a real PyMuPDF document."""
    created: list[RecordingDocument] = []

    def install(document: RecordingDocument) -> RecordingDocument:
        monkeypatch.setattr(parser_module.fitz, "open", lambda *a, **k: document)
        created.append(document)
        return document

    yield install, created


def test_successful_parse_exits_the_document_context(install_document):
    """Normal read: the double is entered and exited exactly once."""
    install, created = install_document
    document = install(RecordingDocument([FakePage("可见正文")]))

    sections = parse_document("irrelevant.pdf", "application/pdf")

    assert sections == [DocumentSection("page", "可见正文", 1)]
    assert document.events == ["enter", "exit(none)"], document.events
    assert "close" not in document.events, "release must go through the context manager"
    # Strong reference retained until this assertion ran.
    assert created == [document]


def test_internal_parse_exception_propagates_and_still_exits_the_context(install_document):
    """An internal iteration failure propagates after unwinding the context."""
    install, created = install_document
    document = install(RecordingDocument([], fail_on_iteration=True))

    with pytest.raises(ValueError, match="document closed or encrypted"):
        parse_document("irrelevant.pdf", "application/pdf")

    assert document.events == ["enter", "exit(ValueError)"], document.events
    assert "close" not in document.events, "failure must unwind through the context exit"
    assert created == [document]


def test_double_has_no_del(install_document):
    """Guard the premise: an explicit __del__ would make the assertions weaker."""
    assert "__del__" not in RecordingDocument.__dict__
    assert not hasattr(RecordingDocument, "__del__")
