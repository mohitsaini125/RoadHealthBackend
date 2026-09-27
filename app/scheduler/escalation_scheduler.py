"""
APScheduler is only a clock: it triggers escalation_service.check_overdue_reports()
on an interval. It contains no business rules of its own.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.services import escalation_service

logger = logging.getLogger("escalation_scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_escalation_check() -> None:
    db = SessionLocal()
    try:
        escalation_service.check_overdue_reports(db)
    except Exception:
        logger.exception("Scheduled escalation check failed.")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled via SCHEDULER_ENABLED=false.")
        return None

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_escalation_check,
        "interval",
        minutes=settings.ESCALATION_INTERVAL_MINUTES,
        id="escalation_check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Escalation scheduler started (every %s minute(s)).", settings.ESCALATION_INTERVAL_MINUTES
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Escalation scheduler stopped.")
        _scheduler = None
