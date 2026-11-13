"""Made-up papers: an arXiv answer and a source archive, built here (no real paper's text or figures)."""

from __future__ import annotations

import gzip
import io
import struct
import tarfile
import zlib

ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/api/x</id>
  <entry>
    <id>http://arxiv.org/abs/2401.01234v3</id>
    <title>Tiny Fields:
  Learning $\\alpha$-Blended Scenes in $O(n^2)$ Time</title>
    <updated>2024-03-01T10:00:00Z</updated>
    <summary>We present Tiny Fields, a method for scenes. It runs at 95\\% of real time with $\\mathbf{x}_{t+1}$ updates.
Code: https://github.com/example/tiny-fields. Video: https://youtu.be/abc123.</summary>
    <category term="cs.GR" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <published>2024-01-03T17:57:23Z</published>
    <arxiv:comment>Accepted to CVPR 2024 (highlight). 12 pages, 9 figures</arxiv:comment>
    <arxiv:primary_category term="cs.CV"/>
    <arxiv:doi>10.1234/example.5678</arxiv:doi>
    <author><name>Ada Example</name><arxiv:affiliation>Example University</arxiv:affiliation></author>
    <author><name>Bo  Sample</name><arxiv:affiliation>Sample Lab</arxiv:affiliation></author>
    <author><name>Cy Test</name></author>
  </entry>
</feed>"""

ERROR = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_9999.99999</id>
<title>Error</title><summary>incorrect id format for 9999.99999</summary></entry></feed>"""


def png(width: int = 2, height: int = 1) -> bytes:
    """A valid tiny PNG."""
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


MAIN = r"""\documentclass{article}
\usepackage{graphicx}
\graphicspath{{figs/}}
\title{Tiny Fields}
\begin{document}
\maketitle
% \begin{figure}\includegraphics{commented-out}\caption{Never}\end{figure}
\input{sections/intro}
\begin{figure*}
  \centering
  \includegraphics[width=\linewidth]{plot}
  \caption{Results: a PDF figure, skipped.}
\end{figure*}
\begin{figure}
  \includegraphics[width=0.9\linewidth]{figs/method.jpg}
  \caption{Our method, with $\alpha=0.5$.}\label{fig:method}
\end{figure}
\end{document}
"""
INTRO = r"""\section{Introduction}
\begin{figure}[t]
  \includegraphics{teaser}
  \caption{\textbf{Tiny Fields} renders scenes \emph{fast}.}
\end{figure}
"""


def source(gz: bool = True, extra: dict[str, bytes] | None = None) -> bytes:
    """A source archive like arXiv's: a gzipped tar of the TeX project."""
    files = {"main.tex": MAIN.encode(), "sections/intro.tex": INTRO.encode(), "figs/teaser.png": png(), "figs/method.jpg": b"\xff\xd8\xff\xe0jpeg",
             "figs/plot.pdf": b"%PDF-1.4 figure", **(extra or {})}  # fmt: skip
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(buf.getvalue()) if gz else buf.getvalue()


class FakeArxiv:
    """arXiv's API and e-print links, answering from the made-up paper."""

    def __init__(self, atom: str = ATOM, src: bytes | None = None, statuses: list[int] | None = None) -> None:
        self.atom, self.src = atom, source() if src is None else src
        self.statuses = statuses or []
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append(url)
        assert headers["User-Agent"].startswith("paper-page/")
        if self.statuses:
            return self.statuses.pop(0), {}, b"busy"
        if url.startswith("https://export.arxiv.org/api/query"):
            return 200, {"content-type": "application/atom+xml"}, self.atom.encode()
        if url.startswith("https://arxiv.org/e-print/"):
            return 200, {"content-type": "application/x-eprint-tar"}, self.src
        return 404, {}, b"not found"
