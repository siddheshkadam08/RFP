"""Scheduled crawl: due-source selection by frequency tier (FR-CRAWL-001 / FR-SOURCE-002)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.source import CrawlFrequency
from app.services import source_service as S

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)


# --- _is_due: per-tier freshness window --------------------------------------

def test_is_due_when_never_crawled():
    assert S._is_due(None, CrawlFrequency.DAILY, NOW) is True


def test_is_due_false_when_recently_crawled():
    assert S._is_due(NOW - timedelta(hours=2), CrawlFrequency.DAILY, NOW) is False


def test_is_due_true_just_under_interval_via_tolerance():
    # 23h elapsed >= 0.9 * 24h (21.6h) -> due, so a slightly-early beat still crawls.
    assert S._is_due(NOW - timedelta(hours=23), CrawlFrequency.DAILY, NOW) is True


def test_is_due_handles_naive_last_crawl():
    naive = datetime(2026, 6, 20, 12, 0)  # 8 days ago, no tzinfo
    assert S._is_due(naive, CrawlFrequency.WEEKLY, NOW) is True


def test_is_due_hourly_window():
    assert S._is_due(NOW - timedelta(minutes=20), CrawlFrequency.HOURLY, NOW) is False
    assert S._is_due(NOW - timedelta(minutes=58), CrawlFrequency.HOURLY, NOW) is True


# --- list_due_sources: filters the queried set by due-ness -------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    """Returns preset rows for any query (the WHERE clause is exercised by SQL, not here)."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _FakeResult(self._rows)


async def test_list_due_sources_returns_only_due():
    rows = [
        SimpleNamespace(id="fresh", frequency=CrawlFrequency.DAILY, last_crawl_at=NOW - timedelta(hours=1)),
        SimpleNamespace(id="stale", frequency=CrawlFrequency.DAILY, last_crawl_at=NOW - timedelta(days=2)),
        SimpleNamespace(id="new", frequency=CrawlFrequency.DAILY, last_crawl_at=None),
    ]
    due = await S.list_due_sources(_FakeDB(rows), "daily", now=NOW)
    ids = {s.id for s in due}
    assert ids == {"stale", "new"}  # "fresh" is skipped


async def test_list_due_sources_unknown_frequency_is_empty():
    due = await S.list_due_sources(_FakeDB([]), "fortnightly", now=NOW)
    assert due == []
