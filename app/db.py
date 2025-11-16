import os
import logging
from typing import Optional, List
from pathlib import Path

import pymysql


logger = logging.getLogger("db")


def get_mysql_connection() -> Optional[pymysql.connections.Connection]:
    """Create a MySQL connection from environment variables."""
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    database = os.environ.get("DB_NAME")

    if not all([host, user, password, database]):
        logger.warning("MySQL env vars not fully set; skipping DB connection")
        return None

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to MySQL: {e}")
        return None


def _load_sql_files() -> List[str]:
    """Load .sql files from migrations directory in lexical order."""
    try:
        base_dir = Path(__file__).resolve().parent.parent  # project root
        mig_dir = base_dir / "migrations"
        if not mig_dir.is_dir():
            logger.info("DB: No migrations directory found; skipping DB migrations")
            return []
        sql_files = sorted(mig_dir.glob("*.sql"))
        if not sql_files:
            logger.info("DB: No .sql files found in migrations directory; nothing to run")
            return []
        statements: List[str] = []
        for path in sql_files:
            try:
                sql = path.read_text(encoding="utf-8")
                statements.append(sql)
                logger.info(f"DB: Loaded migration file {path.name}")
            except Exception as e:
                logger.error(f"DB: Failed to read migration file {path}: {e}")
        return statements
    except Exception as e:
        logger.error(f"DB: Failed to load SQL migrations: {e}")
        return []


def run_migrations() -> None:
    """Run SQL migrations on startup using external .sql files (idempotent DDL recommended)."""
    sql_statements = _load_sql_files()
    if not sql_statements:
        return

    conn = get_mysql_connection()
    if conn is None:
        return

    try:
        with conn.cursor() as cur:
            for idx, stmt in enumerate(sql_statements, start=1):
                try:
                    logger.info(f"DB: Applying migration {idx}/{len(sql_statements)}")
                    cur.execute(stmt)
                    logger.info(f"DB: Migration {idx} applied successfully")
                except Exception as e:
                    logger.error(f"DB: Error applying migration {idx}: {e}")
        logger.info("DB: All MySQL migrations processed from migrations/*.sql")
    except Exception as e:
        logger.error(f"DB: Error applying MySQL migrations batch: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


