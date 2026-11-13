---
name: paper-page
description: Make a project page for a research paper with paper-page, from its arXiv ID (or a local TeX project before it is on arXiv): title, authors, venue, buttons for arXiv/PDF/code/video/data, the teaser figure, the abstract and a BibTeX block, with Google Scholar citation_* tags and Open Graph tags, as one static HTML file for GitHub Pages. Use when the user wants a project page, paper website or landing page for their paper, or to publish one on GitHub Pages.
license: MIT
compatibility: Needs Python 3.10+ and uv. Runs paper-page with uvx from GitHub (git+https://github.com/zch6a/paper-page) unless installed. Reaches only arXiv (export.arxiv.org and arxiv.org/e-print).
metadata:
  homepage: https://github.com/zch6a/paper-page
---

# A project page with paper-page

```bash
uvx --from git+https://github.com/zch6a/paper-page paper-page new <arXiv ID or link> -o page/
uvx --from git+https://github.com/zch6a/paper-page paper-page new --tex paper/main.tex -o page/   # not on arXiv yet
uvx --from git+https://github.com/zch6a/paper-page paper-page render page/                        # after editing page.json
```

- `new` writes `page/page.json` (everything on the page) and `page/index.html`, and copies the teaser and figures
  (web formats only) into `page/figures/`. Read its report back to the user: the venue it found (or that none was
  named), the links, the figures taken and any skipped.
- **Ask the user for what arXiv does not have** and put it in `page.json`, then `render`: author homepages and
  affiliations, code/video/data links not in the abstract, the venue, `site_url` (where the page will live; needed
  for the teaser in link previews). Never invent a link, an affiliation or a venue.
- A figure reported as a PDF (often the teaser) must be converted to PNG to show; with poppler installed:
  `pdftoppm -png -r 200 -singlefile fig.pdf page/figures/teaser`, then set `teaser.src` to `figures/teaser.png`.
- `new` refuses to overwrite an existing `page.json` (the user's edits are in it); use `--force` only when the user
  wants to start over.
- To publish: write the page to `docs/` and use Settings → Pages → Deploy from a branch (main, /docs), or the README's
  workflow for a `page/` folder. Pushing and changing repository settings are the user's to approve.
