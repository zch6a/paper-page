# Changelog

## 0.1.1 — 2026-11-14

- The agent skill's frontmatter is valid YAML again: its description held a `: `, which YAML reads as a new key, so
  the whole frontmatter failed to parse and the skill loaded without its description (`claude plugin validate`
  reported it). The values are quoted now.

## 0.1.0 — 2026-11-13

First release.

- `paper-page new <arXiv ID or link>`: `page.json` and `index.html` from arXiv's metadata, with the venue (when the
  comment names it), the code, video, data and project page links found in the abstract and comment, and a BibTeX
  entry; the teaser and figures, with their captions, from the paper's source (web image formats copied; PDF figures
  converted with poppler's `pdftoppm` when installed, `--no-convert` to skip).
- `paper-page new --tex main.tex`: the same from a TeX project, before the paper is on arXiv.
- `paper-page render`: the HTML again after editing `page.json`.
- The page: one self-contained file, light and dark, phone-friendly; Google Scholar's `citation_*` tags and Open
  Graph tags; a copy button for the BibTeX; a Content-Security-Policy that lets only that button's script run.
