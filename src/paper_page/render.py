"""page.json to index.html: one self-contained file (no fonts, scripts or styles fetched from elsewhere; one small
script for the copy button), light and dark, readable on a phone. Every text is HTML-escaped; links must be http(s)
and figures a path inside the page's folder or an https URL, anything else is left out and reported. The head carries
the meta tags Google Scholar indexes (citation_*) and the Open Graph tags link previews read."""

from __future__ import annotations

import datetime as dt
import html
import posixpath
import re
import urllib.parse

from . import __version__
from .model import Figure, Page

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

ICONS = {  # 16x16 line icons, drawn for this page
    "paper": '<path d="M4 1.5h5.5L13 5v9.5H4z"/><path d="M9.5 1.5V5H13"/><path d="M6 8h5M6 10.5h5"/>',
    "code": '<path d="M5.5 4 1.5 8l4 4M10.5 4l4 4-4 4"/>',
    "video": '<rect x="1.5" y="3" width="13" height="10" rx="2"/><path d="M6.5 5.8v4.4L10.2 8z"/>',
    "data": '<ellipse cx="8" cy="3.5" rx="5.5" ry="2"/><path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"/>',
    "web": '<circle cx="8" cy="8" r="6.5"/><path d="M1.5 8h13M8 1.5c2 2 2.8 4.2 2.8 6.5S10 12.5 8 14.5C6 12.5 5.2 10.3 5.2 8S6 3.5 8 1.5"/>',
    "spark": '<path d="M8 1.5 9.6 6.4 14.5 8l-4.9 1.6L8 14.5 6.4 9.6 1.5 8l4.9-1.6z"/>',
    "link": '<path d="M6.5 9.5 9.5 6.5M7 4.5l1.3-1.3a3 3 0 0 1 4.5 4.5L11.5 9M9 11.5l-1.3 1.3a3 3 0 0 1-4.5-4.5L4.5 7"/>',
}
KINDS = {"arxiv": "paper", "pdf": "paper", "paper": "paper", "doi": "paper", "code": "code", "github": "code", "video": "video",
         "youtube": "video", "data": "data", "dataset": "data", "project page": "web", "website": "web", "demo": "spark", "model": "spark"}  # fmt: skip


def safe_url(url: str) -> str:
    """The URL when it is http(s), else "" (no javascript:, data: or file: links)."""
    return url if re.match(r"^https?://[^\s<>\"]+$", url.strip(), flags=re.I) else ""


def safe_src(src: str) -> str:
    """A figure's src when it is a path inside the page's folder or an https URL, else ""."""
    s = src.strip()
    if re.search(r"[\x00-\x20\x7f]", s):
        return ""  # a tab or newline inside could hide a scheme ("java\tscript:") from the check
    if re.match(r"^https://[^\s<>\"]+$", s, flags=re.I):
        return s
    plain = urllib.parse.unquote(s).replace("\\", "/")  # %2e%2e is .. to a browser
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", plain) or plain.startswith("/") or not s:
        return ""
    norm = posixpath.normpath(plain)
    return "" if norm == ".." or norm.startswith("../") or "/../" in f"/{norm}/" else posixpath.normpath(s.replace("\\", "/"))


def _icon(label: str) -> str:
    kind = KINDS.get(label.strip().lower(), "link")
    return f'<svg viewBox="0 0 16 16" aria-hidden="true">{ICONS[kind]}</svg>'


def _date(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return ""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _rgba(color: str, alpha: float) -> str:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def render(page: Page) -> tuple[str, list[str]]:
    """The page's HTML, and what was left out (unsafe links, figures with no usable src)."""
    e = html.escape
    warnings: list[str] = []

    # authors, with affiliations numbered in order of appearance
    affiliations: list[str] = []
    for a in page.authors:
        for aff in (x.strip() for x in a.affiliation.split(";")):
            if aff and aff not in affiliations:
                affiliations.append(aff)
    many = len(affiliations) > 1
    names = []
    for a in page.authors:
        marks = [str(affiliations.index(x.strip()) + 1) for x in a.affiliation.split(";") if x.strip()] if many else []
        url = safe_url(a.url)
        if a.url and not url:
            warnings.append(f"author {a.name}: url {a.url!r} is not an http(s) link: left out")
        name = f'<a href="{e(url)}">{e(a.name)}</a>' if url else e(a.name)
        names.append(f'<span class="author">{name}{"<sup>" + ",".join(marks) + "</sup>" if marks else ""}</span>')
    affs = "".join(f"<span>{'<sup>' + str(i + 1) + '</sup>' if many else ''}{e(x)}</span>" for i, x in enumerate(affiliations))

    buttons = []
    for link in page.links:
        url = safe_url(link.url)
        if not url:
            warnings.append(f"link {link.label}: {link.url!r} is not an http(s) link: left out")
            continue
        buttons.append(f'<a class="button" href="{e(url)}">{_icon(link.label)}<span>{e(link.label)}</span></a>')

    def figure(f: Figure, eager: bool) -> str:
        src = safe_src(f.src)
        if not src:
            warnings.append(f"figure {f.src!r}: not a path inside the page's folder or an https URL: left out")
            return ""
        loading = "" if eager else ' loading="lazy"'
        caption = f"<figcaption>{e(f.caption)}</figcaption>" if f.caption else ""
        return f'<figure><img src="{e(src)}" alt="{e(f.alt or f.caption[:150])}"{loading}>{caption}</figure>'

    teaser = figure(page.teaser, True) if page.teaser else ""
    more = "".join(figure(f, False) for f in page.figures)

    site = safe_url(page.site_url)
    if page.site_url and not site:
        warnings.append(f"site_url {page.site_url!r} is not an http(s) link: left out")
    base = site if site.endswith("/") or not site else site + "/"
    teaser_src = safe_src(page.teaser.src) if page.teaser else ""
    og_image = teaser_src if teaser_src.startswith("https://") else (base + teaser_src if base and teaser_src else "")
    if og_image.lower().endswith(".svg"):
        warnings.append("the teaser is an SVG: link previews (social sites, chat apps) do not show SVG images; a PNG or JPEG of it shows")
    description = page.abstract[:297] + "…" if len(page.abstract) > 300 else page.abstract

    meta = [f'<meta name="description" content="{e(description)}">', f'<meta name="citation_title" content="{e(page.title)}">']
    meta += [f'<meta name="citation_author" content="{e(a.name)}">' for a in page.authors]
    if page.published:
        meta.append(f'<meta name="citation_publication_date" content="{e(page.published.replace("-", "/"))}">')
    if page.arxiv:
        meta += [
            f'<meta name="citation_arxiv_id" content="{e(page.arxiv)}">',
            f'<meta name="citation_pdf_url" content="https://arxiv.org/pdf/{e(page.arxiv)}">',
        ]
    if page.doi:
        meta.append(f'<meta name="citation_doi" content="{e(page.doi)}">')
    meta += ['<meta property="og:type" content="article">', f'<meta property="og:title" content="{e(page.title)}">',
             f'<meta property="og:description" content="{e(description)}">']  # fmt: skip
    if base:
        meta += [f'<link rel="canonical" href="{e(base)}">', f'<meta property="og:url" content="{e(base)}">']
    if og_image:
        meta += [f'<meta property="og:image" content="{e(og_image)}">', '<meta name="twitter:card" content="summary_large_image">']

    posted = _date(page.published)
    byline = []
    if page.arxiv:
        byline.append(f"arXiv:{e(page.arxiv)}{e(page.version)}" + (f" · posted {posted}" if posted else ""))
    elif posted:
        byline.append(posted)

    sections = []
    if teaser:
        sections.append(f'<section class="teaser">{teaser}</section>')
    if page.abstract:
        sections.append(f'<section><h2>Abstract</h2><p class="abstract">{e(page.abstract)}</p></section>')
    if more:
        sections.append(f'<section class="figures"><h2>Figures</h2>{more}</section>')
    if page.bibtex.strip():
        sections.append(
            '<section><h2>Citation</h2><div class="cite"><button type="button" id="copy">Copy</button>'
            f'<pre id="bibtex">{e(page.bibtex.strip())}</pre></div></section>'
        )

    accent = page.accent
    out = PAGE.format(
        title=e(page.title),
        meta="\n".join(meta),
        accent=accent,
        tint=_rgba(accent, 0.10),
        tint_dark=_rgba(accent, 0.22),
        venue=f'<p class="venue">{e(page.venue)}</p>' if page.venue.strip() else "",
        authors=", ".join(names) if names else "",
        affiliations=f'<p class="affiliations">{affs}</p>' if affs else "",
        buttons=f'<nav class="buttons">{"".join(buttons)}</nav>' if buttons else "",
        byline=f'<p class="byline">{"".join(byline)}</p>' if byline else "",
        sections="\n".join(sections),
        version=__version__,
    )
    return out, warnings


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{meta}
<meta name="generator" content="paper-page {version}">
<style>
:root{{--bg:#fff;--fg:#1d2127;--muted:#5d6672;--line:#dfe3e8;--card:#f6f8fa;--accent:{accent};--tint:{tint}}}
@media (prefers-color-scheme:dark){{:root{{--bg:#101318;--fg:#e8ebef;--muted:#9aa3ad;--line:#2b313a;--card:#171b21;--tint:{tint_dark}}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:17px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}}
header{{background:linear-gradient(180deg,var(--tint),transparent);padding:56px 20px 28px;text-align:center}}
.inner{{max-width:880px;margin:0 auto}}
.venue{{display:inline-block;margin:0 0 14px;padding:3px 12px;border:1px solid var(--accent);border-radius:999px;color:var(--accent);font-size:14px;font-weight:600;letter-spacing:.02em}}
h1{{font-size:clamp(28px,4.4vw,42px);line-height:1.18;margin:0 0 18px;letter-spacing:-.01em}}
.authors{{font-size:18px;margin:0 0 6px}}.author{{white-space:nowrap}}
.authors a{{color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line)}}.authors a:hover{{color:var(--accent);border-color:var(--accent)}}
sup{{font-size:.65em;color:var(--muted);margin-left:1px}}
.affiliations{{color:var(--muted);font-size:15px;margin:0 0 4px}}.affiliations span{{margin:0 9px;display:inline-block}}
.byline{{color:var(--muted);font-size:14px;margin:6px 0 0}}
.buttons{{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin:22px 0 0}}
.button{{display:inline-flex;align-items:center;gap:7px;padding:8px 16px;border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--fg);text-decoration:none;font-size:15px;font-weight:600}}
.button:hover{{border-color:var(--accent);color:var(--accent)}}.button:first-child{{background:var(--accent);border-color:var(--accent);color:#fff}}
.button svg{{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}}
main{{max-width:880px;margin:0 auto;padding:8px 20px 40px}}
section{{margin:34px 0}}
h2{{font-size:22px;margin:0 0 12px}}
.abstract{{margin:0;text-align:justify;hyphens:auto}}
figure{{margin:0 0 26px}}img{{display:block;max-width:100%;max-height:85vh;width:auto;height:auto;margin:0 auto;border-radius:6px}}
figcaption{{color:var(--muted);font-size:15px;margin-top:10px}}
.cite{{position:relative}}
pre{{margin:0;padding:16px;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow-x:auto;font:13.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
#copy{{position:absolute;top:8px;right:8px;font:inherit;font-size:13px;padding:3px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}}
footer{{max-width:880px;margin:0 auto;padding:18px 20px 40px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
footer a{{color:var(--muted)}}
a{{color:var(--accent)}}
@media (max-width:600px){{body{{font-size:16px}}header{{padding-top:36px}}.abstract{{text-align:left}}.author{{white-space:normal}}}}
</style>
</head>
<body>
<header><div class="inner">
{venue}
<h1>{title}</h1>
<p class="authors">{authors}</p>
{affiliations}
{byline}
{buttons}
</div></header>
<main>
{sections}
</main>
<footer>Made with <a href="https://github.com/zch6a/paper-page">paper-page</a>.</footer>
<script>
"use strict";
const copy = document.getElementById("copy");
if (copy) copy.addEventListener("click", () => {{
  const text = document.getElementById("bibtex").textContent;
  const done = () => {{ copy.textContent = "Copied"; setTimeout(() => {{ copy.textContent = "Copy"; }}, 1500); }};
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => {{}});
}});
</script>
</body>
</html>
"""
