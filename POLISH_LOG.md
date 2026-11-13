# Polish log

### 2026-11-13 — development

**Why it exists**: the usual project page is a copied template repository filled in by hand (names, links, figures,
BibTeX), and the best-known template is no longer maintained. Everything a project page starts from is on arXiv.

**What it does**: `paper-page new <arXiv ID>` reads arXiv's API (title, authors, affiliations when present,
abstract, comment, categories, DOI) and the paper's source (figures and captions), and writes `page.json` (the page
as data, for the author to edit) and `index.html`; `render` makes the HTML again; `new --tex` works from a local TeX
project. The page has the `citation_*` tags Google Scholar reads, Open Graph tags (with `site_url`, the teaser in link
previews), a BibTeX block with a copy button, light and dark, and no outside resources. The design is its own.

**Tried on real papers** (pages kept in the scratchpad, never in the repository: the figures are the authors'):

- NeRF (2003.08934): venue "ECCV 2020 (oral)" and the project page found in the comment.
- DDPM (2006.11239): the code link found in the abstract; four figures with captions.
- Attention Is All You Need (1706.03762): the architecture figure as the teaser; three PDF figures listed.
- 3D Gaussian Splatting (2308.04079): the project page found.

What the real papers showed, fixed before the first commit:

1. **The teaser.** NeRF's and 3DGS's teasers are PDFs. The first version promoted the first raster figure to teaser,
   so the page led with a results table's neighbour. Now only the paper's first figure is the teaser; when it is a
   PDF, the page has none and the report says how to convert it (`pdftoppm`).
2. **Captions carried citation keys** ("from the Deep Blending dataset hedman2018deep"): `\cite`, `\ref`, `\label`
   and strike-out commands now go with their arguments; leftover commands (`\small`, `\centering`) are dropped,
   operators (`\log`, `\max`) kept as words.
3. **arXiv answered 429** after a few requests: the client now waits as told (Retry-After, up to a minute) or 10, 20,
   40 seconds, three times.

Found by the tests while writing them:

4. **A path-escape bug** in reading the source: `lstrip("./")` strips characters, so `../evil.tex` became
   `evil.tex` and was accepted. Rewritten (and the archive is never extracted anyway: only chosen images are
   written, under names the tool makes).
5. Spaces after TeX symbols were eaten (`\alpha \leq 0.5` → `α≤0.5`); a umlaut came out as a combining mark (NFC
   now); NeurIPS's `\And` between authors was not split; the venue pattern ignored case everywhere, so its "a name
   with capitals inside" rule did nothing (now only the words around it ignore case).

Also: files are written with LF on every system (the same page.json makes the same page), and a CI job renders the
made-up example and checks it is the committed one.

Tests: 28 (with doctests). ruff, mypy clean.

Next: polishing round 1 (a PDF teaser is common in this field: convert PDF figures when a converter such as
`pdftoppm` is installed, opt-in; more real papers, e.g. ones with affiliations in arXiv's metadata and ACM/CVPR
`\teaser` blocks).
