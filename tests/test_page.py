from __future__ import annotations

import gzip
import io
import json
import tarfile
from pathlib import Path

import pytest
from fixtures import ATOM, ERROR, FakeArxiv, png, source

from paper_page import cli
from paper_page.arxiv import ArxivError, Client, entry_of, parse_id
from paper_page.make import from_entry, from_tex, take_figures, venue_of
from paper_page.model import Author, Figure, Link, Page
from paper_page.render import render
from paper_page.tex import read_source


def client(fake: FakeArxiv, sleeps: list[float] | None = None) -> Client:
    return Client(get=fake, sleep=(sleeps.append if sleeps is not None else lambda _: None))


# --- arXiv ---


def test_ids_and_links() -> None:
    assert parse_id(" https://arxiv.org/abs/2401.01234v3 ") == ("2401.01234", "v3")
    assert parse_id("https://export.arxiv.org/abs/2401.01234?context=cs") == ("2401.01234", "")
    for bad in ("", "2401.123", "https://example.org/abs/2401.01234", "10.1234/x"):
        with pytest.raises(ArxivError, match="not an arXiv ID"):
            parse_id(bad)


def test_the_entry_becomes_a_page() -> None:
    page = from_entry(entry_of(ATOM.encode(), "2401.01234"), "2401.01234")
    assert page.title == "Tiny Fields: Learning α-Blended Scenes in O(n²) Time"
    assert [(a.name, a.affiliation) for a in page.authors] == [("Ada Example", "Example University"), ("Bo Sample", "Sample Lab"), ("Cy Test", "")]
    assert page.version == "v3" and page.published == "2024-01-03" and page.categories == ["cs.CV", "cs.GR"]
    assert page.venue == "CVPR 2024 (highlight)" and page.doi == "10.1234/example.5678"
    assert "95% of real time with xₜ₊₁ updates" in page.abstract
    assert [(x.label, x.url) for x in page.links] == [
        ("arXiv", "https://arxiv.org/abs/2401.01234"), ("DOI", "https://doi.org/10.1234/example.5678"), ("PDF", "https://arxiv.org/pdf/2401.01234"),
        ("Code", "https://github.com/example/tiny-fields"), ("Video", "https://youtu.be/abc123"),
    ]  # fmt: skip
    assert page.bibtex.startswith("@misc{example2024tiny,") and "note          = {CVPR 2024 (highlight)}" in page.bibtex
    assert "author        = {Example, Ada and Sample, Bo and Test, Cy}" in page.bibtex


def test_an_unknown_id_and_a_broken_answer_are_errors() -> None:
    with pytest.raises(ArxivError, match="has no paper 9999.99999: incorrect id format"):
        entry_of(ERROR.encode(), "9999.99999")
    with pytest.raises(ArxivError, match="not Atom"):
        entry_of(b"<html>", "x")
    with pytest.raises(ArxivError, match="has no paper"):
        entry_of(b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>', "x")


def test_the_client_paces_itself_and_retries_when_busy() -> None:
    sleeps: list[float] = []
    fake = FakeArxiv(statuses=[503])
    c = client(fake, sleeps)
    c.metadata("2401.01234")
    c.source("2401.01234")
    assert len(fake.calls) == 3 and 10.0 in sleeps  # one retry after the 503
    assert any(2.0 < s <= 3.0 for s in sleeps)  # the three seconds arXiv asks for between requests
    with pytest.raises(ArxivError, match="answered 404"):
        Client(get=lambda u, h: (404, {}, b""), sleep=lambda _: None).fetch("https://arxiv.org/e-print/x")


def test_venues_named_plainly_and_not_otherwise() -> None:
    assert venue_of("To appear in ICML 2024") == "ICML 2024"
    assert venue_of("Published at the ACL 2023 main conference") == "ACL 2023"
    assert venue_of("NeurIPS 2023 spotlight; code soon") == "NeurIPS 2023"
    assert venue_of("Accepted for publication") == "" and venue_of("") == "" and venue_of("Preprint, 2024") == ""


# --- the source ---


def test_sources_are_read_in_memory_and_names_cannot_leave_the_archive() -> None:
    assert set(read_source(source())) == {"main.tex", "sections/intro.tex", "figs/teaser.png", "figs/method.jpg", "figs/plot.pdf"}
    assert "main.tex" in read_source(source(gz=False))
    assert read_source(gzip.compress(b"\\documentclass{article}\\begin{document}x\\end{document}")) == {
        "main.tex": b"\\documentclass{article}\\begin{document}x\\end{document}"
    }
    assert read_source(b"%PDF-1.5 a paper") == {} and read_source(b"\x1f\x8b broken") == {} and read_source(b"garbage") == {}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in ("../evil.tex", "/abs.tex", "C:/win.tex", "ok/../../up.tex", "fine.tex"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        link = tarfile.TarInfo("link.tex")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    assert read_source(buf.getvalue()) == {"fine.tex": b"x"}


def test_figures_with_their_captions_the_teaser_first() -> None:
    figs = take_figures(read_source(source()), 4)
    assert figs.teaser == Figure("figures/fig-1.png", "Tiny Fields renders scenes fast.", "Tiny Fields renders scenes fast.")
    assert [(f.src, f.caption) for f in figs.figures] == [("figures/fig-2.jpg", "Our method, with α=0.5.")]
    assert figs.skipped == ["figs/plot.pdf"] and figs.images["figures/fig-1.png"] == png()
    assert take_figures(read_source(source()), 1).figures == [] and take_figures(read_source(source()), 0).teaser is None


def test_a_pdf_teaser_leaves_no_teaser_rather_than_promoting_a_later_figure() -> None:
    pdf_first = {
        "main.tex": rb"""\documentclass{article}\begin{document}
\begin{figure}\includegraphics{teaser}\caption{The real teaser.}\end{figure}
\begin{figure}\includegraphics{later}\caption{Results \cite{someone2020} in Fig.~\ref{fig:x}.}\end{figure}\end{document}""",
        "teaser.pdf": b"%PDF-1.4",
        "later.png": png(),
    }
    figs = take_figures(pdf_first, 4)
    assert figs.teaser is None and figs.teaser_skipped == "teaser.pdf"
    assert [(f.src, f.caption) for f in figs.figures] == [("figures/fig-1.png", "Results in Fig..")]


def test_a_page_from_a_tex_project() -> None:
    files = {
        "paper.tex": rb"""\documentclass{article}\title{A Local Paper\thanks{Draft.}}
\author{Ada Example\thanks{Equal.} \\ Univ A \And Bo Sample \\ Lab B}
\begin{document}\begin{abstract}We do \emph{things}.\end{abstract}\end{document}"""
    }
    page = from_tex(files)
    assert page.title == "A Local Paper" and [a.name for a in page.authors] == ["Ada Example", "Bo Sample"] and page.abstract == "We do things."
    with pytest.raises(ValueError, match="no main TeX file"):
        from_tex({"x.tex": b"no class"})


# --- page.json and the HTML ---


def page() -> Page:
    return Page("Tiny <script>alert(1)</script> Fields",
                [Author("Ada Example", "https://ada.example", "Univ A; Lab C"), Author("Bo Sample", "", "Lab C")],
                abstract="We & they.", arxiv="2401.01234", version="v3", published="2024-01-03", venue="CVPR 2024",
                links=[Link("arXiv", "https://arxiv.org/abs/2401.01234"), Link("Code", "javascript:alert(1)")],
                teaser=Figure("figures/fig-1.png", "A teaser."), figures=[Figure("../secret.png"), Figure("https://cdn.example/x.png", "Remote")],
                bibtex="@misc{x}", doi="10.1/x")  # fmt: skip


def test_the_html_escapes_text_and_leaves_out_unsafe_links() -> None:
    out, warnings = render(page())
    assert "<script>alert(1)" not in out and "Tiny &lt;script&gt;alert(1)&lt;/script&gt; Fields" in out
    assert "javascript:" not in out and "../secret.png" not in out and 'src="https://cdn.example/x.png"' in out
    assert any("Code" in w for w in warnings) and any("secret" in w for w in warnings)
    assert '<a href="https://ada.example">Ada Example</a><sup>1,2</sup>' in out and "<sup>2</sup>Lab C" in out


def test_the_head_carries_scholar_and_preview_tags_and_nothing_is_fetched() -> None:
    out, _ = render(page())
    for tag in ('name="citation_title"', 'name="citation_author" content="Bo Sample"', 'name="citation_publication_date" content="2024/01/03"',
                'name="citation_arxiv_id" content="2401.01234"', 'name="citation_pdf_url" content="https://arxiv.org/pdf/2401.01234"',
                'name="citation_doi" content="10.1/x"', 'property="og:title"'):  # fmt: skip
        assert tag in out
    assert "og:image" not in out  # a relative teaser needs site_url
    p = page()
    p.site_url = "https://ada.example/tiny"
    out, _ = render(p)
    assert (
        'property="og:image" content="https://ada.example/tiny/figures/fig-1.png"' in out
        and 'rel="canonical" href="https://ada.example/tiny/"' in out
    )
    assert '<link rel="stylesheet"' not in out and "<script src" not in out and "@import" not in out
    assert "prefers-color-scheme:dark" in out


def test_page_json_round_trips_and_wrong_fields_are_named() -> None:
    p = page()
    assert Page.from_json(p.to_json()) == p
    for bad, message in (('{"title": ""}', "title is empty"), ('{"title": "T", "authors": [{"url": "x"}]}', "author 1 has no name"),
                         ('{"title": "T", "accent": "red"}', "accent is a color"), ('{"title": "T", "colour": 1}', "unknown field"),
                         ('{"title": "T", "links": [{"label": "Code"}]}', "link 1 needs"),
                         ('{"title": "T", "teaser": {"caption": "x"}}', "teaser needs a src"), ("[1]", "an object"), ("{", "not JSON")):  # fmt: skip
        with pytest.raises(ValueError, match=message):
            Page.from_json(bad)


# --- the command line ---


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeArxiv:
    f = FakeArxiv()
    monkeypatch.setattr(cli, "Client", lambda: Client(get=f, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)  # no pdftoppm, whatever this machine has
    return f


def test_new_writes_the_page_its_data_and_figures(tmp_path: Path, fake: FakeArxiv, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "page"
    assert cli.main(["new", "arXiv:2401.01234", "-o", str(out)]) == 0
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "figures/fig-1.png",
        "figures/fig-2.jpg",
        "index.html",
        "page.json",
    ]
    data = json.loads((out / "page.json").read_text(encoding="utf-8"))
    assert data["venue"] == "CVPR 2024 (highlight)" and data["teaser"]["src"] == "figures/fig-1.png"
    text = capsys.readouterr().out
    assert "venue: CVPR 2024 (highlight)" in text and "skipped: figs/plot.pdf" in text and "figures: 2 taken" in text
    assert cli.main(["new", "2401.01234", "-o", str(out)]) == 2  # page.json is the author's: not replaced
    assert "exists" in capsys.readouterr().err


def test_render_after_editing_page_json(tmp_path: Path, fake: FakeArxiv, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "page"
    cli.main(["new", "2401.01234", "-o", str(out), "--figures", "0"])
    data = json.loads((out / "page.json").read_text(encoding="utf-8"))
    data["authors"][0]["url"] = "https://ada.example"
    data["links"].append({"label": "Data", "url": "https://zenodo.org/records/1"})
    data["figures"] = [{"src": "figures/missing.png"}]
    (out / "page.json").write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["render", str(out)]) == 0
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="https://ada.example"' in html and "https://zenodo.org/records/1" in html
    assert "figures/missing.png is not in" in capsys.readouterr().err
    assert len(fake.calls) == 1  # --figures 0: the source is not fetched


def test_new_from_a_local_tex_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    proj = tmp_path / "paper"
    (proj / "figs").mkdir(parents=True)
    (proj / "main.tex").write_text(
        r"""\documentclass{article}\graphicspath{{figs/}}\title{Local}\author{Ada Example}
\begin{document}\begin{figure}\includegraphics{teaser}\caption{T.}\end{figure}\end{document}""",
        encoding="utf-8",
    )
    (proj / "other.tex").write_text(r"\documentclass{article}\title{Not this one}\begin{document}\end{document}" + "x" * 5000, encoding="utf-8")
    (proj / "figs" / "teaser.png").write_bytes(png())
    assert cli.main(["new", "--tex", str(proj / "main.tex"), "-o", str(tmp_path / "page")]) == 0
    data = json.loads((tmp_path / "page" / "page.json").read_text(encoding="utf-8"))
    assert data["title"] == "Local" and data["teaser"]["src"] == "figures/fig-1.png" and data["arxiv"] == ""


def test_errors_are_one_line_and_exit_2(tmp_path: Path, fake: FakeArxiv, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["new", "not-an-id", "-o", str(tmp_path / "p")]) == 2
    assert "not an arXiv ID" in capsys.readouterr().err
    assert cli.main(["new", "-o", str(tmp_path / "p")]) == 2
    assert cli.main(["render", str(tmp_path / "nowhere")]) == 2
    assert "cannot be read" in capsys.readouterr().err


def fake_converter(pdf: bytes) -> bytes | None:
    return png(3, 2) if pdf.startswith(b"%PDF") and b"broken" not in pdf else None


def test_pdf_figures_are_converted_when_a_converter_is_there() -> None:
    files = {
        "main.tex": rb"""\documentclass{article}\begin{document}
\begin{figure}\includegraphics{teaser}\caption{Teaser.}\end{figure}
\begin{figure}\includegraphics{bad}\caption{Broken.}\end{figure}
\begin{figure}\includegraphics{ok}\caption{Fine.}\end{figure}\end{document}""",
        "teaser.pdf": b"%PDF-1.4 teaser",
        "bad.pdf": b"%PDF-1.4 broken",
        "ok.png": png(),
    }
    figs = take_figures(files, 4, convert=fake_converter)
    assert figs.teaser == Figure("figures/fig-1.png", "Teaser.", "Teaser.") and figs.images["figures/fig-1.png"] == png(3, 2)
    assert figs.converted == ["teaser.pdf"] and figs.skipped == ["bad.pdf"] and [f.src for f in figs.figures] == ["figures/fig-2.png"]
    assert take_figures(files, 4, convert=lambda pdf: b"not a png").teaser is None  # an answer that is not a PNG is not used


def test_the_cli_converts_with_pdftoppm_unless_told_not_to(tmp_path: Path, fake: FakeArxiv, monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setattr(cli, "find_converter", lambda: fake_converter)
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "a")]) == 0
    assert "3 taken, 1 of them converted from PDF" in capsys.readouterr().out
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "b"), "--no-convert"]) == 0
    text = capsys.readouterr().out
    assert "2 taken" in text and "skipped: figs/plot.pdf" in text and "pdftoppm installed" not in text


def test_without_pdftoppm_the_report_says_how_to_get_conversion(tmp_path: Path, fake: FakeArxiv, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "a")]) == 0
    assert "with poppler's pdftoppm installed" in capsys.readouterr().out


def test_a_converted_photo_may_come_back_as_jpeg_and_macros_are_used_in_captions() -> None:
    files = {
        "main.tex": rb"""\documentclass{article}\newcommand{\model}{SAM\xspace}\begin{document}
\begin{figure}\includegraphics{photo}\caption{Masks from \model{} at quality \cite{x}, here.}\end{figure}\end{document}""",
        "photo.pdf": b"%PDF-1.4 photo",
    }
    figs = take_figures(files, 4, convert=lambda pdf: b"\xff\xd8\xff\xe0 a jpeg")
    assert figs.teaser == Figure("figures/fig-1.jpg", "Masks from SAM at quality, here.", "Masks from SAM at quality, here.")


def test_force_clears_the_old_figures_paper_page_made_and_nothing_else(tmp_path: Path, fake: FakeArxiv) -> None:
    out = tmp_path / "page"
    (out / "figures").mkdir(parents=True)
    for name in ("fig-1.jpg", "fig-9.png", "my-diagram.png", "fig-notes.txt"):
        (out / "figures" / name).write_bytes(b"old")
    (out / "page.json").write_text("{}", encoding="utf-8")
    assert cli.main(["new", "2401.01234", "-o", str(out), "--force"]) == 0
    assert sorted(p.name for p in (out / "figures").iterdir()) == ["fig-1.png", "fig-2.jpg", "fig-notes.txt", "my-diagram.png"]
    assert (out / "figures" / "fig-2.jpg").read_bytes() != b"old"


def test_one_link_of_each_kind_when_the_comment_and_the_abstract_both_name_one() -> None:
    atom = ATOM.replace("Accepted to CVPR 2024 (highlight). 12 pages, 9 figures", "Project page: https://example.org/tiny")
    atom = atom.replace("Video: https://youtu.be/abc123.", "See https://example.org/other for more.")
    page = from_entry(entry_of(atom.encode(), "2401.01234"), "2401.01234")
    assert [x.label for x in page.links].count("Project page") == 1 and ("Project page", "https://example.org/tiny") in [
        (x.label, x.url) for x in page.links
    ]


def test_a_tex_project_keeps_the_links_its_abstract_names() -> None:
    files = {
        "p.tex": rb"""\documentclass{article}\title{T}\begin{document}\begin{abstract}Code: \url{https://github.com/a/b}.\end{abstract}\end{document}"""
    }
    assert [(x.label, x.url) for x in from_tex(files).links] == [("Code", "https://github.com/a/b")]


def test_an_svg_teaser_with_a_site_url_warns_about_link_previews() -> None:
    p = page()
    p.site_url, p.teaser = "https://ada.example/tiny/", Figure("figures/teaser.svg", "T.")
    assert any("SVG" in w for w in render(p)[1])


def test_no_arguments_prints_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2 and "paper-page new 2003.08934" in capsys.readouterr().out


def test_the_page_carries_a_policy_that_runs_only_its_own_script() -> None:
    import base64
    import hashlib
    import re as regex

    out, _ = render(page())
    csp = regex.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', out)
    script = regex.search(r"<script>(.*?)</script>", out, flags=regex.S)
    assert csp and script
    digest = base64.b64encode(hashlib.sha256(script.group(1).encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in csp.group(1) and "default-src 'none'" in csp.group(1)
    assert out.count("<script") == 1
