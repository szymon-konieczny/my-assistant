import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from invoice.scanner import run_scan
from news.fetcher import fetch_all_feeds

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def scheduled_scan():
    """Monthly scan job — scans the previous calendar month."""
    logger.info("Scheduled monthly scan triggered")
    run_scan()


def scheduled_news_fetch():
    """Daily news fetch job."""
    logger.info("Scheduled news fetch triggered")
    fetch_all_feeds()


def setup_scheduler():
    """Configure scheduled jobs."""
    scheduler.add_job(
        scheduled_scan,
        CronTrigger(
            day=settings.scan_cron_day,
            hour=settings.scan_cron_hour,
            minute=settings.scan_cron_minute,
        ),
        id="monthly_invoice_scan",
        replace_existing=True,
    )
    logger.info(
        f"Scheduled monthly scan: day={settings.scan_cron_day}, "
        f"hour={settings.scan_cron_hour}:{settings.scan_cron_minute:02d}"
    )

    scheduler.add_job(
        scheduled_news_fetch,
        CronTrigger(hour=8, minute=0),
        id="daily_news_fetch",
        replace_existing=True,
    )
    logger.info("Scheduled daily news fetch: 08:00")
