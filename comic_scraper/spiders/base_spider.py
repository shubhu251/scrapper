"""
Base spider class with common functionality for all comic scrapers
"""
import scrapy
from datetime import datetime
from comic_scraper.utils.helpers import get_current_timestamp, clean_text


class BaseComicSpider(scrapy.Spider):
    """Base class for all comic scrapers with common functionality"""
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'RANDOMIZE_DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
    }
    
    def __init__(self, *args, **kwargs):
        super(BaseComicSpider, self).__init__(*args, **kwargs)
        self.scraped_at = get_current_timestamp()
    
    def add_scraped_timestamp(self, item):
        """Add timestamp to item"""
        if hasattr(item, 'fields') and 'scraped_at' in item.fields:
            item['scraped_at'] = self.scraped_at
        return item
    
    def clean_item(self, item):
        """Clean item fields"""
        for field_name, field_value in item.items():
            if isinstance(field_value, str):
                item[field_name] = clean_text(field_value)
        return item
    
    def parse_error(self, response, error_msg="Failed to parse"):
        """Log parsing errors"""
        self.logger.error(f"{error_msg}: {response.url}")

