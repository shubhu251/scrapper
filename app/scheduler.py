import os
import logging
from typing import Any, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .tasks import run_bullseye_spider, run_scrapy_spider
import yaml


def start_scheduler():
    """Start background scheduler from YAML config or env cron (default: 02:00 IST)."""
    scheduler_tz = os.environ.get("TZ", "UTC")
    scheduler = BackgroundScheduler(timezone=scheduler_tz)
    logger = logging.getLogger("scheduler")
    schedules_file = os.environ.get("SCHEDULES_FILE", "jobs.yml")

    def add_job_from_cron(job_id: str, cron_expr: str, func, tz: str = None):
        minute, hour, day, month, dow = cron_expr.split()
        trigger_kwargs = {"minute": minute, "hour": hour, "day": day, "month": month, "day_of_week": dow}
        if tz:
            trigger_kwargs["timezone"] = tz
        scheduler.add_job(
            func,
            CronTrigger(**trigger_kwargs),
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )

    if os.path.exists(schedules_file):
        try:
            with open(schedules_file, "r") as f:
                config: Dict[str, Any] = yaml.safe_load(f) or {}
            jobs: List[Dict[str, Any]] = config.get("jobs", [])
            for job in jobs:
                job_id = job.get("id") or "job_" + str(len(jobs))
                cron = job.get("cron")
                job_type = job.get("type", "spider")
                target = job.get("target", "bullseye_press")
                job_tz = job.get("timezone", scheduler_tz)
                if not cron:
                    continue
                if job_type == "spider":
                    logger.info(f"Scheduling spider '{target}' with cron '{cron}' (tz={job_tz})")
                    add_job_from_cron(job_id, cron, lambda t=target: run_scrapy_spider(t), tz=job_tz)
                elif job_type == "bullseye":
                    logger.info(f"Scheduling bullseye spider with cron '{cron}' (tz={job_tz})")
                    add_job_from_cron(job_id, cron, run_bullseye_spider, tz=job_tz)
                else:
                    # Unknown type; skip
                    logger.warning(f"Unknown job type '{job_type}' in schedule; skipping job '{job_id}'")
                    continue
        except Exception as e:
            # Fallback to env-based single cron if YAML parsing fails
            cron_expr = os.environ.get("CRON_EXPRESSION", "0 20 * * *")
            logger.error(f"Failed to parse schedules file '{schedules_file}': {e}. Falling back to CRON_EXPRESSION={cron_expr}")
            add_job_from_cron("bullseye_cron_job", cron_expr, run_bullseye_spider, tz=scheduler_tz)
    else:
        # No YAML provided, fallback to single env cron
        cron_expr = os.environ.get("CRON_EXPRESSION", "0 20 * * *")
        logging.getLogger("scheduler").info(f"No schedules file found. Using CRON_EXPRESSION={cron_expr} (tz={scheduler_tz})")
        add_job_from_cron("bullseye_cron_job", cron_expr, run_bullseye_spider, tz=scheduler_tz)

    scheduler.start()
    return scheduler


