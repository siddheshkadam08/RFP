"""robots.txt compliance + crawl-delay throttling (FR-CRAWL-005).

The gate's only I/O boundary is ``fetch_raw_text`` (the robots.txt GET), which these
tests stub, so they are fully offline.
"""
from app.services import robots


def _stub_robots(monkeypatch, body):
    async def fake_fetch(url, timeout=20.0):
        return body

    monkeypatch.setattr(robots, "fetch_raw_text", fake_fetch)


# --- allow / disallow --------------------------------------------------------

async def test_disallow_blocks_only_matching_paths(monkeypatch):
    _stub_robots(monkeypatch, "User-agent: RFPIntelligenceBot\nDisallow: /private\n")
    gate = robots.RobotsGate(respect=True)
    assert await gate.allowed("https://x.test/public/page") is True
    assert await gate.allowed("https://x.test/private/secret") is False


async def test_wildcard_disallow_all_blocks(monkeypatch):
    _stub_robots(monkeypatch, "User-agent: *\nDisallow: /\n")
    gate = robots.RobotsGate(respect=True)
    assert await gate.allowed("https://x.test/anything") is False


async def test_missing_robots_allows_all(monkeypatch):
    _stub_robots(monkeypatch, None)  # 404 / unreachable -> allow all
    gate = robots.RobotsGate(respect=True)
    assert await gate.allowed("https://x.test/whatever") is True


async def test_respect_false_bypasses_and_never_fetches(monkeypatch):
    fetched = []

    async def fake_fetch(url, timeout=20.0):
        fetched.append(url)
        return "User-agent: *\nDisallow: /\n"

    monkeypatch.setattr(robots, "fetch_raw_text", fake_fetch)
    gate = robots.RobotsGate(respect=False)
    assert await gate.allowed("https://x.test/blocked") is True
    assert fetched == []  # disabled -> robots.txt is never even requested


# --- per-origin throttling ---------------------------------------------------

async def test_throttle_delays_subsequent_requests_using_crawl_delay(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(robots.asyncio, "sleep", fake_sleep)
    _stub_robots(monkeypatch, "User-agent: *\nCrawl-delay: 2\n")

    gate = robots.RobotsGate(respect=True, default_delay=0.0)
    await gate.throttle("https://x.test/a")  # first request: no wait
    await gate.throttle("https://x.test/b")  # second: must wait ~crawl-delay
    assert len(slept) == 1
    assert 1.5 <= slept[0] <= 2.0


async def test_throttle_caps_at_max_delay(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(robots.asyncio, "sleep", fake_sleep)
    _stub_robots(monkeypatch, "User-agent: *\nCrawl-delay: 9999\n")

    gate = robots.RobotsGate(respect=True, default_delay=0.0, max_delay=5.0)
    await gate.throttle("https://x.test/a")
    await gate.throttle("https://x.test/b")
    assert slept and slept[0] <= 5.0


async def test_throttle_zero_default_delay_no_sleep(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(robots.asyncio, "sleep", fake_sleep)
    _stub_robots(monkeypatch, "User-agent: *\nDisallow: /private\n")  # no Crawl-delay

    gate = robots.RobotsGate(respect=True, default_delay=0.0)
    await gate.throttle("https://x.test/a")
    await gate.throttle("https://x.test/b")
    assert slept == []  # no crawl-delay + zero default -> never sleeps
