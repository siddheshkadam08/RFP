from __future__ import annotations

"""Seed 20 realistic SupTech/RegTech sources into the sources table.

Run from the ``backend/`` directory with the virtualenv active::

    python -m scripts.seed_sources
"""

import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.source import CrawlFrequency, Source, SourceType  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_sources")

SOURCES = [
    {
        "name": "US Federal Reserve",
        "url": "https://www.federalreserve.gov/newsevents.htm",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "central_bank",
        "country": "United States",
        "region": "North America",
        "tags": ["monetary-policy", "banking-regulation", "fintech"],
    },
    {
        "name": "SEC EDGAR",
        "url": "https://www.sec.gov/cgi-bin/browse-edgar",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "capital_market",
        "country": "United States",
        "region": "North America",
        "tags": ["securities", "XBRL", "regulatory-filings"],
    },
    {
        "name": "SAM.gov",
        "url": "https://sam.gov/search/?index=opp",
        "source_type": SourceType.TENDER_PORTAL,
        "frequency": CrawlFrequency.DAILY,
        "domain": "other",
        "country": "United States",
        "region": "North America",
        "tags": ["federal-procurement", "tenders", "RFP"],
    },
    {
        "name": "Bank of England",
        "url": "https://www.bankofengland.co.uk/news/news",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "central_bank",
        "country": "United Kingdom",
        "region": "Europe",
        "tags": ["prudential-regulation", "fintech", "XBRL"],
    },
    {
        "name": "European Central Bank",
        "url": "https://www.ecb.europa.eu/press/html/index.en.html",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "central_bank",
        "country": "Germany",
        "region": "Europe",
        "tags": ["eurozone", "banking-supervision", "SDMX"],
    },
    {
        "name": "European Banking Authority",
        "url": "https://www.eba.europa.eu/news-and-events",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "capital_market",
        "country": "France",
        "region": "Europe",
        "tags": ["DPM", "XBRL", "regulatory-reporting"],
    },
    {
        "name": "TED (Tenders Electronic Daily)",
        "url": "https://ted.europa.eu/en/",
        "source_type": SourceType.TENDER_PORTAL,
        "frequency": CrawlFrequency.DAILY,
        "domain": "other",
        "country": "Belgium",
        "region": "Europe",
        "tags": ["EU-procurement", "public-tenders"],
    },
    {
        "name": "Reserve Bank of India",
        "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "central_bank",
        "country": "India",
        "region": "South Asia",
        "tags": ["payments", "digital-rupee", "XBRL"],
    },
    {
        "name": "SEBI India",
        "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=1",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "capital_market",
        "country": "India",
        "region": "South Asia",
        "tags": ["securities", "XBRL", "market-regulation"],
    },
    {
        "name": "Monetary Authority of Singapore",
        "url": "https://www.mas.gov.sg/news",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.DAILY,
        "domain": "central_bank",
        "country": "Singapore",
        "region": "Asia Pacific",
        "tags": ["fintech", "digital-assets", "suptech"],
    },
    {
        "name": "Bank of Japan",
        "url": "https://www.boj.or.jp/en/announcements/index.htm",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "Japan",
        "region": "Asia Pacific",
        "tags": ["monetary-policy", "CBDC", "ISO-20022"],
    },
    {
        "name": "Central Bank of UAE",
        "url": "https://www.centralbank.ae/en/news",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "United Arab Emirates",
        "region": "Middle East & North Africa",
        "tags": ["digital-dirham", "open-banking", "fintech"],
    },
    {
        "name": "Saudi Central Bank (SAMA)",
        "url": "https://www.sama.gov.sa/en-US/News/Pages/default.aspx",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "Saudi Arabia",
        "region": "Middle East & North Africa",
        "tags": ["vision-2030", "banking-regulation", "suptech"],
    },
    {
        "name": "South African Reserve Bank",
        "url": "https://www.resbank.co.za/en/home/publications",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "South Africa",
        "region": "Sub-Saharan Africa",
        "tags": ["prudential-regulation", "XBRL", "fintech"],
    },
    {
        "name": "Central Bank of Nigeria",
        "url": "https://www.cbn.gov.ng/Press/",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "Nigeria",
        "region": "Sub-Saharan Africa",
        "tags": ["eNaira", "banking-supervision", "digital-finance"],
    },
    {
        "name": "Central Bank of Kenya",
        "url": "https://www.centralbank.go.ke/press-releases/",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "Kenya",
        "region": "Sub-Saharan Africa",
        "tags": ["mobile-money", "suptech", "financial-inclusion"],
    },
    {
        "name": "Banco Central do Brasil",
        "url": "https://www.bcb.gov.br/en/pressdetail/news",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "central_bank",
        "country": "Brazil",
        "region": "Latin America & Caribbean",
        "tags": ["PIX", "open-finance", "DREX"],
    },
    {
        "name": "World Bank Procurement",
        "url": "https://projects.worldbank.org/en/projects-operations/procurement",
        "source_type": SourceType.FUNDING_PORTAL,
        "frequency": CrawlFrequency.DAILY,
        "domain": "other",
        "country": None,
        "region": "Global",
        "tags": ["development-finance", "IFI", "SupTech"],
    },
    {
        "name": "BIS (Bank for International Settlements)",
        "url": "https://www.bis.org/list/press_rel/index.htm",
        "source_type": SourceType.REGULATOR_WEBSITE,
        "frequency": CrawlFrequency.MONTHLY,
        "domain": "other",
        "country": "Switzerland",
        "region": "Global",
        "tags": ["Basel", "standards", "innovation-hub"],
    },
    {
        "name": "XBRL International",
        "url": "https://www.xbrl.org/news/",
        "source_type": SourceType.NEWS_FEED,
        "frequency": CrawlFrequency.WEEKLY,
        "domain": "other",
        "country": None,
        "region": "Global",
        "tags": ["XBRL", "digital-reporting", "taxonomy"],
    },
]


async def seed_sources() -> None:
    async with AsyncSessionLocal() as db:
        for src_data in SOURCES:
            existing = (
                await db.execute(select(Source).where(Source.name == src_data["name"]))
            ).scalar_one_or_none()
            if existing:
                logger.info("Source already exists: %s — skipping.", src_data["name"])
                continue
            db.add(Source(**src_data))
            logger.info("Inserted: %s (%s, %s)", src_data["name"], src_data["region"], src_data["source_type"].value)
        await db.commit()


async def main() -> None:
    try:
        await seed_sources()
    finally:
        await engine.dispose()
    logger.info("Seeding complete. %d sources defined.", len(SOURCES))


if __name__ == "__main__":
    asyncio.run(main())
