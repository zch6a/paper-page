"""Regression tests for what the first independent review found (polishing round 2)."""

from __future__ import annotations

import gzip
import io
import os
import tarfile
import time
from pathlib import Path

import pytest
from fixtures import FakeArxiv, png

from paper_page import cli
from paper_page.arxiv import Client
from paper_page.make import bibtex, from_tex, venue_of
from paper_page.model import Author, Page
from paper_page.render import safe_src
from paper_page.tex import MAX_TOTAL, SourceTooLarge, expand, figures, main_file, read_source, to_text, use_macros


def test_a_gzip_bomb_is_refused_without_inflating_it() -> None:
    bomb = gzip.compress(b"\0" * (MAX_TOTAL + 1024), compresslevel=9)
    assert len(bomb) < MAX_TOTAL // 100
    with pytest.raises(SourceTooLarge):
        read_source(bomb)


def test_a_corrupt_archive_is_no_source_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    corrupt = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + b"\xff" * 64
    assert read_source(corrupt) == {}
    fake = FakeArxiv(src=corrupt)
    monkeypatch.setattr(cli, "Client", lambda: Client(get=fake, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    assert "no TeX source" in capsys.readouterr().err


def test_a_too_large_source_still_makes_the_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeArxiv(src=gzip.compress(b"\0" * (MAX_TOTAL + 1024), compresslevel=9))
    monkeypatch.setattr(cli, "Client", lambda: Client(get=fake, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    assert "larger than" in capsys.readouterr().err and (tmp_path / "p" / "index.html").exists()


def test_tex_projects_do_not_follow_links_out_of_the_project(tmp_path: Path) -> None:
    secret = tmp_path / "private.png"
    secret.write_bytes(png(5, 5))
    proj = tmp_path / "paper"
    proj.mkdir()
    tex = r"\documentclass{article}\title{T}\begin{document}\begin{figure}\includegraphics{teaser}\caption{C.}\end{figure}\end{document}"
    (proj / "main.tex").write_text(tex, encoding="utf-8")
    try:
        os.symlink(secret, proj / "teaser.png")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links need extra rights on this system")
    out = tmp_path / "page"
    assert cli.main(["new", "--tex", str(proj / "main.tex"), "-o", str(out), "--no-convert"]) == 0
    assert not (out / "figures").exists() or not any((out / "figures").iterdir())


def test_inputs_that_include_each_other_do_not_multiply() -> None:
    files = {"a.tex": b"\\input{b}" * 10 + b"A", "b.tex": b"\\input{a}" * 10 + b"B"}
    start = time.perf_counter()
    assert expand("a.tex", files) == "BA" and time.perf_counter() - start < 1


def test_unclosed_figures_do_not_take_quadratic_time() -> None:
    tex = "\\begin{figure}" * 20000 + "x" * 100000
    start = time.perf_counter()
    assert figures(tex) == [] and time.perf_counter() - start < 2


def test_a_macro_that_contains_itself_stops_growing() -> None:
    out = use_macros("x \\a y", {"a": "\\a " * 300})
    assert len(out) < 10000


def test_submissions_workshops_and_tracks_are_not_the_venue() -> None:
    for comment in ("NeurIPS 2023 submission", "Accepted at the ICML 2023 Workshop on Things", "NeurIPS 2023 Datasets and Benchmarks Track",
                    "CVPR 2024 Workshops", "Under review at ICLR 2025", "Findings of ACL 2023"):  # fmt: skip
        assert venue_of(comment) == "", comment
    assert venue_of("Accepted to ICLR 2024 (oral)") == "ICLR 2024 (oral)"


def test_special_letters_and_urls_in_text() -> None:
    assert to_text(r"Bj\o rn and Stra\ss e, \LaTeX{} and \'{\i}") == "Bjørn and Straße, LaTeX and í"
    assert to_text(r"see https://example.org/~ada/model_2 now") == "see https://example.org/~ada/model_2 now"


def test_authors_of_lncs_and_acmart_projects() -> None:
    lncs = {"p.tex": rb"\documentclass{llncs}\title{T}\author{Ada Example\inst{1} \and Bo Sample\inst{2}}\begin{document}\end{document}"}
    assert [a.name for a in from_tex(lncs).authors] == ["Ada Example", "Bo Sample"]
    acm = {
        "p.tex": rb"\documentclass{acmart}\title{T}\author{Ada Example}\affiliation{U}\author{Bo Sample}\affiliation{V}\begin{document}\end{document}"
    }
    assert [a.name for a in from_tex(acm).authors] == ["Ada Example", "Bo Sample"]


def test_bibtex_escapes_and_suffixes() -> None:
    entry = bibtex(Page("Fast C# code_gen for 100$", [Author("Ada Example Jr.")], published="2024-01-01"))
    assert entry.startswith("@misc{example2024fast,")
    assert r"{{Fast C\# code\_gen for 100\$}}" in entry and "{Example, Jr., Ada}" in entry


def test_a_failed_write_leaves_the_old_page(tmp_path: Path) -> None:
    (tmp_path / "page.json").write_text('{"title": "Bad \\ud800 title"}', encoding="utf-8")
    (tmp_path / "index.html").write_text("the old page", encoding="utf-8")
    assert cli.main(["render", str(tmp_path)]) == 2
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == "the old page"


def test_figure_paths_with_encoded_dots_or_hidden_schemes_are_refused() -> None:
    assert safe_src("figures/%2e%2e/%2e%2e/secret.png") == "" and safe_src("java\tscript:alert(1)") == ""
    assert safe_src("figures/fig-1.png") == "figures/fig-1.png" and safe_src("figures/a%20b.png") == "figures/a%20b.png"


def test_new_does_not_overwrite_someone_elses_figure_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeArxiv()
    monkeypatch.setattr(cli, "Client", lambda: Client(get=fake, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-1.png").write_bytes(b"mine")
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path)]) == 2
    assert (tmp_path / "figures" / "fig-1.png").read_bytes() == b"mine"


def test_plain_tar_sources_are_still_read() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo("main.tex")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"abc"))
    assert read_source(buf.getvalue()) == {"main.tex": b"abc"}


def test_latex_209_sources_are_read() -> None:
    old = gzip.compress(rb"\documentstyle[12pt]{article}\begin{document}\title{Old}\end{document}")
    assert list(read_source(old)) == ["main.tex"] and main_file(read_source(old)) == "main.tex"


def test_a_source_without_figures_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeArxiv(src=gzip.compress(rb"\documentclass{article}\begin{document}\includepdf{paper.pdf}\end{document}"))
    monkeypatch.setattr(cli, "Client", lambda: Client(get=fake, sleep=lambda _: None))
    monkeypatch.setattr(cli, "find_converter", lambda: None)
    assert cli.main(["new", "2401.01234", "-o", str(tmp_path / "p")]) == 0
    assert "the source has no figures paper-page can read" in capsys.readouterr().out
