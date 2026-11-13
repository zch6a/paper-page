# Contributing

```bash
uv sync
uv run pytest -q          # tests never touch the network: arXiv is a fake, and the real opener fails if called
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Where things are

| Module | What it does |
| --- | --- |
| `arxiv.py` | IDs and links parsed; the client (one request every three seconds, retries); the Atom entry |
| `tex.py` | TeX as text (simple math in Unicode); the source read in memory; the main file, `\input`, figures and captions |
| `make.py` | a page from arXiv's entry (links, venue, BibTeX), figures from the source, a page from a local TeX project |
| `model.py` | `page.json`: the page as data, checked field by field when read |
| `render.py` | `page.json` to `index.html`: escaping, safe links, the Scholar and Open Graph tags, the style |
| `cli.py` | `paper-page new`, `paper-page render` |

The example in `examples/tiny-fields` is a made-up paper; a test checks that its `index.html` is what `render` makes
now. After changing the page's markup or style, run `paper-page render examples/tiny-fields` and, for the README,
`scripts/screenshots.ps1`'s commands (headless Chrome).

## Rules the project keeps

- arXiv's public API and e-print links only, at the pace arXiv asks.
- Tests use made-up papers, never a real paper's text or figures, and never the network.
- Pages made while trying the tool on real papers stay out of the repository (`/page/`, `/trial/` are ignored).
