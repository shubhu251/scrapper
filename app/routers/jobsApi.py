from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from ..tasks import run_scrapy_spider


router = APIRouter()


class TriggerRequest(BaseModel):
    job: str  # spider name to trigger, e.g., "bullseye_press"


@router.post("/trigger_job")
def trigger_scrape(payload: TriggerRequest, background_tasks: BackgroundTasks):
    try:
        # Fire-and-forget in background; logs will be written to the configured log file
        background_tasks.add_task(run_scrapy_spider, payload.job)
        return {"triggered": True}
    except Exception:
        return {"triggered": False}


