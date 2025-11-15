# Comic Book Scraper Project

A modular Scrapy-based web scraping project for collecting comic book data from multiple websites. This project scrapes publisher information, series, comics, genres, characters, and artist information.

## Features

- **Modular Architecture**: Separate spiders for different data types (publishers, series, comics, genres, characters, artists)
- **Base Spider Class**: Common functionality shared across all spiders
- **Data Export**: Automatic export to JSON and CSV formats
- **Data Validation**: Pipeline-based validation and duplicate detection
- **Helper Utilities**: Text cleaning, date parsing, and data normalization

## Project Structure

```
comic_scraper/
├── __init__.py
├── items.py              # Data models (PublisherItem, SeriesItem, ComicItem, etc.)
├── pipelines.py          # Data processing pipelines (validation, export, duplicates)
├── settings.py           # Scrapy configuration
├── middlewares.py        # Custom middlewares
├── utils/
│   ├── __init__.py
│   └── helpers.py        # Utility functions for data cleaning and parsing
└── spiders/
    ├── __init__.py
    ├── base_spider.py    # Base class for all spiders
    ├── publisher_spider.py
    ├── series_spider.py
    ├── comic_spider.py
    ├── genre_spider.py
    ├── character_spider.py
    ├── artist_spider.py
    └── bullseye_press_spider.py  # Specific spider for Bullseye Press
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running Spiders

#### Bullseye Press Spider (Ready to Use)
```bash
scrapy crawl bullseye_press
```

#### Generic Spiders (Require Configuration)
```bash
# Scrape publishers
scrapy crawl publisher -a start_urls="https://example.com/publishers"

# Scrape series
scrapy crawl series -a start_urls="https://example.com/series"

# Scrape comics
scrapy crawl comic -a start_urls="https://example.com/comics"

# Scrape genres
scrapy crawl genre -a start_urls="https://example.com/genres"

# Scrape characters
scrapy crawl character -a start_urls="https://example.com/characters"

# Scrape artists
scrapy crawl artist -a start_urls="https://example.com/artists"
```

### Export Options

Data is automatically exported to the `data/` directory in both JSON and CSV formats with timestamps.

You can also use Scrapy's built-in export:
```bash
scrapy crawl bullseye_press -o output.json
scrapy crawl bullseye_press -o output.csv
```

## Data Models

### PublisherItem
- name, website, description, founded, headquarters, url, scraped_at

### SeriesItem
- title, publisher, description, start_date, end_date, issue_count, genre, url, scraped_at

### ComicItem
- title, series, issue_number, publisher, release_date, cover_artist, writers, artists, colorists, letterers, editors, characters, description, page_count, price, isbn, cover_image_url, url, scraped_at

### GenreItem
- name, description, url, scraped_at

### CharacterItem
- name, publisher, first_appearance, first_appearance_date, description, aliases, powers, teams, image_url, url, scraped_at

### ArtistItem
- name, role, bio, birth_date, nationality, notable_works, image_url, url, scraped_at

## Customization

### Adding a New Website Spider

1. Create a new spider file in `comic_scraper/spiders/`
2. Inherit from `BaseComicSpider`
3. Override the `parse()` method with website-specific selectors
4. Use the helper functions from `comic_scraper.utils.helpers`

Example:
```python
from comic_scraper.spiders.base_spider import BaseComicSpider
from comic_scraper.items import ComicItem

class MyWebsiteSpider(BaseComicSpider):
    name = 'my_website'
    start_urls = ['https://example.com/comics']
    
    def parse(self, response):
        # Your parsing logic here
        pass
```

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

