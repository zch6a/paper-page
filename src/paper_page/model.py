"""The page as data: what page.json holds. `paper-page new` writes it from arXiv; the author edits it (links, author
homepages and affiliations, the venue, figures); `paper-page render` makes the HTML from it."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COLOR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass
class Author:
    name: str
    url: str = ""  # a homepage
    affiliation: str = ""  # one or several, separated by "; "


@dataclass
class Link:
    label: str  # Paper, PDF, Code, Video, Data, ... (any text)
    url: str


@dataclass
class Figure:
    src: str  # a path inside the page's folder (figures/teaser.png) or an https URL
    caption: str = ""
    alt: str = ""


@dataclass
class Page:
    title: str
    authors: list[Author] = field(default_factory=list)
    abstract: str = ""
    arxiv: str = ""  # the arXiv ID without its version: 2003.08934
    version: str = ""  # the version the page was made from: v2
    published: str = ""  # YYYY-MM-DD, the first version's date
    venue: str = ""  # "ECCV 2020 (oral)": found in arXiv's comment when it says so, else to fill in
    links: list[Link] = field(default_factory=list)
    teaser: Figure | None = None
    figures: list[Figure] = field(default_factory=list)
    bibtex: str = ""
    doi: str = ""
    categories: list[str] = field(default_factory=list)
    site_url: str = ""  # where the page will live (https://you.github.io/paper/): makes link previews show the teaser
    accent: str = "#2f6fdf"  # the color of the links and buttons

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str, where: str = "page.json") -> Page:
        """A page from page.json, checked: a wrong type is an error naming the field, not a broken page."""
        try:
            d = json.loads(text)
        except ValueError as e:
            raise ValueError(f"{where}: not JSON ({e})") from e
        if not isinstance(d, dict):
            raise ValueError(f'{where}: an object of fields, e.g. {{"title": ...}}')
        unknown = sorted(set(d) - set(cls.__dataclass_fields__))
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {', '.join(unknown)} (fields: {', '.join(cls.__dataclass_fields__)})")

        def text_of(key: str, value: Any = None) -> str:
            v = d.get(key, "") if value is None else value
            if not isinstance(v, str):
                raise ValueError(f"{where}: {key} is text")
            return v

        def items(key: str) -> list[dict[str, Any]]:
            v = d.get(key) or []
            if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
                raise ValueError(f"{where}: {key} is a list of objects")
            return v

        def figure(x: Any, key: str) -> Figure:
            if not isinstance(x, dict) or not isinstance(x.get("src"), str) or not x["src"]:
                raise ValueError(f"{where}: {key} needs a src (a path in the page's folder, or an https URL)")
            return Figure(x["src"], text_of(f"{key}.caption", x.get("caption", "")), text_of(f"{key}.alt", x.get("alt", "")))

        title = text_of("title").strip()
        if not title:
            raise ValueError(f"{where}: the title is empty")
        authors = []
        for i, a in enumerate(items("authors")):
            if not isinstance(a.get("name"), str) or not a["name"].strip():
                raise ValueError(f"{where}: author {i + 1} has no name")
            authors.append(
                Author(a["name"].strip(), text_of("authors.url", a.get("url", "")), text_of("authors.affiliation", a.get("affiliation", "")))
            )
        links = []
        for i, x in enumerate(items("links")):
            if not isinstance(x.get("label"), str) or not isinstance(x.get("url"), str) or not x["label"] or not x["url"]:
                raise ValueError(f"{where}: link {i + 1} needs a label and a url")
            links.append(Link(x["label"], x["url"]))
        accent = text_of("accent") or "#2f6fdf"
        if not COLOR.fullmatch(accent):
            raise ValueError(f"{where}: accent is a color like #2f6fdf, not {accent!r}")
        categories = d.get("categories") or []
        if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
            raise ValueError(f"{where}: categories is a list of texts")
        teaser = d.get("teaser")
        return cls(
            title=title,
            authors=authors,
            abstract=text_of("abstract"),
            arxiv=text_of("arxiv"),
            version=text_of("version"),
            published=text_of("published"),
            venue=text_of("venue"),
            links=links,
            teaser=figure(teaser, "teaser") if teaser else None,
            figures=[figure(x, f"figures[{i}]") for i, x in enumerate(items("figures"))],
            bibtex=text_of("bibtex"),
            doi=text_of("doi"),
            categories=categories,
            site_url=text_of("site_url"),
            accent=accent,
        )

    @classmethod
    def read(cls, path: Path) -> Page:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise ValueError(f"{path.as_posix()}: cannot be read ({e.strerror or e})") from e
        return cls.from_json(text, path.as_posix())
