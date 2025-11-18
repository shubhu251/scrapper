import os
import subprocess
import sys
import json
import logging
from typing import Tuple, Optional, List
from datetime import datetime

from .notifier import send_telegram_message
from .db import get_mysql_connection


def _build_source_folder(spider_name: str) -> str:
    return ''.join(part.capitalize() for part in spider_name.split('_'))


def _find_latest_output_file(spider_name: str) -> Optional[str]:
    """Locate the most recent JSON output for the given spider based on folder convention."""
    try:
        data_dir = os.environ.get("DATA_DIR", "data")
        date_dir = datetime.now().strftime("%Y-%m-%d")
        source_folder = _build_source_folder(spider_name)
        base_dir = os.path.join(data_dir, date_dir, source_folder)
        if not os.path.isdir(base_dir):
            return None
        candidates: List[str] = [
            os.path.join(base_dir, f) for f in os.listdir(base_dir) if f.endswith(".json")
        ]
        if not candidates:
            return None
        # pick latest by modified time
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]
    except Exception:
        return None


def _count_records_in_json(path: str) -> Optional[int]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        return None
    except Exception:
        return None


def _normalize_name_for_db(name: str) -> str:
    """Convert name to uppercase with underscores (no spaces)."""
    if not name:
        return ""
    # Replace spaces with underscores, convert to uppercase
    return name.replace(" ", "_").upper()


def _infer_source_name(spider_name: str) -> str:
    """Map spider name to human-readable source name."""
    if spider_name == "bullseye_press":
        return "Bullseye Press"
    elif spider_name == "holy_cow":
        return "Holy Cow Entertainment"
    elif spider_name == "yali_dream_creations":
        return "Yali Dream Creations"
    # Fallback: capitalize parts
    return " ".join(part.capitalize() for part in spider_name.split("_"))


def _insert_scraped_data_into_db(spider_name: str, latest_file: Optional[str]) -> Optional[int]:
    """
    Read the aggregated JSON file and insert records into comics_data_dump table.
    Returns number of rows processed (inserted/updated), or None on failure.
    """
    logger = logging.getLogger("db")
    if not latest_file or not os.path.isfile(latest_file):
        logger.info("DB: No latest JSON file found for DB insertion")
        return None

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            logger.warning("DB: Latest JSON is not a list; skipping DB load")
            return None
    except Exception as e:
        logger.error(f"DB: Failed to read latest JSON file for DB load: {e}")
        return None

    conn = get_mysql_connection()
    if conn is None:
        return None

    source_name = _infer_source_name(spider_name)
    source_name_normalized = _normalize_name_for_db(source_name)
    processed = 0

    try:
        with conn.cursor() as cur:
            # Ensure source exists
            current_dt = datetime.now()
            try:
                cur.execute(
                    "INSERT IGNORE INTO sources (source, description, url, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (source_name_normalized, None, None, current_dt, current_dt),
                )
            except Exception as e:
                logger.error(f"DB: Failed to upsert source '{source_name_normalized}': {e}")

            # Helper function to check if item is a ComicItem based on schema
            def _is_comic_item(item: dict) -> bool:
                """Check if item matches ComicItem schema (has price, title, and url)."""
                return (
                    item.get("price") is not None and
                    item.get("title") is not None and
                    item.get("url") is not None
                )

            def _is_publisher_item(item: dict) -> bool:
                """Check if item matches PublisherItem schema (has name but no comic fields)."""
                return item.get("name") is not None and not _is_comic_item(item)

            # First, handle PublisherItems - these should go into sources table
            for it in items:
                if not isinstance(it, dict):
                    continue
                if _is_publisher_item(it):
                    try:
                        pub_name = it.get("name")
                        pub_name_normalized = _normalize_name_for_db(pub_name) if pub_name else None
                        pub_description = it.get("description")
                        pub_url = it.get("url") or it.get("website")
                        current_dt = datetime.now()
                        cur.execute(
                            "INSERT INTO sources (source, description, url, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE description = VALUES(description), url = VALUES(url), updated_at = %s",
                            (pub_name_normalized, pub_description, pub_url, current_dt, current_dt, current_dt),
                        )
                        logger.debug(f"DB: Upserted source '{pub_name_normalized}' into sources table")
                    except Exception as e:
                        logger.error(f"DB: Failed to insert source '{it.get('name')}': {e}")

            # Now handle ComicItems - these go into comics_data_dump
            sql = """
            INSERT INTO comics_data_dump (
                title, series_name, issue, language, binding,
                original_price, price, description, url, cover_image_url,
                source, scraped_at, uploaded_date, publisher, pages,
                status, failed_at, processed_at, failure_reason,
                writers, artists, colorists, genre, additional_info, raw_json,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                'CREATED', NULL, NULL, NULL,
                %s, %s, %s, %s, %s, %s,
                %s, %s
            )
            ON DUPLICATE KEY UPDATE
                updated_at = %s
            """

            for it in items:
                if not isinstance(it, dict):
                    continue
                # Only process ComicItems (skip PublisherItems and other types)
                if not _is_comic_item(it):
                    continue
                try:
                    title = it.get("title")
                    url = it.get("url")
                    if not url or not title:
                        continue  # url and title are required for comics_data_dump

                    series_name = it.get("series")
                    issue = it.get("issue")
                    language = it.get("language")
                    binding = it.get("binding")
                    original_price = it.get("original_price")
                    price = it.get("price")
                    description = it.get("description")
                    cover_image_url = it.get("cover_image_url")
                    scraped_at = it.get("scraped_at")
                    uploaded_date = it.get("listing_date")
                    publisher = it.get("publisher")
                    publisher_normalized = _normalize_name_for_db(publisher) if publisher else None
                    pages = it.get("pages")

                    writers = json.dumps(it.get("writers"), ensure_ascii=False) if it.get("writers") is not None else None
                    artists = json.dumps(it.get("artists"), ensure_ascii=False) if it.get("artists") is not None else None
                    colorists = json.dumps(it.get("colorists"), ensure_ascii=False) if it.get("colorists") is not None else None
                    genre = json.dumps(it.get("genre"), ensure_ascii=False) if it.get("genre") is not None else None
                    additional_info = json.dumps(it.get("additional_info"), ensure_ascii=False) if it.get("additional_info") is not None else None
                    raw_json = json.dumps(it, ensure_ascii=False)
                    current_dt = datetime.now()

                    cur.execute(
                        sql,
                        (
                            title, series_name, issue, language, binding,
                            original_price, price, description, url, cover_image_url,
                            source_name_normalized, scraped_at, uploaded_date, publisher_normalized, pages,
                            writers, artists, colorists, genre, additional_info, raw_json,
                            current_dt, current_dt, current_dt,
                        ),
                    )
                    processed += 1
                except Exception as e:
                    logger.error(f"DB: Failed to insert comic record for url={it.get('url')}: {e}")

        logger.info(f"DB: Inserted/updated {processed} records into comics_data_dump")
        return processed
    except Exception as e:
        logger.error(f"DB: Error during comics_data_dump insert batch: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_scrapy_spider(spider_name: str) -> Tuple[int, str]:
    """Run a scrapy spider by name and return (returncode, output_snippet)."""
    try:
        send_telegram_message(f"🟢 Starting job: <b>{spider_name}</b>")
        # Send Scrapy logs to a file in the current folder
        log_file = os.environ.get(
            "SCRAPER_LOG_FILE",
            os.environ.get("APP_LOG_FILE", "./app.log")
        )
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        cmd = [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            spider_name,
            "-s",
            f"LOG_FILE={log_file}",
            "-s",
            "LOG_LEVEL=INFO",
        ]
        result = subprocess.run(cmd, text=True, cwd=".")
        # We don't capture output because Scrapy logs write to scraper.log now
        output = f"Scrapy finished with code {result.returncode}. See {log_file}"
        if result.returncode != 0:
            # Try to attach last log snippet for context
            snippet = ""
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as lf:
                    lf.seek(0, os.SEEK_END)
                    size = lf.tell()
                    lf.seek(max(0, size - 4000))
                    snippet = lf.read()[-1000:]
            except Exception:
                pass
            send_telegram_message(
                f"🔴 Job failed: <b>{spider_name}</b>\nLog: {log_file}\n\n<pre>{snippet}</pre>"
            )
        else:
            # Find latest output and count records
            latest_file = _find_latest_output_file(spider_name)
            count = _count_records_in_json(latest_file) if latest_file else None
            # Push scraped data into DB
            db_processed = _insert_scraped_data_into_db(spider_name, latest_file)

            if count is not None:
                msg = (
                    f"✅ Job completed: <b>{spider_name}</b>\n"
                    f"Records: <b>{count}</b>\nFile: {latest_file}"
                )
                if db_processed is not None:
                    msg += f"\nDB rows processed: <b>{db_processed}</b>"
                send_telegram_message(msg)
            else:
                send_telegram_message(
                    f"✅ Job completed: <b>{spider_name}</b>\nLog: {log_file}"
                )
        return result.returncode, output
    except Exception as exc:
        send_telegram_message(f"🔴 Job error: <b>{spider_name}</b>\n{exc}")
        return 1, f"Exception while running spider '{spider_name}': {exc}"


def run_bullseye_spider() -> Tuple[int, str]:
    """Backward compatible helper for Bullseye Press spider."""
    return run_scrapy_spider("bullseye_press")


