# Security

## What it does

- **Talks only to arXiv**, over HTTPS: `export.arxiv.org` (the API, for the metadata) and `arxiv.org/e-print` (the
  source, for figures; not fetched with `--figures 0`). One request every three seconds, as arXiv asks; the
  User-Agent names the tool, not the user. Nothing about you is sent.
- **The source is never extracted.** The archive is read in memory; a name that would leave it (`../x`, `/x`, `C:/x`),
  a link or a device is ignored; only the images chosen for the page are written, under names paper-page makes
  (`figures/fig-1.png`). Sizes are capped (60 MB download, 25 MB a file).
- **PDF figures** are converted by running poppler's `pdftoppm` when it is installed (`--no-convert` turns this
  off): a fixed program and arguments, no shell, a 60-second limit, the PDF in a temporary folder removed afterwards.
  The PDF is the paper's own figure from arXiv; `pdftoppm` is your installed copy, as up to date as you keep it.
- **The page is inert to the data.** Every text from arXiv or `page.json` is HTML-escaped; a link is written only when
  it is `http(s)`, a figure only when it is a path inside the page's folder or an `https` URL; anything else is left
  out and reported. The page loads no fonts, scripts or styles from elsewhere; its one script copies the BibTeX.
- **Your edits are kept.** `new` refuses to overwrite an existing `page.json` without `--force`.

## What it does not protect against

- **The figures themselves**: SVG figures are shown with `<img>`, which runs no script in them, but the images are the
  paper's, as its authors made them.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a vulnerability) rather than a public issue.
