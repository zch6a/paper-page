"""PDF figures to PNG, with poppler's pdftoppm when it is installed (MiKTeX ships it; on Linux and macOS it comes with
poppler-utils / poppler). The PDF is written to a temporary folder, converted there (its first page, 1600 pixels wide)
and the folder removed; pdftoppm runs without a shell, with a time limit. A diagram stays a PNG; a figure of photos,
large as a PNG, becomes a JPEG when that is smaller."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

Converter = Callable[[bytes], "bytes | None"]  # a PDF -> a PNG or JPEG image, or None when it could not be converted
WIDTH = 1600
TIMEOUT = 60
LARGE = 600 * 1024  # a PNG larger than this is mostly photo: it is tried as JPEG too, and the smaller kept


def find_converter() -> Converter | None:
    """pdftoppm as a converter, or None when it is not installed."""
    exe = shutil.which("pdftoppm")
    if exe is None:
        return None

    def run(src: Path, out: Path, *kind: str) -> bytes | None:
        try:
            done = subprocess.run(  # noqa: S603 - a fixed program and arguments, no shell
                [exe, *kind, "-f", "1", "-l", "1", "-singlefile", "-scale-to-x", str(WIDTH), "-scale-to-y", "-1", str(src), str(out)],
                capture_output=True,
                timeout=TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        made = out.with_suffix(".jpg" if "-jpeg" in kind else ".png")
        return made.read_bytes() if done.returncode == 0 and made.is_file() else None

    def convert(pdf: bytes) -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="paper-page-") as tmp:
            src = Path(tmp) / "figure.pdf"
            src.write_bytes(pdf)
            png = run(src, Path(tmp) / "figure", "-png")
            if png is None or len(png) <= LARGE:
                return png
            jpeg = run(src, Path(tmp) / "photo", "-jpeg", "-jpegopt", "quality=85")
            return jpeg if jpeg is not None and len(jpeg) < len(png) else png

    return convert
