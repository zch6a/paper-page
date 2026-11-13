"""A page from arXiv's metadata (and, for figures, its source), or from a local TeX project before it is on arXiv:
links found in the abstract and the comment (code, video, project page), the venue when the comment names one, a
BibTeX entry, the teaser and figures with their captions."""

from __future__ import annotations

import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .arxiv import ARXIV, ATOM
from .convert import Converter
from .model import Author, Figure, Link, Page
from .tex import WEB_IMAGES, all_args, command_arg, drop_commands, expand, figures, find_images, graphicspath, macros, main_file, to_text, use_macros

URL = re.compile(r"https?://[^\s<>\"'{}\\]+")


def from_entry(entry: ET.Element, arxiv_id: str) -> Page:
    """The page arXiv's Atom entry gives (no figures yet)."""
    eid = (entry.findtext(f"{ATOM}id") or "").strip()
    version = m.group(1) if (m := re.search(r"(v\d+)$", eid)) else ""
    title = to_text(" ".join((entry.findtext(f"{ATOM}title") or "").split()))
    abstract_tex = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
    comment = " ".join((entry.findtext(f"{ARXIV}comment") or "").split())
    authors = []
    for a in entry.findall(f"{ATOM}author"):
        name = " ".join((a.findtext(f"{ATOM}name") or "").split())
        if name:
            affiliations = [" ".join((x.text or "").split()) for x in a.findall(f"{ARXIV}affiliation") if (x.text or "").strip()]
            authors.append(Author(name, "", "; ".join(affiliations)))
    published = (entry.findtext(f"{ATOM}published") or "")[:10]
    primary = entry.find(f"{ARXIV}primary_category")
    categories = [c.get("term", "") for c in entry.findall(f"{ATOM}category") if c.get("term")]
    if primary is not None and primary.get("term") in categories:
        categories.remove(primary.get("term", ""))
        categories.insert(0, primary.get("term", ""))
    doi = (entry.findtext(f"{ARXIV}doi") or "").strip()
    links = [Link("arXiv", f"https://arxiv.org/abs/{arxiv_id}"), Link("PDF", f"https://arxiv.org/pdf/{arxiv_id}")]
    for x in found_links(comment) + found_links(abstract_tex):  # the comment's first; one link of each kind
        if x.label not in {y.label for y in links}:
            links.append(x)
    if doi:
        links.insert(1, Link("DOI", f"https://doi.org/{doi}"))
    page = Page(
        title=title,
        authors=authors,
        abstract=to_text(abstract_tex),
        arxiv=arxiv_id,
        version=version,
        published=published,
        venue=venue_of(comment),
        links=links,
        doi=doi,
        categories=categories,
    )
    page.bibtex = bibtex(page)
    return page


def found_links(text: str) -> list[Link]:
    """Links named in an abstract or a comment, labelled by the word just before them ("code at ...") or else by where
    they go (the first of each kind, in order).

    >>> [(x.label, x.url) for x in found_links("Code: https://github.com/a/b. Video at https://youtu.be/x; see http://tancik.com/nerf")]
    [('Code', 'https://github.com/a/b'), ('Video', 'https://youtu.be/x'), ('Project page', 'http://tancik.com/nerf')]
    >>> [(x.label, x.url) for x in found_links("Our code is released at https://lab.example.org/tiny and data at https://example.org/d")]
    [('Code', 'https://lab.example.org/tiny'), ('Data', 'https://example.org/d')]
    >>> [x.label for x in found_links("Code and data are available at https://github.com/a/b")]
    ['Code']
    """
    out: list[Link] = []
    seen: set[str] = set()
    for m in URL.finditer(text):
        url = m.group(0).rstrip(".,;:)]")
        if url.count("(") < url.count(")"):
            url = url.rstrip(")")
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
        if host.endswith("arxiv.org") or url in seen:
            continue
        said = _said(re.split(r"[.;!?](?:\s|$)", text[max(0, m.start() - 60) : m.start()])[-1])  # within its own sentence
        by_host = _by_host(host, url)
        if by_host:
            label = by_host  # github.com is code whatever the sentence says ("code and data are at ...")
        elif said:
            label = said
        elif host in ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org"):
            label = "Code"
        elif host in ("youtube.com", "youtu.be", "vimeo.com", "m.youtube.com"):
            label = "Video"
        elif host == "huggingface.co":
            label = "Data" if "/datasets/" in url else "Demo" if "/spaces/" in url else "Model"
        elif host.endswith(("zenodo.org", "kaggle.com")):
            label = "Data"
        else:
            label = "Project page"
        if label in {x.label for x in out}:
            continue
        seen.add(url)
        out.append(Link(label, url))
    return out


def _by_host(host: str, url: str) -> str:
    """The kind of link a host says plainly, or ""."""
    if host in ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org"):
        return "Code"
    if host in ("youtube.com", "youtu.be", "vimeo.com", "m.youtube.com"):
        return "Video"
    if host == "huggingface.co" and "/datasets/" in url:
        return "Data"
    if host.endswith(("zenodo.org", "kaggle.com")):
        return "Data"
    return ""


SAID = {"code": "Code", "implementation": "Code", "source": "Code", "video": "Video", "videos": "Video", "data": "Data",
        "dataset": "Data", "datasets": "Data", "demo": "Demo"}  # fmt: skip
PAGE_WORDS = {"project", "website", "homepage", "webpage"}


def _said(before: str) -> str:
    """The kind of link the words just before it name: a project page first ("Project page with videos and code: ..."
    is one page holding both), else the nearest keyword ("our code is at ..."), else "".

    >>> [x.label for x in found_links("on several established datasets. https://repo.example.org/gs/")]
    ['Project page']
    >>> _said("Project page with videos and code: "), _said("Our code is released at "), _said("as shown in ")
    ('Project page', 'Code', '')
    """
    words = re.findall(r"[a-z]+", before.lower())[-6:]
    if PAGE_WORDS & set(words):
        return "Project page"
    return next((SAID[w] for w in reversed(words) if w in SAID), "")


# a venue's name has capitals inside it (NeurIPS, CVPR, ECCV, ICML-W): matched case-sensitively; the words around it not
NAME = r"(?:[A-Z][A-Za-z]*[A-Z][A-Za-z]*|[A-Z]{2,})(?:[- ][A-Z][A-Za-z]+)?"
KIND = r"(?:\s*\((?i:oral|spotlight|poster|highlight|best paper[^)]*)\))?"
VENUE_START = re.compile(rf"^\s*(?i:accepted\s+(?:at|to|by|for|in)\s+(?:the\s+)?)?({NAME}\s?(?:19|20)\d{{2}}\b{KIND})")
VENUE_ANY = re.compile(
    rf"\b(?i:accepted|to appear|published|presented)\b[^.;]{{0,40}}?\b(?i:at|in|to|by|for)\s+(?:(?i:the)\s+)?({NAME}\s?(?:19|20)\d{{2}}\b{KIND})"
)


def venue_of(comment: str) -> str:
    """The venue an arXiv comment names, when it does plainly ("ECCV 2020 (oral). ...", "Accepted to ICLR 2024");
    "" otherwise (page counts and the like are not venues).

    >>> venue_of("ECCV 2020 (oral). Project page with videos and code: http://tancik.com/nerf")
    'ECCV 2020 (oral)'
    >>> venue_of("15 pages, 5 figures. Accepted to NeurIPS 2023"), venue_of("12 pages, 3 figures"), venue_of("v2: typos fixed")
    ('NeurIPS 2023', '', '')
    >>> venue_of("NeurIPS 2023 submission"), venue_of("Accepted at the ICML 2023 Workshop on X"), venue_of("Submitted to CVPR 2024")
    ('', '', '')
    """
    for pattern in (VENUE_START, VENUE_ANY):
        m = pattern.search(comment)
        if m and re.search(r"(?:19|20)\d{2}", m.group(1)) and not re.match(r"(?i)(pages?|figures?|tables?|v\d)", m.group(1)):
            after, before = comment[m.end(1) : m.end(1) + 40].lower(), comment[max(0, m.start(1) - 40) : m.start(1)].lower()
            if re.match(
                r"\W*(?:[a-z]+\W+){0,4}?(workshops?|submission|track|tutorial|competition|challenge|demo|findings|doctoral)\b", after
            ) or re.search(r"\b(submitted|submission|under review|workshops?|findings|rejected)\b", before):
                return ""  # a submission, a workshop or a track is not the conference: never guessed
            return " ".join(m.group(1).split())
    return ""


def bibtex(page: Page) -> str:
    r"""A BibTeX entry for the page's paper (arXiv's fields: eprint, archivePrefix, primaryClass), the title's case kept.

    >>> print(bibtex(Page("NeRF: Representing Scenes", [Author("Ben Mildenhall"), Author("Ren Ng")], arxiv="2003.08934",
    ...                   published="2020-03-19", categories=["cs.CV"])))
    @misc{mildenhall2020nerf,
      title         = {{NeRF: Representing Scenes}},
      author        = {Mildenhall, Ben and Ng, Ren},
      year          = {2020},
      eprint        = {2003.08934},
      archivePrefix = {arXiv},
      primaryClass  = {cs.CV},
      url           = {https://arxiv.org/abs/2003.08934},
    }
    """
    year = page.published[:4]
    first = _last(page.authors[0].name) if page.authors else "anon"
    words = [
        w
        for w in re.findall(r"[A-Za-z0-9]+", _ascii(page.title))
        if w.lower() not in {"a", "an", "the", "on", "of", "for", "to", "in", "and", "with"}
    ]
    key = f"{_ascii(first).lower()}{year}{(words[0].lower() if words else '')}"
    key = re.sub(r"[^a-z0-9]", "", key) or "paper"
    fields = [("title", "{" + _bib(page.title) + "}"), ("author", " and ".join(_bib(_last_first(a.name)) for a in page.authors)), ("year", year)]
    if page.venue:
        fields.append(("note", _bib(page.venue)))
    if page.arxiv:
        fields += [("eprint", page.arxiv), ("archivePrefix", "arXiv")]
        if page.categories:
            fields.append(("primaryClass", page.categories[0]))
        fields.append(("url", f"https://arxiv.org/abs/{page.arxiv}"))
    if page.doi:
        fields.append(("doi", page.doi))
    body = "".join(f"  {k:<13} = {{{v}}},\n" for k, v in fields if v)
    return f"@misc{{{key},\n{body}}}"


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _bib(s: str) -> str:
    r"""Text as a BibTeX value: braces and backslashes dropped, LaTeX's special characters escaped.

    >>> _bib("Fast C# code_gen for 100$ & 50% with ~ and ^")
    'Fast C\\# code\\_gen for 100\\$ \\& 50\\% with \\textasciitilde{} and \\textasciicircum{}'
    """
    s = s.replace("\\", "").replace("{", "").replace("}", "")
    for c in "&%#_$":
        s = s.replace(c, "\\" + c)
    return s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")


SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def _split_name(name: str) -> tuple[str, str, str]:
    """(first names, last name, suffix): "Ada Example Jr." is ("Ada", "Example", "Jr.")."""
    parts = name.split()
    suffix = parts.pop() if len(parts) > 2 and parts[-1].lower().rstrip(",") in SUFFIXES else ""
    parts[-1] = parts[-1].rstrip(",")
    return " ".join(parts[:-1]), parts[-1], suffix.rstrip(",")


def _last(name: str) -> str:
    return _split_name(name)[1]


def _last_first(name: str) -> str:
    """BibTeX's "Last, Jr., First" form.

    >>> _last_first("Ada Example"), _last_first("Ada Example Jr."), _last_first("Plato")
    ('Example, Ada', 'Example, Jr., Ada', 'Plato')
    """
    if len(name.split()) < 2:
        return name
    first, last, suffix = _split_name(name)
    return f"{last}, {suffix}, {first}" if suffix else f"{last}, {first}"


# --- figures and local TeX ---


@dataclass
class Figures:
    teaser: Figure | None = None
    figures: list[Figure] = field(default_factory=list)
    images: dict[str, bytes] = field(default_factory=dict)  # path in the page folder -> the image
    skipped: list[str] = field(default_factory=list)  # figures not in a web format (PDF, EPS): to convert by hand
    teaser_skipped: str = ""  # the paper's first figure, when it is one of those: the page then has no teaser
    converted: list[str] = field(default_factory=list)  # PDF figures converted to PNG
    missing: list[str] = field(default_factory=list)  # images a figure includes that are not in the source (a .tif, say)


def take_figures(files: dict[str, bytes], limit: int, main: str | None = None, convert: Converter | None = None) -> Figures:
    """Up to `limit` figures of a source, copied as figures/fig-N.ext when a browser shows them as they are (PNG,
    JPEG, GIF, WebP, SVG), PDF figures converted to PNG with `convert` when given; the others listed as skipped. The
    paper's first figure is the teaser, and only it: when it cannot be shown, the page has no teaser rather than a
    later figure in its place."""
    out = Figures()
    main = main or main_file(files)
    if main is None or limit <= 0:
        return out
    tex = expand(main, files)
    gp = graphicspath(tex)
    own = macros(tex)
    n = 0
    for i, f in enumerate(figures(tex)):  # i counts every figure: the teaser is the first, found or not
        if n >= limit:
            break
        candidates = find_images(f.image, files, main, gp)
        if not candidates:
            out.missing.append(f.image)
            if i == 0:
                out.teaser_skipped = f.image
            continue
        found, data, ext = _usable(candidates, files, convert, out)
        if data is None:
            out.skipped.append(found)
            if i == 0:
                out.teaser_skipped = found
            continue
        n += 1
        src = f"figures/fig-{n}{'.jpg' if ext == '.jpeg' else ext}"
        caption = to_text(use_macros(f.caption, own))
        figure = Figure(src, caption, alt=caption[:150])
        out.images[src] = data
        if i == 0:
            out.teaser = figure
        else:
            out.figures.append(figure)
    return out


def _usable(candidates: list[str], files: dict[str, bytes], convert: Converter | None, out: Figures) -> tuple[str, bytes | None, str]:
    """The first candidate a browser can show: a web image as it is, a PDF converted; (the first candidate, None, "")
    when there is none."""
    for found in candidates:
        ext = posixpath.splitext(found)[1].lower()
        if ext in WEB_IMAGES:
            return found, files[found], ext
        if ext == ".pdf" and convert is not None:
            data = convert(files[found])
            if data is not None and data[:8] == b"\x89PNG\r\n\x1a\n":
                out.converted.append(found)
                return found, data, ".png"
            if data is not None and data[:3] == b"\xff\xd8\xff":
                out.converted.append(found)
                return found, data, ".jpg"
    return candidates[0], None, ""


def from_tex(files: dict[str, bytes], main: str | None = None) -> Page:
    r"""A page from a TeX project (a paper not on arXiv yet): \title, \author (names split at \and, commas and line
    breaks; \thanks and footnote marks dropped), the abstract."""
    main = main or main_file(files)
    if main is None:
        raise ValueError("no main TeX file (one with \\documentclass and \\begin{document})")
    tex = expand(main, files)
    own = macros(tex)
    raw_title = command_arg(tex, "title") or command_arg(tex, "icmltitle") or ""  # ICML has its own command
    title = to_text(use_macros(drop_commands(raw_title, ("thanks", "footnote")), own))
    if not title:
        raise ValueError(f"{main}: no \\title")
    icml = all_args(tex, "icmlauthor")
    blocks = all_args(tex, "author")
    if icml:  # \icmlauthor{Name}{affiliation key}: one per author
        names = [to_text(use_macros(n, own)) for n in icml]
    else:  # acmart and others give each author an \author of their own: the first name of each; else one block of all
        names = (
            [n for b in blocks for n in author_names(use_macros(b, own))[:1]]
            if len(blocks) > 1
            else author_names(use_macros(blocks[0] if blocks else "", own))
        )
    authors = [Author(n) for n in names if n]
    abstract = ""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, flags=re.S)
    if m:
        abstract = to_text(use_macros(m.group(1), own))
    page = Page(title=title, authors=authors, abstract=abstract, links=found_links(m.group(1)) if m else [])
    page.bibtex = bibtex(page)
    return page


def author_names(block: str) -> list[str]:
    r"""The names in an \author block: the first line of each \and part, or a list separated by commas.

    >>> author_names(r"Ada Example\thanks{Equal.} \\ Univ. A \and Bo Sample$^{1}$ \\ Univ. B")
    ['Ada Example', 'Bo Sample']
    >>> author_names(r"Ada Example, Bo Sample and Cy Test")
    ['Ada Example', 'Bo Sample', 'Cy Test']
    >>> author_names(r"Ada Example\inst{1} \and Bo Sample\inst{2}")
    ['Ada Example', 'Bo Sample']
    """
    block = drop_commands(
        block, ("thanks", "footnote", "footnotemark", "affiliation", "email", "orcid", "orcidlink", "inst", "IEEEauthorrefmark", "affil")
    )
    block = re.sub(r"\$[^$]*\$|\\textsuperscript\{[^{}]*\}|\\footnotemark(\[[^\]]*\])?", "", block)
    parts = re.split(r"\\and\b", block, flags=re.I)  # \and, \And (NeurIPS), \AND
    names: list[str] = []
    for part in parts:
        first = re.split(r"\\\\|\\newline", part)[0]
        for n in re.split(r",|\band\b", to_text(first)) if len(parts) == 1 else [to_text(first)]:
            n = " ".join(n.replace("*", "").split()).strip(" ,")
            if n and len(n.split()) <= 6 and not re.search(r"@|\d", n):
                names.append(n)
    return names
