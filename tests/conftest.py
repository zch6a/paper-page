"""No test reaches the network: arXiv is a fake everywhere, and the real opener fails loudly if anything calls it."""

from __future__ import annotations

import pytest

from paper_page import arxiv


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        raise AssertionError(f"a test tried to reach {url}")

    monkeypatch.setattr(arxiv, "_urlopen", refuse)
