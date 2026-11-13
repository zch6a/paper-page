"""paper-page: a project page for your paper, from its arXiv ID.

paper-page new 2003.08934 -o page/       page.json and index.html from arXiv (the teaser and figures from its source)
paper-page new --tex paper/main.tex      from your TeX project, before the paper is on arXiv
paper-page render page/                  index.html again, after you edit page.json

page.json is yours to edit: author homepages and affiliations, links (code, video, data), the venue, the figures,
site_url (where the page will live: link previews then show the teaser). Publish the folder on GitHub Pages.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from . import __version__
from .arxiv import ArxivError, Client, parse_id
from .convert import find_converter
from .make import Figures, from_entry, from_tex, take_figures
from .model import Page
from .render import render
from .tex import SourceTooLarge, read_source

MAX_LOCAL_FILES = 5000
MAX_LOCAL_BYTES = 250 * 2**20  # read from a --tex project at most (a paper's figures are a few dozen MB)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="paper-page", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="exit status: 0 done, 2 an error")  # fmt: skip
    ap.add_argument("--version", action="version", version=f"paper-page {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    n = sub.add_parser("new", help="make page.json and index.html from an arXiv ID (or a TeX project)")
    n.add_argument("arxiv", nargs="?", help="an arXiv ID or link: 2003.08934, arXiv:2003.08934v2, https://arxiv.org/abs/...")
    n.add_argument("--tex", type=Path, help="the main .tex file of a paper not on arXiv yet (instead of an ID)")
    n.add_argument("-o", "--out", type=Path, default=Path("page"), help="the page's folder (default page/)")
    n.add_argument("--figures", type=int, default=4, metavar="N", help="take the first N figures, the first as the teaser (default 4; 0 for none)")
    n.add_argument("--no-convert", action="store_true", help="leave PDF figures out instead of converting them with pdftoppm (when installed)")
    n.add_argument("--force", action="store_true", help="replace an existing page.json (your edits in it are lost)")
    r = sub.add_parser("render", help="make index.html again from the folder's page.json")
    r.add_argument("folder", type=Path, nargs="?", default=Path("page"), help="the page's folder (default page/)")
    args = ap.parse_args(argv)
    try:
        if args.command == "new":
            return _new(args)
        return _render(args.folder)
    except (ArxivError, ValueError, OSError) as e:
        print(f"paper-page: {e}", file=sys.stderr)
        return 2


def _new(args: argparse.Namespace) -> int:
    if (args.arxiv is None) == (args.tex is None):
        raise ValueError("give an arXiv ID, or --tex with your main .tex file (one of the two)")
    out: Path = args.out
    if (out / "page.json").exists() and not args.force:
        raise ValueError(f"{(out / 'page.json').as_posix()} exists (your edits may be in it): `paper-page render {out.as_posix()}` "
                         "makes the HTML again; --force starts over")  # fmt: skip
    if args.figures < 0:
        raise ValueError("--figures is 0 or more")
    if args.tex is not None:
        files = _local_files(args.tex)
        main_name = next(iter(files))
        page = from_tex(files, main_name)
        source_note = f"from {args.tex.as_posix()}"
    else:
        arxiv_id, version = parse_id(args.arxiv)
        client = Client()
        page = from_entry(client.metadata(arxiv_id, version), arxiv_id)
        files, main_name = {}, None
        if args.figures:
            print(f"paper-page: fetching arXiv:{arxiv_id}{page.version}'s source for its figures (--figures 0 skips this)", file=sys.stderr)
            kind, blob = client.source(arxiv_id, version)
            try:
                files = read_source(blob)
            except SourceTooLarge as e:
                print(f"paper-page: {e}: no figures taken", file=sys.stderr)
                files = {}
            if not files and blob:
                print(f"paper-page: arXiv has no TeX source for {arxiv_id} ({kind or 'unknown type'}): no figures taken", file=sys.stderr)
        source_note = f"from arXiv:{arxiv_id}{page.version}"
    convert = None if args.no_convert else find_converter()
    figs = take_figures(files, args.figures, main_name, convert) if files else Figures()
    page.teaser, page.figures = figs.teaser, figs.figures
    taken = [out / rel for rel in figs.images if (out / rel).exists()]
    if taken and not args.force:
        raise ValueError(f"{taken[0].as_posix()} exists: --force replaces the figures paper-page names (fig-N), or choose another -o")
    out.mkdir(parents=True, exist_ok=True)
    for old in (out / "figures").glob("fig-*.*") if args.force else ():
        if re.fullmatch(r"fig-\d+\.(png|jpg|gif|webp|svg)", old.name):  # only the files paper-page names: yours stay
            old.unlink()
    for rel, data in figs.images.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _write(out / "page.json", page.to_json())
    html, warnings = render(page)
    _write(out / "index.html", html)
    print(f"paper-page: {page.title}")
    print(f"  {len(page.authors)} author(s), {source_note}" + (f"; venue: {page.venue}" if page.venue else "; no venue named (set it in page.json)"))
    found = [x.label for x in page.links if x.label not in ("arXiv", "PDF", "DOI")]
    print("  links: " + (", ".join(x.label for x in page.links) or "none") + ("" if found else " (add code, video, data in page.json)"))
    converted = f", {len(figs.converted)} of them converted from PDF with pdftoppm" if figs.converted else ""
    print(f"  figures: {len(figs.images)} taken{converted}" + (f" (teaser: {page.teaser.src})" if page.teaser else ""))
    if figs.teaser_skipped:
        name = figs.teaser_skipped.rsplit("/", 1)[-1]
        why = "could not be converted" if convert is not None and name.lower().endswith(".pdf") else "is not in a web format"
        print(f"  the teaser ({figs.teaser_skipped}) {why}: no teaser on the page; convert it to PNG (e.g. "
              f"`pdftoppm -png -r 200 -singlefile {name} teaser`), put it in {out.as_posix()}/figures/ and set teaser.src in page.json")  # fmt: skip
    for s in figs.skipped:
        if s != figs.teaser_skipped:
            print(f"  figure not in a web format, skipped: {s} (convert it to PNG and add it to page.json)")
    if convert is None and not args.no_convert and any(s.lower().endswith(".pdf") for s in figs.skipped):
        print("  (with poppler's pdftoppm installed, PDF figures are converted for you; MiKTeX includes it)")
    for w in warnings:
        print(f"paper-page: warning: {w}", file=sys.stderr)
    print(f"  -> {(out / 'index.html').as_posix()}; edit {(out / 'page.json').as_posix()}, then `paper-page render {out.as_posix()}`")
    return 0


def _render(folder: Path) -> int:
    page = Page.read(folder / "page.json")
    html, warnings = render(page)
    for f in [page.teaser, *page.figures]:
        if f is not None and not f.src.startswith("https://") and not (folder / f.src).is_file():
            warnings.append(f"figure {f.src} is not in {folder.as_posix()}/")
    _write(folder / "index.html", html)
    for w in warnings:
        print(f"paper-page: warning: {w}", file=sys.stderr)
    print(f"paper-page: {(folder / 'index.html').as_posix()}")
    return 0


def _write(path: Path, text: str) -> None:
    """UTF-8 with LF line ends on every system (the same page.json makes the same file), written whole or not at all:
    the text is encoded first and the file replaced only once the new one is complete."""
    data = text.encode("utf-8")  # a text that cannot be written fails here, before anything is touched
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _local_files(main: Path) -> dict[str, bytes]:
    """The TeX project around `main` (its folder and below), by path relative to that folder."""
    if not main.is_file():
        raise ValueError(f"{main.as_posix()}: no such file")
    root = main.resolve().parent
    files: dict[str, bytes] = {}
    total = 0
    for p in sorted(root.rglob("*")):
        if len(files) >= MAX_LOCAL_FILES or total > MAX_LOCAL_BYTES:
            break
        if p.suffix.lower() not in (".tex", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".eps"):
            continue
        # a link (or a file reached through one) may point anywhere: only the project's own files are read
        if (
            p.is_symlink()
            or not p.is_file()
            or not p.resolve().is_relative_to(root)
            or any(q.is_symlink() for q in p.parents if q != root and root in q.parents)
        ):
            continue
        size = p.stat().st_size
        if size < 25 * 2**20:
            total += size
            files[p.relative_to(root).as_posix()] = p.read_bytes()
    name = main.resolve().relative_to(root).as_posix()
    # the main file the user named comes first, whatever the others are
    return {name: files.pop(name, main.read_bytes()), **files}


if __name__ == "__main__":
    raise SystemExit(main())
