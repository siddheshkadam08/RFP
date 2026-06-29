"""Background tasks for the RFP Intelligence System."""
import asyncio
import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _crawl_sources_async(frequency: str) -> dict:
    """Crawl every active, due source of ``frequency`` via the shared ingestion engine.

    Runs inside the Celery worker process (not the API), so disposing the async engine and
    headless browser at the end keeps each run self-contained — a fresh ``asyncio.run`` loop
    must not reuse connections/a browser bound to a previous run's (now-closed) loop.
    """
    # Imported lazily so importing this module (e.g. for the beat schedule) doesn't pull in
    # the async DB engine / fetcher stack.
    from app.core.database import AsyncSessionLocal, engine
    from app.services import source_service
    from app.services.ingestion_service import ingest_source
    from app.services.url_fetcher import shutdown_browser

    summaries: list[dict] = []
    try:
        async with AsyncSessionLocal() as db:
            sources = await source_service.list_due_sources(db, frequency)
            logger.info("Scheduled crawl (%s): %s source(s) due", frequency, len(sources))
            for source in sources:
                try:
                    summaries.append(await ingest_source(db, source))
                except Exception:  # noqa: BLE001 - ingest_source is isolated; never abort the batch
                    logger.exception("Scheduled crawl failed for source %s", getattr(source, "id", "?"))
    finally:
        await shutdown_browser()
        await engine.dispose()

    return {
        "frequency": frequency,
        "sources_crawled": len(summaries),
        "documents_created": sum(item.get("documents_created", 0) for item in summaries),
        "opportunities_created": sum(item.get("opportunities_created", 0) for item in summaries),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="app.tasks.crawl_sources")
def crawl_sources(frequency: str) -> dict:
    """Crawl active sources whose tier matches ``frequency`` and which are due now.

    Args:
        frequency: One of 'hourly', 'daily', 'weekly', 'monthly'.

    Returns:
        Summary of crawl results.
    """
    logger.info("Starting scheduled crawl for %s sources", frequency)
    return asyncio.run(_crawl_sources_async(frequency))


@celery_app.task(name="app.tasks.process_document")
def process_document(document_id: str) -> dict:
    """Process a single document through the AI pipeline.

    Pipeline:
    1. Extract text (OCR if needed)
    2. Check relevance
    3. Extract opportunity data
    4. Classify category
    5. Score opportunity
    6. Store results

    Args:
        document_id: UUID of the document to process.

    Returns:
        Processing results.
    """
    logger.info("Processing document: %s", document_id)
    return {
        "document_id": document_id,
        "status": "completed",
        "relevant": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="app.tasks.generate_weekly_report")
def generate_weekly_report() -> dict:
    """Generate the weekly intelligence report.

    Includes:
    - New opportunities detected
    - Updated opportunities
    - High priority opportunities
    - Regional trends
    - Standards trends
    - Emerging market signals
    """
    logger.info("Generating weekly report")
    return {
        "status": "completed",
        "report_type": "weekly",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="app.tasks.check_deadline_alerts")
def check_deadline_alerts() -> dict:
    """Check for opportunities with approaching deadlines and create alerts.

    Triggers alerts for:
    - Deadlines within 7 days
    - Deadlines within 3 days (high severity)
    - Deadlines within 1 day (critical severity)
    """
    logger.info("Checking deadline alerts")
    return {
        "alerts_created": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="app.tasks.generate_report_async")
def generate_report_async(report_id: str, report_type: str, parameters: dict | None = None) -> dict:
    """Generate a report asynchronously.

    Args:
        report_id: UUID of the report record.
        report_type: Type of report to generate.
        parameters: Optional report parameters.
    """
    logger.info("Generating report %s of type %s", report_id, report_type)
    return {
        "report_id": report_id,
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
