#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""harness55 probe: read-only capability probe for a pypdfium2-based PDF adapter.

Purpose
-------
Answer, with local evidence and no network, the questions that decide how the
PDFium adapter prototype must be written:

  * which pypdfium2 / PDFium / reportlab / PIL / pypdf versions are present;
  * which API surface exists (document open, page size, text page, bitmap,
    context-manager and ``closed`` support, raw error codes);
  * whether PDFium can read an in-memory buffer as well as a path;
  * whether native English *and* native CJK text can be extracted without OCR,
    and which font strategy makes that possible offline;
  * which exception type/message PDFium raises for corrupt, truncated and
    encrypted input (so the adapter can classify instead of leaking);
  * whether ``page.get_size()`` can be trusted to predict the bitmap pixel
    count before ``render()`` allocates it, including a rotated page;
  * what license metadata the installed pypdfium2 distribution actually ships.

This file writes nothing anywhere: it only reads local packages and builds
synthetic PDFs in memory. It is an evidence probe, not a test suite.
"""

from __future__ import annotations

import importlib.metadata as md
import inspect
import io
import json
import platform
import sys
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT: dict = {"probe": "harness55-pdfium55", "writes": "none (memory only)"}

FONT_CANDIDATES = [
    ("cid_stsong_light", r"C:\Windows\Fonts\STSONG.TTF", "UnicodeCIDFont:STSong-Light"),
    ("ttf_msyh", r"C:\Windows\Fonts\msyh.ttc", "TTFont:msyh.ttc"),
    ("ttf_simhei", r"C:\Windows\Fonts\simhei.ttf", "TTFont:simhei.ttf"),
    ("ttf_simsun", r"C:\Windows\Fonts\simsun.ttc", "TTFont:simsun.ttc"),
]

CJK_SAMPLE = "个人简历 数据库备份恢复记录 项目经历"


def rec(section: str, key: str, fn):
    """Record the outcome of ``fn`` under REPORT[section][key]; never raise."""
    try:
        entry = {"ok": True, "value": fn()}
    except Exception as exc:  # noqa: BLE001 - a probe must survive every failure
        entry = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().strip().splitlines()[-3:],
        }
    REPORT.setdefault(section, {})[key] = entry
    return entry.get("value")


def info_to_dict(value) -> object:
    """pypdfium2 version objects are not JSON serialisable; flatten them."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    fields = {
        name: str(getattr(value, name))
        for name in dir(value)
        if not name.startswith("_") and not callable(getattr(value, name, None))
    }
    return {"repr": str(value), "fields": fields} if fields else str(value)


def versions() -> dict:
    out = {
        "python": sys.version.split()[0],
        "python_full": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": {},
    }
    for name in ("pypdfium2", "reportlab", "pillow", "pypdf", "cryptography", "pycryptodome", "rapidocr"):
        try:
            out["packages"][name] = md.version(name)
        except md.PackageNotFoundError:
            out["packages"][name] = None
    return out


def api_surface() -> dict:
    import pypdfium2 as pdfium

    def sig(obj):
        try:
            return str(inspect.signature(obj))
        except (TypeError, ValueError) as exc:
            return f"<no signature: {type(exc).__name__}>"

    out = {
        "version_info": {
            "PYPDFIUM_INFO": info_to_dict(getattr(pdfium, "PYPDFIUM_INFO", None)),
            "PDFIUM_INFO": info_to_dict(getattr(pdfium, "PDFIUM_INFO", None)),
        },
        "signatures": {
            "PdfDocument.__new__": sig(pdfium.PdfDocument.__new__),
            "PdfPage.render": sig(pdfium.PdfPage.render),
            "PdfPage.get_textpage": sig(pdfium.PdfPage.get_textpage),
            "PdfPage.get_size": sig(pdfium.PdfPage.get_size),
            "PdfTextPage.get_text_range": sig(pdfium.PdfTextPage.get_text_range),
            "PdfBitmap.to_pil": sig(pdfium.PdfBitmap.to_pil),
        },
        "lifecycle": {},
        "error_codes": {},
    }
    for cls_name in ("PdfDocument", "PdfPage", "PdfTextPage", "PdfBitmap"):
        cls = getattr(pdfium, cls_name)
        out["lifecycle"][cls_name] = {
            "close": hasattr(cls, "close"),
            "context_manager": hasattr(cls, "__enter__") and hasattr(cls, "__exit__"),
            "closed_property": "closed" in dir(cls),
        }
    err = pdfium.PdfiumError
    out["error_codes"]["PdfiumError_mro"] = [c.__name__ for c in err.__mro__]
    out["error_codes"]["PdfiumError_attrs"] = [a for a in dir(err) if not a.startswith("_")]
    raw = pdfium.raw
    out["error_codes"]["raw_FPDF_ERR"] = sorted(n for n in dir(raw) if n.startswith("FPDF_ERR"))
    out["error_codes"]["raw_err_values"] = {
        n: getattr(raw, n) for n in sorted(dir(raw)) if n.startswith("FPDF_ERR")
    }
    out["error_codes"]["PdfDocument_load_methods"] = sorted(
        n for n in dir(raw) if "Load" in n and "Document" in n
    )
    return out


def build_text_pdf(lines: list[str], font_name: str = "Helvetica", font_size: int = 14) -> bytes:
    """Build a one-page PDF with native text, in memory."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf.setFont(font_name, font_size)
    y = A4[1] - 72
    for line in lines:
        pdf.drawString(72, y, line)
        y -= font_size * 1.6
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def register_font(label: str, path: str, spec: str) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    if spec.startswith("UnicodeCIDFont:"):
        name = spec.split(":", 1)[1]
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        return name
    name = f"probe_{label}"
    kwargs = {}
    if path.lower().endswith(".ttc"):
        kwargs["subfontIndex"] = 0
    pdfmetrics.registerFont(TTFont(name, path, **kwargs))
    return name


def attempt(fn):
    """Run fn() and return its value, or an error record; never raise."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a probe must survive every failure
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().strip().splitlines()[-3:],
        }


def text_extraction() -> dict:
    import pypdfium2 as pdfium

    def extract(raw: bytes) -> dict:
        with pdfium.PdfDocument(raw) as doc:
            page = doc[0]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                    chars = textpage.count_chars()
                finally:
                    textpage.close()
            finally:
                page.close()
        return {"chars": chars, "text": text, "cjk_roundtrip": "简历" in text}

    out = {
        "native_english": attempt(
            lambda: extract(build_text_pdf(["Native FastAPI resume line one", "second line"]))
        ),
        "cjk_candidates": {},
    }
    for label, path, spec in FONT_CANDIDATES:
        def one(label=label, path=path, spec=spec):
            if not Path(path).exists():
                return {"font_file_exists": False, "font_file": path}
            name = register_font(label, path, spec)
            raw = build_text_pdf(["Native EN line", CJK_SAMPLE], font_name=name)
            result = extract(raw)
            result.update(
                {"font_file_exists": True, "font_file": path, "font_name": name, "pdf_bytes": len(raw)}
            )
            return result

        out["cjk_candidates"][label] = attempt(one)
    return out


def classify(raw: bytes, password: str | None = None) -> dict:
    import pypdfium2 as pdfium

    kwargs = {"password": password} if password is not None else {}
    try:
        doc = pdfium.PdfDocument(raw, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - classification is the point
        return {
            "outcome": "raised",
            "class": type(exc).__name__,
            "mro": [c.__name__ for c in type(exc).__mro__],
            "message": str(exc),
            "err_code": getattr(exc, "err_code", None),
            "args": [repr(a) for a in getattr(exc, "args", ())],
        }
    try:
        return {"outcome": "opened", "pages": len(doc)}
    finally:
        doc.close()


def build_encrypted_pdf() -> dict:
    """Encrypt a synthetic PDF; report which offline strategy worked."""
    plain = build_text_pdf(["Encrypted native text"])
    attempts = {}

    def via_reportlab() -> bytes:
        from reportlab.lib.pdfencrypt import StandardEncryption
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas

        enc = StandardEncryption("userpw55", "ownerpw55", canPrint=1, canModify=0, strength=128)
        buffer = io.BytesIO()
        pdf = rl_canvas.Canvas(buffer, pagesize=A4, encrypt=enc)
        pdf.setFont("Helvetica", 14)
        pdf.drawString(72, 720, "Encrypted native text")
        pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    def via_pypdf() -> bytes:
        from pypdf import PdfWriter

        writer = PdfWriter(clone_from=io.BytesIO(plain))
        writer.encrypt(user_password="userpw55", owner_password="ownerpw55", algorithm="RC4-128")
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    for label, fn in (("reportlab_StandardEncryption", via_reportlab), ("pypdf_PdfWriter.encrypt", via_pypdf)):
        try:
            raw = fn()
            attempts[label] = {
                "ok": True,
                "bytes": len(raw),
                "no_password": classify(raw),
                "right_password": classify(raw, "userpw55"),
                "wrong_password": classify(raw, "nope"),
            }
        except Exception as exc:  # noqa: BLE001
            attempts[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return attempts


def geometry() -> dict:
    """Can page.get_size() predict render() dimensions, including rotation?"""
    import math

    import pypdfium2 as pdfium

    raw = build_text_pdf(["geometry probe"])
    out: dict = {}
    with pdfium.PdfDocument(raw) as doc:
        page = doc[0]
        try:
            for label, rotation in (("rotation_0", 0), ("rotation_90", 90), ("rotation_180", 180)):
                if rotation:
                    page.set_rotation(rotation)
                size = page.get_size()
                predicted = (math.ceil(size[0] * 2), math.ceil(size[1] * 2))
                bitmap = page.render(scale=2)
                try:
                    actual = (bitmap.width, bitmap.height)
                finally:
                    bitmap.close()
                out[label] = {
                    "get_rotation": page.get_rotation(),
                    "get_size_points": [round(size[0], 3), round(size[1], 3)],
                    "predicted_px_scale2": list(predicted),
                    "actual_px": list(actual),
                    "prediction_exact": predicted == actual,
                    "pixels": actual[0] * actual[1],
                }
        finally:
            page.close()
    return out


def buffer_and_buffer_protocol() -> dict:
    import pypdfium2 as pdfium

    raw = build_text_pdf(["buffer probe"])
    out = {}
    for label, payload in (
        ("bytes", raw),
        ("bytearray", bytearray(raw)),
        ("memoryview", memoryview(raw)),
        ("BytesIO", io.BytesIO(raw)),
        ("path_str", None),
    ):
        if payload is None:
            continue
        try:
            doc = pdfium.PdfDocument(payload)
            out[label] = {"ok": True, "pages": len(doc)}
            doc.close()
        except BaseException as exc:  # noqa: BLE001
            out[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return out


def license_metadata() -> dict:
    dist = md.distribution("pypdfium2")
    meta = dist.metadata
    out = {
        "name": meta.get("Name"),
        "version": dist.version,
        "metadata_License": meta.get("License"),
        "metadata_License_Expression": meta.get("License-Expression"),
        "classifiers": [c for c in (meta.get_all("Classifier") or []) if "License" in c],
        "require_python": meta.get("Requires-Python"),
    }
    names = []
    for rel in dist.files or []:
        low = str(rel).lower()
        if "licen" in low or "copying" in low or "notice" in low:
            names.append(str(rel))
    out["license_files"] = sorted(names)[:24]
    heads = {}
    for rel in sorted(names)[:8]:
        path = Path(dist.locate_file(rel))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            heads[str(rel)] = {
                "bytes": path.stat().st_size,
                "head": [ln.strip() for ln in text.splitlines() if ln.strip()][:4],
            }
        except OSError as exc:
            heads[str(rel)] = {"error": f"{type(exc).__name__}: {exc}"}
    out["license_heads"] = heads
    return out


def thread_safety_note() -> dict:
    return {
        "runtime_test": "not applicable: PDFium is documented as not thread-safe",
        "official_statement_sources": [
            "https://pypdfium2.readthedocs.io/en/stable/readme.html",
            "https://pypdfium2.readthedocs.io/en/stable/python_api.html",
        ],
        "prototype_rule": "one process, one thread; process isolation only; no new parsing threads",
        "network_access_during_probe": False,
    }


def main() -> None:
    import argparse
    import hashlib

    parser = argparse.ArgumentParser(description="harness55 pypdfium2 capability probe")
    parser.add_argument("--verify", help="re-verify a previously captured probe log")
    args = parser.parse_args()

    if args.verify:
        text = Path(args.verify).read_text(encoding="utf-8")
        marker = "===== PDFIUM55 PROBE SHA256: "
        body, sep, rest = text.partition(marker)
        if not sep:
            print("FAIL: probe hash declaration missing")
            raise SystemExit(2)
        declared = rest.replace(" =====", "").strip()
        if body.endswith("\n"):
            body = body[:-1]  # the run prints exactly one newline between body and marker
        recomputed = hashlib.sha256(body.encode("utf-8")).hexdigest()
        print(f"probe_sha256_declared={declared}")
        print(f"probe_sha256_recomputed={recomputed}")
        print(f"probe_bytes={len(body.encode('utf-8'))}")
        print(f"VERDICT={'PASS' if declared == recomputed else 'FAIL'}")
        raise SystemExit(0 if declared == recomputed else 1)

    import pypdfium2 as pdfium

    rec("environment", "versions", versions)
    rec("environment", "api_surface", api_surface)
    rec("environment", "buffer_protocol", buffer_and_buffer_protocol)
    rec("environment", "license_metadata", license_metadata)
    rec("environment", "thread_safety", thread_safety_note)
    rec("extraction", "text", text_extraction)

    def errors() -> dict:
        good = build_text_pdf(["corruption probe"])
        return {
            "not_a_pdf": classify(b"this is not a pdf at all"),
            "pdf_header_then_nul": classify(b"%PDF-1.7\n" + b"\x00" * 512),
            "truncated_valid_pdf": classify(good[:200]),
            "valid_pdf_control": classify(good),
            "empty_bytes": classify(b""),
        }

    rec("errors", "classification", errors)
    rec("errors", "encrypted", build_encrypted_pdf)
    rec("geometry", "size_vs_bitmap", geometry)
    REPORT["pdfium_module_file"] = getattr(pdfium, "__file__", None)
    body = json.dumps(REPORT, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    print(body)
    print(f"===== PDFIUM55 PROBE SHA256: {digest} =====")


if __name__ == "__main__":
    main()
