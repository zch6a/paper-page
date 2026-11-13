"""The real converter: pdftoppm on a one-page PDF made here (skipped where pdftoppm is not installed)."""

from __future__ import annotations

import shutil

import pytest

from paper_page import convert


def tiny_pdf() -> bytes:
    """A valid one-page PDF with a filled rectangle, written by hand (offsets computed)."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R >>",
    ]
    stream = b"0.2 0.4 0.8 rg 20 20 160 60 re f"
    objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def test_no_converter_without_pdftoppm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert convert.find_converter() is None


@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="pdftoppm is not installed")
def test_pdftoppm_turns_a_pdf_into_a_png_and_a_broken_one_into_none() -> None:
    c = convert.find_converter()
    assert c is not None
    png = c(tiny_pdf())
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(png[16:20], "big") == convert.WIDTH  # the width in the PNG header
    assert c(b"%PDF-1.4 not really") is None
