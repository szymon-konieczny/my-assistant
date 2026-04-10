import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from invoice.scanner import run_scan

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def scheduled_scan():
    """Monthly scan job — scans the previous calendar month."""
    logger.info("Scheduled monthly scan triggered")
    run_scan()


def setup_scheduler():
    """Configure the monthly scan job."""
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
