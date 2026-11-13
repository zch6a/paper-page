r"""TeX, as far as a project page needs it: titles and abstracts as readable text (simple math as Unicode), the files
of an arXiv source read in memory (never extracted: a name in the archive never becomes a path on disk), the main
file with its \input files, and its figures (the image each includes, and its caption)."""

from __future__ import annotations

import gzip
import io
import posixpath
import re
import tarfile
import unicodedata
from dataclasses import dataclass

GREEK = {name: chr(code) for name, code in (
    ("alpha", 0x3B1), ("beta", 0x3B2), ("gamma", 0x3B3), ("delta", 0x3B4), ("epsilon", 0x3B5), ("varepsilon", 0x3B5),
    ("zeta", 0x3B6), ("eta", 0x3B7), ("theta", 0x3B8), ("vartheta", 0x3D1), ("iota", 0x3B9), ("kappa", 0x3BA),
    ("lambda", 0x3BB), ("mu", 0x3BC), ("nu", 0x3BD), ("xi", 0x3BE), ("pi", 0x3C0), ("rho", 0x3C1), ("sigma", 0x3C3),
    ("tau", 0x3C4), ("upsilon", 0x3C5), ("phi", 0x3C6), ("varphi", 0x3C6), ("chi", 0x3C7), ("psi", 0x3C8), ("omega", 0x3C9),
    ("Gamma", 0x393), ("Delta", 0x394), ("Theta", 0x398), ("Lambda", 0x39B), ("Xi", 0x39E), ("Pi", 0x3A0),
    ("Sigma", 0x3A3), ("Phi", 0x3A6), ("Psi", 0x3A8), ("Omega", 0x3A9),
)}  # fmt: skip
SYMBOLS = {
    "times": "×", "cdot": "·", "pm": "±", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "approx": "≈",
    "sim": "~", "infty": "∞", "rightarrow": "→", "to": "→", "leftarrow": "←", "Rightarrow": "⇒", "in": "∈",
    "sqrt": "√", "sum": "∑", "partial": "∂", "nabla": "∇", "ell": "ℓ", "dots": "…", "ldots": "…", "cdots": "⋯",
    "%": "%", "&": "&", "_": "_", "#": "#", "$": "$", "{": "{", "}": "}", "textasciitilde": "~",
}  # fmt: skip
SUP = str.maketrans("0123456789+-=()niT", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵀ")
SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303", "c": "\u0327", "v": "\u030c", "=": "\u0304", "u": "\u0306"}


def to_text(s: str) -> str:
    r"""TeX as text for a web page: simple math in Unicode, formatting commands dropped, quotes and dashes typeset.

    >>> to_text(r"An $O(n^2)$ method with $\alpha \leq 0.5$ and $\mathbf{x}_{t+1}$")
    'An O(n²) method with α ≤ 0.5 and xₜ₊₁'
    >>> to_text(r"``Neural'' fields -- \emph{fast}, 95\% of the time, by Schr\"odinger")
    '“Neural” fields – fast, 95% of the time, by Schrödinger'
    >>> to_text(r"{\small Generated samples} at $\log p(x)$, \centering done")
    'Generated samples at log p(x), done'
    """
    # references and revision marks go with their arguments: \cite{key} must not leave "key" in the text
    s = re.sub(r"~?\\(?:cite[a-z]*|nocite|ref|eqref|autoref|cref|Cref|pageref|label|sout|st|xout)\*?\s*(?:\[[^\]]*\]\s*)*\{[^{}]*\}", "", s)
    s = re.sub(r"\\([`'\"^~=])\{?([A-Za-z])\}?", lambda m: m.group(2) + ACCENTS[m.group(1)], s)
    s = re.sub(r"\\([cvu])\{([A-Za-z])\}", lambda m: m.group(2) + ACCENTS[m.group(1)], s)
    for _ in range(3):  # nested: \textbf{\emph{x}}
        s = re.sub(
            r"\\(?:text(?:bf|it|tt|rm|sc|sf|normal)?|emph|mathrm|mathbf|mathit|mathcal|mathbb|mathsf|mathtt|boldsymbol|bm|operatorname|textsc|underline|url)\{([^{}]*)\}",
            r"\1",
            s,
        )
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: _script(m.group(1), SUP, "^"), s)
    s = re.sub(r"_\{([^{}]*)\}", lambda m: _script(m.group(1), SUB, "_"), s)
    s = re.sub(r"\^([0-9a-zA-Z])", lambda m: _script(m.group(1), SUP, "^"), s)
    s = re.sub(r"_([0-9])", lambda m: _script(m.group(1), SUB, "_"), s)
    # what is left: math operators as their names, other commands (\small, \centering, \bf) dropped
    s = re.sub(r"\\([A-Za-z]+)( ?)", _command, s)
    s = re.sub(r"\\([%&_#${}])", lambda m: SYMBOLS[m.group(1)], s)
    s = s.replace("``", "“").replace("''", "”").replace("---", "—").replace("--", "–").replace("~", " ").replace("\\\\", " ")
    s = re.sub(r"(?<!\\)\$", "", s)
    s = re.sub(r"\\[,;:! ]", " ", s)
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+([,.;:!?)])", r"\1", " ".join(s.split()))  # "quality \cite{x}, while": no space before the comma
    return unicodedata.normalize("NFC", s)  # o + a combining diaeresis as one letter


OPERATORS = {"log", "exp", "ln", "max", "min", "arg", "sin", "cos", "tan", "lim", "sup", "inf", "det", "dim", "argmax", "argmin"}


def _command(m: re.Match[str]) -> str:
    """A command left after the rest: a symbol (keeping the space after it), an operator's name, or nothing."""
    name, space = m.group(1), m.group(2)
    symbol = GREEK.get(name) or SYMBOLS.get(name)
    if symbol:
        return symbol + space
    return name + " " if name in OPERATORS else ""


def _script(text: str, table: dict[int, int], mark: str) -> str:
    """A super- or subscript in Unicode when every character has a form for it, else written out: x^(ab), x_θ."""
    plain = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1)) or m.group(0), text).replace(" ", "")
    t = plain.translate(table)
    if t and all(ord(c) in table.values() for c in t):
        return t
    return mark + plain if len(plain) == 1 else f"{mark}({plain})"


# --- the source ---

MAX_FILE = 25 * 1024 * 1024
MAX_TOTAL = 250 * 1024 * 1024
KEEP = (".tex", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".eps", ".bbl", ".sty", ".cls")


def read_source(blob: bytes) -> dict[str, bytes]:
    """The files of an arXiv source, by their normalized path in it (a gzipped or plain tar, or one gzipped TeX file);
    {} when it is not a source (a PDF, say). Read in memory; names that leave the archive (../x, /x) are dropped."""
    data = blob
    if blob[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(blob)
        except (OSError, EOFError):
            return {}
    if data[:5] == b"%PDF-":
        return {}
    files: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            total = 0
            for member in tar:
                name = _safe_name(member.name)
                if not member.isfile() or name is None or not name.lower().endswith(KEEP) or member.size > MAX_FILE:
                    continue
                total += member.size
                if total > MAX_TOTAL:
                    break
                f = tar.extractfile(member)
                if f is not None:
                    files[name] = f.read()
        return files
    except tarfile.TarError:
        pass
    text = data[:MAX_FILE]
    if b"\\documentclass" in text or b"\\begin{document}" in text:
        return {"main.tex": text}  # one gzipped TeX file
    return {}


def _safe_name(name: str) -> str | None:
    """The archive name as a relative path that stays inside it, else None.

    >>> _safe_name("./figs/a.png"), _safe_name("../a.tex"), _safe_name("x/../../a.tex"), _safe_name("/etc/a"), _safe_name("C:/a")
    ('figs/a.png', None, None, None, None)
    """
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    n = posixpath.normpath(n)
    return None if n in (".", "..") or n.startswith("../") else n


def decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def strip_comments(tex: str) -> str:
    r"""TeX without its comments (a % not escaped as \%).

    >>> strip_comments("a % note\nb 50\\% c")
    'a \nb 50\\% c'
    """
    return re.sub(r"(?<!\\)%.*", "", tex)


def main_file(files: dict[str, bytes]) -> str | None:
    """The main TeX file: one with \\documentclass and \\begin{document} (of several, ms.tex/main.tex/paper.tex first,
    then the largest)."""
    mains = [
        n for n, b in files.items() if n.lower().endswith(".tex") and re.search(rb"(?m)^[^%\n]*\\documentclass", b) and b"\\begin{document}" in b
    ]
    if not mains:
        return None
    preferred = ("main.tex", "ms.tex", "paper.tex")
    mains.sort(key=lambda n: (posixpath.basename(n).lower() not in preferred, n.count("/"), -len(files[n])))
    return mains[0]


def expand(name: str, files: dict[str, bytes], depth: int = 0) -> str:
    r"""The file with its \input and \include files in place (comments stripped), as far as they are in the source."""
    tex = strip_comments(decode(files.get(name, b"")))
    if depth > 8:
        return tex
    base = posixpath.dirname(name)

    def inline(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        for candidate in (target, target + ".tex", posixpath.join(base, target), posixpath.join(base, target) + ".tex"):
            c = posixpath.normpath(candidate)
            if c in files and c != name:
                return expand(c, files, depth + 1)
        return ""

    return re.sub(r"\\(?:input|include|subfile)\s*\{([^{}]+)\}", inline, tex)


def braced(tex: str, start: int) -> tuple[str, int]:
    """The text of the {group} opening at `start` (its braces balanced) and the index after it.

    >>> braced("x{a{b}c}d", 1)
    ('a{b}c', 8)
    """
    depth, i = 0, start
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return tex[start + 1 : i], i + 1
        i += 1
    return tex[start + 1 :], len(tex)


def command_arg(tex: str, command: str) -> str | None:
    r"""The first argument of the first \command (its optional [..] skipped), braces balanced."""
    m = re.search(r"\\" + command + r"\*?\s*(?:\[[^\]]*\]\s*)?\{", tex)
    if not m:
        return None
    return braced(tex, m.end() - 1)[0]


@dataclass
class TexFigure:
    image: str  # the path as \includegraphics names it
    caption: str  # as TeX


def figures(tex: str) -> list[TexFigure]:
    r"""Each figure (and figure*, teaser) environment's first \includegraphics and its caption, in order."""
    out = []
    for m in re.finditer(r"\\begin\{(figure\*?|teaserfigure|wrapfigure)\}(.*?)\\end\{\1\}", tex, flags=re.S):
        body = m.group(2)
        g = re.search(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}", body)
        if g:
            out.append(TexFigure(g.group(1).strip(), command_arg(body, "caption") or ""))
    teaser = re.search(r"\\teaser\s*\{", tex)  # some styles (ACM, CVPR teasers) put the teaser in the title block
    if teaser:
        body = braced(tex, teaser.end() - 1)[0]
        g = re.search(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}", body)
        if g and not any(f.image == g.group(1).strip() for f in out):
            out.insert(0, TexFigure(g.group(1).strip(), command_arg(body, "caption") or ""))
    return out


def macros(tex: str) -> dict[str, str]:
    r"""The paper's own macros without arguments (\newcommand{\model}{SAM}, \def\ours{Tiny}), by name.

    >>> macros(r"\newcommand{\model}{SAM\xspace} \newcommand\ours{Tiny} \def\etal{et al.} \newcommand{\f}[1]{#1}")
    {'model': 'SAM', 'ours': 'Tiny', 'etal': 'et al.'}
    """
    out: dict[str, str] = {}
    for m in re.finditer(r"\\(?:(?:re)?newcommand\*?|providecommand\*?)\s*\{?\\([A-Za-z]+)\}?\s*(\[|\{)|\\def\s*\\([A-Za-z]+)\s*(\{)", tex):
        name, opener = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if opener == "[":
            continue  # it takes arguments: not expanded
        body = braced(tex, m.end() - 1)[0]
        out.setdefault(name, re.sub(r"\\xspace\b|\\@\s*", "", body).strip())
    return out


def use_macros(text: str, own: dict[str, str]) -> str:
    r"""The text with the paper's own macros in place (nested ones too, three levels).

    >>> use_macros(r"masks from \model{} and \ours.", {"model": "SAM", "ours": r"\model-2"})
    'masks from SAM and SAM-2.'
    """
    if not own:
        return text
    pattern = re.compile(r"\\(" + "|".join(sorted(map(re.escape, own), key=len, reverse=True)) + r")(?![A-Za-z])(?:\{\})?")
    for _ in range(3):
        text = pattern.sub(lambda m: own[m.group(1)], text)
    return text


WEB_IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def find_image(path: str, files: dict[str, bytes], main: str, graphicspath: list[str]) -> str | None:
    """The file an \\includegraphics path names (extensions tried in the order pdfLaTeX does, web images first)."""
    base = posixpath.dirname(main)
    dirs = ["", base, *(posixpath.join(base, g) for g in graphicspath), *graphicspath]
    exts = ["", *WEB_IMAGES, ".pdf", ".eps"]
    for d in dirs:
        for ext in exts:
            c = posixpath.normpath(posixpath.join(d, path + ext)) if path else ""
            if c in files:
                return c
    return None


def graphicspath(tex: str) -> list[str]:
    r"""The folders \graphicspath names.

    >>> graphicspath(r"\graphicspath{{figs/}{./img/}}")
    ['figs/', 'img/']
    """
    arg = command_arg(tex, "graphicspath")
    return [posixpath.normpath(p).rstrip("/") + "/" for p in re.findall(r"\{([^{}]*)\}", arg or "") if p.strip()]
