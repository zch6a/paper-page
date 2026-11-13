"""Regression tests for what the second independent review found (polishing round 5)."""

from __future__ import annotations

import gzip
import time
from pathlib import Path

import pytest
from fixtures import FakeArxiv, png, source

from paper_page import cli
from paper_page.arxiv import Client
from paper_page.make import found_links, from_tex, take_figures
from paper_page.tex import figures, to_text


def fake_cli(monkeypatch: pytest.MonkeyPatch, fake: FakeArxiv) -> None:
    monkeypatch.setattr(cli, "Client", lambda: Client(get=fake, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)


def test_a_failed_source_download_still_makes_the_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeArxiv()
    real = fake.__call__

    def no_eprint(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        return (404, {}, b"") if "/e-print/" in url else real(url, headers)

    monkeypatch.setattr(cli, "Client", lambda: Client(get=no_eprint, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    err = capsys.readouterr().err
    assert "answered 404" in err and "no figures taken" in err and (tmp_path / "p" / "page.json").exists()


def test_a_too_large_source_gives_one_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from paper_page.tex import MAX_TOTAL

    fake_cli(monkeypatch, FakeArxiv(src=gzip.compress(b"\0" * (MAX_TOTAL + 1024), compresslevel=9)))
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    err = capsys.readouterr().err
    assert "larger than" in err and "no TeX source" not in err


def test_escaped_characters_line_breaks_degrees_and_dotted_words() -> None:
    assert to_text(r"costs less than \$10") == "costs less than $10"
    assert to_text(r"a\textasciitilde b and the set \{x, y\}") == "a~b and the set {x, y}"
    assert to_text(r"Input\\Output pairs") == "Input Output pairs"
    assert to_text(r"$90^\circ$ and $45^{\circ}$") == "90° and 45°"
    assert to_text("exported to the .ply format and loaded by .NET.") == "exported to the .ply format and loaded by .NET."


def test_a_figure_of_subfigures_has_its_own_caption() -> None:
    tex = r"""\begin{figure}
\begin{subfigure}{.5\linewidth}\includegraphics{a}\caption{Input}\end{subfigure}
\begin{subfigure}{.5\linewidth}\includegraphics{b}\caption{Output}\end{subfigure}
\caption{Our method turns inputs into outputs.}\end{figure}"""
    assert [(f.image, f.caption) for f in figures(tex)] == [("a", "Our method turns inputs into outputs.")]


def test_a_missing_first_figure_leaves_no_teaser_and_says_so() -> None:
    files = {
        "main.tex": rb"""\documentclass{article}\begin{document}
\begin{figure}\includegraphics{teaser.tif}\caption{Teaser.}\end{figure}
\begin{figure}\includegraphics{results}\caption{Results.}\end{figure}\end{document}""",
        "results.png": png(),
    }
    figs = take_figures(files, 4)
    assert figs.teaser is None and figs.teaser_skipped == "teaser.tif" and figs.missing == ["teaser.tif"] and len(figs.figures) == 1


def test_image_extensions_in_any_case_and_pdflatex_order() -> None:
    files = {"main.tex": rb"\documentclass{article}\begin{document}\begin{figure}\includegraphics{teaser}\caption{T.}\end{figure}\end{document}",
             "teaser.PNG": png()}  # fmt: skip
    assert take_figures(files, 4).teaser is not None
    both = {**files, "teaser.pdf": b"%PDF-1.4"}
    converted = take_figures(both, 4, convert=lambda pdf: png(7, 7))
    assert converted.converted == ["teaser.pdf"]  # the PDF is what the paper prints: it is the one shown when it can be
    assert take_figures(both, 4).teaser is not None  # without a converter, the PNG of the same name stands in


def test_an_unambiguous_host_beats_the_words_before_it() -> None:
    assert [x.label for x in found_links("Code and data are available at https://github.com/a/b")] == ["Code"]
    assert [x.label for x in found_links("The code for this project is available at https://github.com/a/b")] == ["Code"]


def test_tex_projects_use_their_macros_nested_thanks_and_icml_commands() -> None:
    files = {
        "main.tex": rb"""\documentclass{article}\newcommand{\ours}{TinyNeRF}\title{\ours: Fast Fields\thanks{Funded by \emph{X}}}
\begin{document}\begin{abstract}\ours{} is fast.\end{abstract}\end{document}"""
    }
    page = from_tex(files)
    assert page.title == "TinyNeRF: Fast Fields" and page.abstract == "TinyNeRF is fast."
    icml = {
        "main.tex": rb"""\documentclass{article}\begin{document}\twocolumn[\icmltitle{An ICML Paper}
\icmlauthor{Ada Example}{u}\icmlauthor{Bo Sample}{v}]\end{document}"""
    }
    page = from_tex(icml)
    assert page.title == "An ICML Paper" and [a.name for a in page.authors] == ["Ada Example", "Bo Sample"]


def test_captionof_without_an_image_of_its_own_takes_none() -> None:
    tex = r"""\begin{figure}\includegraphics{one}\caption{One.}\end{figure}
\begin{center}\begin{tikzpicture}\end{tikzpicture}\captionof{figure}{TikZ teaser.}\end{center}"""
    assert [(f.image, f.caption) for f in figures(tex)] == [("one", "One.")]


def test_many_captionof_and_figures_are_still_fast() -> None:
    tex = r"\begin{figure}\includegraphics{x}\caption{X}\end{figure}\includegraphics{y}\captionof{figure}{Y}" * 8000
    start = time.perf_counter()
    assert len(figures(tex)) == 16000 and time.perf_counter() - start < 3


def test_an_eps_teaser_hint_does_not_suggest_pdftoppm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    src = source(
        extra={
            "main.tex": rb"\documentclass{article}\begin{document}\begin{figure}\includegraphics{t.eps}\caption{T.}\end{figure}\end{document}",
            "t.eps": b"%!PS",
        }
    )
    fake_cli(monkeypatch, FakeArxiv(src=src))
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    out = capsys.readouterr().out
    assert "pdftoppm does not read EPS" in out and "-singlefile t.eps" not in out
