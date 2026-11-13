"""arXiv: a paper's metadata from its public API (Atom), and its source (for figures) from its e-print link. One
request every three seconds, as arXiv asks; the User-Agent names the tool, not the user."""

from __future__ import annotations

import http.client
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable

from . import __version__

USER_AGENT = f"paper-page/{__version__} (+https://github.com/zch6a/paper-page)"
API = "https://export.arxiv.org/api/query"
MAX_BYTES = 60 * 1024 * 1024  # a source larger than this is not read (figures are optional)

Getter = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
NEW_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
OLD_ID = re.compile(r"([a-z][a-z\-]*(?:\.[A-Z]{2})?/\d{7})(v\d+)?")


class ArxivError(Exception):
    pass


def parse_id(text: str) -> tuple[str, str]:
    """An arXiv ID (and its version, or "") from an ID, an "arXiv:" reference or an abs/pdf link.

    >>> parse_id("2003.08934"), parse_id("arXiv:1706.03762v5"), parse_id("https://arxiv.org/pdf/2003.08934v2.pdf")
    (('2003.08934', ''), ('1706.03762', 'v5'), ('2003.08934', 'v2'))
    >>> parse_id("https://arxiv.org/abs/hep-th/9901001v1")
    ('hep-th/9901001', 'v1')
    """
    s = text.strip()
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.I)
    m = re.match(r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/(.+?)(?:\.pdf)?/?(?:[?#].*)?$", s, flags=re.I)
    if m:
        s = m.group(1)
    for pattern in (NEW_ID, OLD_ID):
        hit = pattern.fullmatch(s)
        if hit:
            return hit.group(1), hit.group(2) or ""
    raise ArxivError(f"not an arXiv ID or link: {text!r} (e.g. 2003.08934, arXiv:2003.08934v2, https://arxiv.org/abs/2003.08934)")


def _urlopen(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as r:  # noqa: S310 - arXiv's own URLs, built here
            body = r.read(MAX_BYTES + 1)
            return r.status, {k.lower(): v for k, v in r.headers.items()}, body
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read(4096) or b""
    except (OSError, http.client.HTTPException) as e:
        return 0, {}, str(e).encode()


class Client:
    def __init__(self, get: Getter | None = None, sleep: Callable[[float], None] = time.sleep, pause: float = 3.0) -> None:
        self._get = get or _urlopen
        self._sleep = sleep
        self._pause = pause
        self._last: float | None = None
        self.calls = 0

    def fetch(self, url: str) -> tuple[dict[str, str], bytes]:
        """A GET, at most one every `pause` seconds; retried three times on a network error, a 503 or a 429, waiting as
        arXiv says (Retry-After, at most a minute) or 10, 20, 40 seconds."""
        for attempt in range(4):
            if self._last is not None:
                self._sleep(max(0.0, self._pause - (time.monotonic() - self._last)))
            self.calls += 1
            status, headers, body = self._get(url, {"User-Agent": USER_AGENT})
            self._last = time.monotonic()
            if status == 200:
                if len(body) > MAX_BYTES:
                    raise ArxivError(f"{url}: larger than {MAX_BYTES // 2**20} MB, not read")
                return headers, body
            if status in (0, 429, 503) and attempt < 3:
                wait = headers.get("retry-after", "")
                self._sleep(min(60.0, float(wait)) if wait.isdigit() else 10.0 * 2**attempt)
                continue
            what = "could not be reached" if status == 0 else f"answered {status}"
            raise ArxivError(f"arXiv {what} for {url}" + (f": {body[:200].decode('utf-8', 'replace')}" if status == 0 else ""))
        raise AssertionError("unreachable")

    def metadata(self, arxiv_id: str, version: str = "") -> ET.Element:
        """The paper's Atom entry (the given version, or the latest)."""
        _, body = self.fetch(f"{API}?{urllib.parse.urlencode({'id_list': arxiv_id + version, 'max_results': '1'})}")
        return entry_of(body, arxiv_id + version)

    def source(self, arxiv_id: str, version: str = "") -> tuple[str, bytes]:
        """The paper's source as arXiv serves it (its content type, and the bytes: a gzipped tar, a gzipped single file, or
        a PDF when the authors gave no source)."""
        headers, body = self.fetch(f"https://arxiv.org/e-print/{arxiv_id}{version}")
        return headers.get("content-type", ""), body


def entry_of(body: bytes, wanted: str) -> ET.Element:
    """The one entry of an API answer; an error (arXiv answers an unknown ID with an entry titled "Error") is raised."""
    try:
        root = ET.fromstring(body)  # noqa: S314 - arXiv's own answer; expat refuses external entities
    except ET.ParseError as e:
        raise ArxivError(f"arXiv's answer for {wanted} is not Atom ({e})") from e
    entries = root.findall(f"{ATOM}entry")
    if not entries:
        raise ArxivError(f"arXiv has no paper {wanted}")
    entry = entries[0]
    eid = (entry.findtext(f"{ATOM}id") or "").strip()
    if "/api/errors" in eid or (entry.findtext(f"{ATOM}title") or "").strip() == "Error":
        raise ArxivError(f"arXiv has no paper {wanted}: {' '.join((entry.findtext(f'{ATOM}summary') or '').split())}")
    return entry
