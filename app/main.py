import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from .scheduler import start_scheduler
from .routers.healthApi import router as health_router
from .routers.jobsApi import router as jobs_router
from .db import run_migrations


app = FastAPI(title="Bullseye Press Scraper Service")

#
# Configure application logging to current folder (./app.log)
#
def _configure_logging():
    try:
        log_path = os.environ.get("APP_LOG_FILE", "app.log")
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        log_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )
        file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
        file_handler.setFormatter(log_formatter)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(log_formatter)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        # Avoid duplicating handlers if reloaded
        if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
            root.addHandler(file_handler)
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            root.addHandler(stream_handler)
    except Exception:
        # Don't crash on logging setup issues
        pass


_configure_logging()
run_migrations()

# Start scheduler on import (when app starts)
_scheduler = start_scheduler()

app.include_router(health_router)
app.include_router(jobs_router)


