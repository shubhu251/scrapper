# Bullseye Press Scraper

A Scrapy-based web scraping project for collecting comic book data from Bullseye Press (https://bullseyepress.in). This project scrapes publisher information, comics, series, and artist information.

## Features

- **Comprehensive Data Extraction**: Scrapes comics with detailed metadata (title, series, issue, price, description, artists, writers, etc.)
- **Base Spider Class**: Common functionality shared across spiders
- **Data Export**: Automatic export to JSON format with timestamps
- **Data Validation**: Pipeline-based validation and duplicate detection
- **Helper Utilities**: Text cleaning, date parsing, and data normalization
- **Docker Support**: Easy deployment with Docker and Docker Compose

## Project Structure

```
comic_scraper/
├── __init__.py
├── items.py              # Data models (PublisherItem, ComicItem, SeriesItem, ArtistItem)
├── pipelines.py          # Data processing pipelines (validation, export, duplicates)
├── settings.py           # Scrapy configuration
├── utils/
│   ├── __init__.py
│   └── helpers.py        # Utility functions for data cleaning and parsing
└── spiders/
    ├── __init__.py
    ├── base_spider.py    # Base class for all spiders
    └── bullseye_press_spider.py  # Spider for Bullseye Press
```

## Installation

### Local Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Docker Installation

The project includes Docker support for easy deployment:

1. **Using Docker Compose (Recommended)**:
```bash
# Build and run the scraper
docker-compose up --build

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

2. **Using Docker directly**:
```bash
# Build the image
docker build -t bullseye-scraper .

# Run the container
docker run --rm -v $(pwd)/data:/app/data bullseye-scraper

# Run with custom command
docker run --rm -v $(pwd)/data:/app/data bullseye-scraper python -m scrapy crawl bullseye_press
```

## Usage

### Running the Service (API + Cron + Migrations via Docker)
```bash
# Start the API service (scheduler reads jobs.yml)
docker-compose up --build

# API will be available at: http://localhost:8000
# Endpoints:
# - GET  /health          -> health check
# - POST /trigger_job     -> trigger a spider by name (fire-and-forget)
```

#### Using Python directly:
```bash
# Option 1: Use the runner script
python run_bullseye_press.py

# Option 2: Use Scrapy directly
scrapy crawl bullseye_press
```

#### Using Docker:
```bash
# Using Docker Compose
docker-compose up

# Using Docker directly
docker run --rm -v $(pwd)/data:/app/data bullseye-scraper
```

### Export Options

Data is automatically exported to the `data/` directory in JSON format with timestamps. The output file is named `Bullseye_Press_<date_time>.json`.

When using Docker, the data directory is mounted as a volume, so scraped data will be available in the `./data` directory on your host machine.

Output directory structure:
- Files are written under `DATA_DIR/<YYYY-MM-DD>/<SourceName>/`
- `<SourceName>` is derived from the spider name by capitalizing parts and removing underscores (e.g., `bullseye_press` -> `BullseyePress`).
- Filenames include seconds and milliseconds: `YYYY-MM-DD-hh-mm-ss-SSS-AM/PM.json`
- Example (for bullseye_press): `data/2025-11-25/BullseyePress/2025-11-25-09-27-45-123-AM.json`

## Configuration

Environment variables (set in `docker-compose.yml`):
- `CRON_EXPRESSION`: Cron in UTC for single scheduled job (fallback; default: `0 20 * * *` = 02:00 IST)
- `SCHEDULES_FILE`: Path to YAML schedules file (default: `jobs.yml`)
- `APP_LOG_FILE`: API/scheduler log file path (default: `/app/logs/app.log` in container, mapped to `./logs/app.log` on host)
- `SCRAPER_LOG_FILE`: Scrapy run log file path. If not set, it uses `APP_LOG_FILE` (so both logs go into one file).
- `DATA_DIR`: Directory where JSON data is written (default: `/app/data`, mapped to `./data` on host)
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: MySQL connection details used for migrations.

### Scheduling via YAML
Define multiple scheduled jobs in `jobs.yml` (times interpreted in the container TZ, default IST):
```yaml
jobs:
  - id: bullseye_daily
    type: spider          # 'spider' runs a scrapy spider by name
    target: bullseye_press
    cron: "0 20 * * *"    # 20:00 UTC daily (02:00 IST)
```
Notes:
- If `jobs.yml` is present, it takes precedence over `CRON_EXPRESSION`.
- Supported `type` values: `spider` (runs `scrapy crawl <target>`). `bullseye` alias is also supported for the Bullseye spider.

### Timezone
- The container timezone is set via `TZ` (default `Asia/Kolkata` from Dockerfile).
- The scheduler uses `TZ` when interpreting cron expressions. Set `TZ` to control default job timezone (e.g., `UTC`, `Asia/Kolkata`).
- You can optionally add `timezone` per job in `jobs.yml` to override `TZ`, but it's not required when the app runs in IST by default.

### Logs
### Trigger API
- Trigger a spider run by name (non-blocking; returns whether trigger was accepted):
```bash
curl -X POST http://localhost:8000/trigger_job \
  -H 'Content-Type: application/json' \
  -d '{"job":"bullseye_press"}'
```
Response:
```json
{"triggered": true}
```

### Telegram Alerts (optional)
- Configure `.env` with:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
- The service will send alerts when a job starts, completes, or fails. If env vars are missing, alerts are skipped.

- Logs are written to the container at `/app/logs/app.log` and are bind-mounted to your host at:
  - `/Users/Shubham/Documents/python/scrapper/logs/app.log`
  - You can change the path via `APP_LOG_FILE` and `SCRAPER_LOG_FILE` if needed.
  
#### Configure via .env
- Copy `env.sample` to `.env` and adjust:
```bash
cp env.sample .env
```
Edit `.env`:
```
APP_LOG_FILE=/app/logs/app.log
SCRAPER_LOG_FILE=/app/logs/app.log
# DB_HOST=your-mysql-host
# DB_PORT=3306
# DB_NAME=comics
# DB_USER=user
# DB_PASSWORD=secret
# TZ=Asia/Kolkata
# SCHEDULES_FILE=jobs.yml
# CRON_EXPRESSION=0 20 * * *
```
docker-compose automatically loads `.env`.

## Libraries and Frameworks Used

- Web scraping: `Scrapy`
- Timezone handling: `pytz` (fallback), Python `zoneinfo` where available
- API framework: `FastAPI`
- ASGI server: `uvicorn`
- Scheduling (cron-like): `APScheduler`
- Config: `PyYAML` for `jobs.yml`
- MySQL driver: `PyMySQL` (lightweight client for migrations from `migrations/*.sql`)

## Data Models

### PublisherItem
- name, website, description, url, scraped_at

### ComicItem
- title, series, issue, publisher, writers, artists, colorists, description, pages, price, original_price, isbn, cover_image_url, listing_date, language, binding, genre, additional_info, url, scraped_at

### SeriesItem
- title, publisher, url, scraped_at

### ArtistItem
- name, publisher, url, scraped_at

## Docker Configuration

### Dockerfile
The Dockerfile uses Python 3.11 slim image and installs all required dependencies. It automatically runs the spider when the container starts.

### docker-compose.yml
The docker-compose file includes:
- Volume mounting for the `data/` directory to persist scraped data
- Environment variables for Python output buffering
- Easy command override options

### Customizing Docker Setup

To modify the Docker setup:
1. Edit `Dockerfile` to change the base image or add dependencies
2. Edit `docker-compose.yml` to modify volumes, environment variables, or commands
3. Rebuild the image: `docker-compose build`

### Modifying Pipelines

Edit `comic_scraper/pipelines.py` to add custom processing:
- Database storage
- Image downloading
- Data enrichment
- API integration

## Configuration

Edit `comic_scraper/settings.py` to customize:
- Download delays
- Concurrent requests
- User agent
- Pipeline order
- Export settings

## Notes

- The spiders are designed to be respectful with download delays
- Robots.txt is respected by default (can be disabled in spider settings)
- All scraped data includes timestamps
- Duplicate items are automatically filtered

## Contributing

When adding support for new websites:
1. Analyze the website structure
2. Create appropriate CSS/XPath selectors
3. Test with a small sample first
4. Update documentation

## License

This project is for educational and research purposes. Please respect website terms of service and robots.txt files.

