"""The repository's own promises: the example page is what `render` makes now, and its README options exist."""

from __future__ import annotations

import re
from pathlib import Path

from paper_page import cli
from paper_page.model import Page
from paper_page.render import render

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "tiny-fields"


def test_the_example_page_is_current_and_renders_without_warnings() -> None:
    html, warnings = render(Page.read(EXAMPLE / "page.json"))
    assert warnings == []
    assert (EXAMPLE / "index.html").read_text(encoding="utf-8") == html, "run: paper-page render examples/tiny-fields"


def test_the_readme_options_are_the_cli_options() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `(--?[a-z][a-z-]*)", readme, flags=re.M))
    help_text = cli.__doc__ or ""
    assert documented == {"-o", "--figures", "--tex", "--no-convert", "--force"}
    assert "paper-page render" in help_text and "paper-page new" in help_text
