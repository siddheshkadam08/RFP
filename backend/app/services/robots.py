"""robots.txt compliance + per-origin crawl-delay throttling (FR-CRAWL-005).

A ``RobotsGate`` is a per-crawl object that, for each origin it sees:
  * fetches and caches the site's ``robots.txt`` (once), and
  * answers ``allowed(url)`` for our declared bot UA, and
  * enforces a minimum delay between requests via ``throttle(url)`` — honoring the
    site's ``Crawl-delay`` when present, otherwise a configured default.

It degrades open: a missing/unreadable ``robots.txt`` or any parser error allows the
fetch (standard crawler practice) so politeness never silently kills a crawl.
"""
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from app.core.config import settings
from app.services.url_fetcher import USER_AGENT, fetch_raw_text

logger = logging.getLogger(__name__)

# Product token matched against robots.txt ``User-agent:`` lines. RobotFileParser splits
# the supplied UA on "/", so "RFPIntelligenceBot/1.0 (...)" already reduces to this — but
# we pass the bare token explicitly for clarity.
_UA_TOKEN = USER_AGENT.split("/", 1)[0]


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class _OriginRules:
    """Cached robots state for one origin + its next-allowed-fetch timestamp."""

    __slots__ = ("parser", "crawl_delay", "next_at")

    def __init__(self, parser: RobotFileParser, crawl_delay: float | None) -> None:
        self.parser = parser
        self.crawl_delay = crawl_delay
        self.next_at = 0.0  # monotonic clock; 0 => first request is never delayed


class RobotsGate:
    """Per-crawl robots.txt allow-checks + per-origin rate limiting."""

    def __init__(
        self,
        *,
        respect: bool | None = None,
        default_delay: float | None = None,
        max_delay: float | None = None,
        user_agent: str = _UA_TOKEN,
    ) -> None:
        self.respect = settings.CRAWL_RESPECT_ROBOTS if respect is None else respect
        self.default_delay = (
            settings.CRAWL_DEFAULT_DELAY_SECONDS if default_delay is None else default_delay
        )
        self.max_delay = settings.CRAWL_MAX_DELAY_SECONDS if max_delay is None else max_delay
        self.user_agent = user_agent
        self._rules: dict[str, _OriginRules] = {}

    async def _rules_for(self, url: str) -> _OriginRules:
        origin = _origin(url)
        cached = self._rules.get(origin)
        if cached is not None:
            return cached
        text = await fetch_raw_text(f"{origin}/robots.txt")
        parser = RobotFileParser()
        # Missing/unreadable robots.txt -> parse nothing -> allow all (standard practice).
        parser.parse(text.splitlines() if text else [])
        parser.modified()  # ensure ``last_checked`` is set so can_fetch() evaluates rules
        delay: float | None = None
        if text:
            try:
                raw = parser.crawl_delay(self.user_agent)
                delay = float(raw) if raw is not None else None
            except Exception:  # noqa: BLE001 - never fail a crawl on a delay parse
                delay = None
        rules = _OriginRules(parser, delay)
        self._rules[origin] = rules
        return rules

    async def allowed(self, url: str) -> bool:
        """True if our bot may fetch ``url`` per the origin's robots.txt."""
        if not self.respect:
            return True
        try:
            rules = await self._rules_for(url)
            return bool(rules.parser.can_fetch(self.user_agent, url))
        except Exception as exc:  # noqa: BLE001 - never block a crawl on a parser error
            logger.debug("robots allow-check failed for %s (allowing): %s", url, exc)
            return True

    async def throttle(self, url: str) -> None:
        """Sleep just enough that consecutive requests to one origin respect its delay."""
        try:
            rules = await self._rules_for(url)
        except Exception:  # noqa: BLE001 - throttling is best-effort
            return
        delay = rules.crawl_delay if rules.crawl_delay is not None else self.default_delay
        if delay <= 0:
            return
        delay = min(delay, self.max_delay)
        now = time.monotonic()
        wait = rules.next_at - now
        if wait > 0:
            await asyncio.sleep(wait)
            now = time.monotonic()
        rules.next_at = now + delay
