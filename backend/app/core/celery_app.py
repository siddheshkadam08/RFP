"""Celery application for background task processing."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "rfp_intelligence",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Scheduled tasks
celery_app.conf.beat_schedule = {
    "crawl-daily-sources": {
        "task": "app.tasks.crawl_sources",
        "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
        "args": ("daily",),
    },
    "crawl-hourly-sources": {
        "task": "app.tasks.crawl_sources",
        "schedule": crontab(minute=0),  # Every hour
        "args": ("hourly",),
    },
    "crawl-weekly-sources": {
        "task": "app.tasks.crawl_sources",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # Monday 3 AM
        "args": ("weekly",),
    },
    "crawl-monthly-sources": {
        "task": "app.tasks.crawl_sources",
        "schedule": crontab(hour=4, minute=0, day_of_month=1),  # 1st of month, 4 AM
        "args": ("monthly",),
    },
    "generate-weekly-report": {
        "task": "app.tasks.generate_weekly_report",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),  # Monday 6 AM
    },
    "check-deadline-alerts": {
        "task": "app.tasks.check_deadline_alerts",
        "schedule": crontab(hour=8, minute=0),  # Daily 8 AM
    },
}
