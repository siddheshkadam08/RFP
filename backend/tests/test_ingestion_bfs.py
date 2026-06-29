"""Breadth-first crawl orchestration: depth limits, pagination, dedup, budget, process flags.

Exercises ``ingestion_service.ingest_source`` with the network / DB / LLM / fetch layers stubbed,
so only the frontier logic is under test.
"""
import pytest

import app.services.ingestion_service as mod
from app.services.crawler import LinkCandidate
from app.services.url_fetcher import FetchedContent

# Synthetic site: url -> (content_links [(url, title)], pagination_urls)
SITE = {
    "https://site/root":    ([("https://site/detailA", "A"), ("https://site/detailB", "B")], ["https://site/page2"]),
    "https://site/page2":   ([("https://site/detailC", "C"), ("https://site/detailA", "A-dup")], []),
    "https://site/detailA": ([("https://site/subA", "subA")], []),
    "https://site/detailB": ([], []),
    "https://site/detailC": ([], []),
    "https://site/subA":    ([], []),
}


class _FakeDB:
    async def execute(self, *a, **k): return None
    async def commit(self): return None
    async def rollback(self): return None


class _NoOpGate:
    """Stand-in for RobotsGate so the frontier tests stay offline (no robots.txt fetch/sleep)."""

    def __init__(self, *a, **k): pass
    async def allowed(self, url): return True
    async def throttle(self, url): return None


class _FakeSource:
    id = "sid"
    url = "https://site/root"
    region = "asia"
    source_type = "regulator_website"


def _fetched(url: str) -> FetchedContent:
    return FetchedContent(url=url, title="t", text="x" * 500, content_type="html",
                          content_hash=url, content_length=500, raw_html="<html></html>")


@pytest.fixture
def crawl(monkeypatch):
    """Patch the I/O boundaries and return a runner that reports (processed, fetched, result)."""
    async def _run(max_depth: int, max_pages: int, gate_cls=_NoOpGate):
        processed: list[str] = []
        fetched: list[str] = []

        async def fake_fetch(url, timeout=30.0):
            fetched.append(url)
            return _fetched(url)

        async def fake_expand(source, fc, *, allow_fallbacks, interactive=False):
            links, pag = SITE.get(fc.url, ([], []))
            return [LinkCandidate(u, t) for u, t in links], list(pag)

        async def fake_gate(cands):
            return cands  # keep all (no LLM)

        async def fake_process(db, source, page):
            processed.append(page.url)
            return {"status": "ok", "documents_created": 1, "opportunities_created": 0, "url": page.url}

        monkeypatch.setattr(mod, "fetch_url_content", fake_fetch)
        monkeypatch.setattr(mod, "_expand_page", fake_expand)
        monkeypatch.setattr(mod, "_gate_candidates", fake_gate)
        monkeypatch.setattr(mod, "_process_page", fake_process)
        monkeypatch.setattr(mod, "RobotsGate", gate_cls)  # no robots.txt I/O in frontier tests
        monkeypatch.setattr(mod.settings, "CRAWL_MAX_DEPTH", max_depth)
        monkeypatch.setattr(mod.settings, "CRAWL_MAX_PAGES", max_pages)

        result = await mod.ingest_source(_FakeDB(), _FakeSource())
        return processed, fetched, result

    return _run


async def test_full_crawl_follows_depth_and_pagination(crawl):
    processed, fetched, result = await crawl(max_depth=3, max_pages=100)
    # detail/leaf pages get processed; listings (root) and pagination pages do not.
    assert {"https://site/detailA", "https://site/detailB", "https://site/detailC",
            "https://site/subA"} <= set(processed)
    assert "https://site/root" not in processed          # root listing = expand-only
    assert "https://site/page2" not in processed         # pagination page = expand-only
    assert "https://site/page2" in fetched               # ...but it WAS fetched & expanded
    assert processed.count("https://site/detailA") == 1  # deduped across root + page2
    assert result["mode"] == "crawl"


async def test_depth_limit_stops_recursion(crawl):
    processed, fetched, _ = await crawl(max_depth=1, max_pages=100)
    assert "https://site/detailA" in processed           # depth-1 detail processed
    assert "https://site/subA" not in fetched            # depth-2 child never reached


async def test_page_budget_caps_fetches(crawl):
    _, _, result = await crawl(max_depth=3, max_pages=2)
    assert result["pages_fetched"] == 2


async def test_robots_disallowed_links_are_skipped(crawl):
    """A robots.txt-disallowed frontier URL is never fetched and is counted, not crawled."""

    class _BlockDetailB:
        def __init__(self, *a, **k): pass
        async def allowed(self, url): return "detailB" not in url
        async def throttle(self, url): return None

    processed, fetched, result = await crawl(max_depth=3, max_pages=100, gate_cls=_BlockDetailB)
    assert "https://site/detailB" not in fetched      # disallowed -> never fetched
    assert "https://site/detailB" not in processed
    assert "https://site/detailA" in processed        # allowed siblings still crawled
    assert result["skipped_disallowed"] >= 1
