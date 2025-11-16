# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import json
import csv
from datetime import datetime
import os
import os


class ComicScraperPipeline:
    """Base pipeline that processes all items"""
    
    def process_item(self, item, spider):
        return item


class JsonExportPipeline:
    """Pipeline to export all items to a single JSON file incrementally (after validation)"""
    
    def __init__(self):
        self.filename = None
        self.item_count = 0
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.data_dir = os.environ.get('DATA_DIR', 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.sub_dir = None
    
    def open_spider(self, spider):
        """Initialize single JSON file when spider opens"""
        # Determine source folder name from spider name (e.g., bullseye_press -> BullseyePress)
        source_folder = ''.join(word.capitalize() for word in spider.name.split('_'))
        # Date directory in format YYYY-MM-DD
        now = datetime.now()
        date_dir = now.strftime('%Y-%m-%d')
        # Create dated subfolder: data/YYYY-MM-DD/<SourceFolder>/
        self.sub_dir = os.path.join(self.data_dir, date_dir, source_folder)
        os.makedirs(self.sub_dir, exist_ok=True)
        # File format: YYYY-MM-DD-hh-mm-sss-am.json (milliseconds + am/pm)
        ms = now.strftime('%f')[:3]
        ampm = now.strftime('%p').upper()
        file_ts = now.strftime(f'%Y-%m-%d-%I-%M-%S-{ms}-{ampm}')
        self.filename = os.path.join(self.sub_dir, f'{file_ts}.json')
        
        # Initialize with empty array
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        
        spider.logger.info(f'Initialized JSON file: {self.filename}')
    
    def process_item(self, item, spider):
        """Write item to single JSON file immediately after validation"""
        adapter = ItemAdapter(item)
        item_dict = dict(adapter)
        
        if not self.filename:
            # Fallback if open_spider wasn't called
            now = datetime.now()
            source_folder = ''.join(word.capitalize() for word in spider.name.split('_'))
            date_dir = now.strftime('%Y-%m-%d')
            if not self.sub_dir:
                self.sub_dir = os.path.join(self.data_dir, date_dir, source_folder)
                os.makedirs(self.sub_dir, exist_ok=True)
            ms = now.strftime('%f')[:3]
            ampm = now.strftime('%p').upper()
            file_ts = now.strftime(f'%Y-%m-%d-%I-%M-%S-{ms}-{ampm}')
            self.filename = os.path.join(self.sub_dir, f'{file_ts}.json')
        
        try:
            # Read existing items
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    items_list = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                items_list = []
            
            # Append new item
            items_list.append(item_dict)
            self.item_count = len(items_list)
            
            # Write back to file atomically (write to temp file, then rename)
            temp_filename = self.filename + '.tmp'
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(items_list, f, ensure_ascii=False, indent=2)
            
            # Atomic rename (works on Unix/Linux/Mac, Windows may need different approach)
            try:
                os.replace(temp_filename, self.filename)
            except OSError:
                # Fallback: if rename fails, just use the temp file
                if os.path.exists(temp_filename):
                    if os.path.exists(self.filename):
                        os.remove(self.filename)
                    os.rename(temp_filename, self.filename)
            
            # Log item type for better visibility
            item_type = type(item).__name__.replace('Item', '')
            spider.logger.info(f'✓ Saved {item_type} to {self.filename} (total: {self.item_count} items)')
        except Exception as e:
            spider.logger.error(f'Error writing item to {self.filename}: {e}')
        
        return item
    
    def close_spider(self, spider):
        """Log final count when spider closes"""
        if self.item_count > 0:
            spider.logger.info(f'Final count: {self.item_count} items exported to {self.filename}')


class CsvExportPipeline:
    """Pipeline to export items to CSV files"""
    
    def __init__(self):
        self.data_dir = os.environ.get('DATA_DIR', 'data')
        self.items = {
            'publishers': [],
            'series': [],
            'comics': [],
            'genres': [],
            'characters': [],
            'artists': []
        }
    
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        item_dict = dict(adapter)
        
        # Categorize items by type
        if 'PublisherItem' in str(type(item)):
            self.items['publishers'].append(item_dict)
        elif 'SeriesItem' in str(type(item)):
            self.items['series'].append(item_dict)
        elif 'ComicItem' in str(type(item)):
            self.items['comics'].append(item_dict)
        elif 'GenreItem' in str(type(item)):
            self.items['genres'].append(item_dict)
        elif 'CharacterItem' in str(type(item)):
            self.items['characters'].append(item_dict)
        elif 'ArtistItem' in str(type(item)):
            self.items['artists'].append(item_dict)
        
        return item
    
    def close_spider(self, spider):
        """Export all items to CSV when spider closes"""
        os.makedirs(self.data_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for item_type, items_list in self.items.items():
            if items_list:
                filename = os.path.join(self.data_dir, f'{item_type}_{timestamp}.csv')
                if items_list:
                    fieldnames = set()
                    for item_dict in items_list:
                        fieldnames.update(item_dict.keys())
                    
                    with open(filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=sorted(fieldnames))
                        writer.writeheader()
                        for item_dict in items_list:
                            # Convert lists to strings for CSV
                            row = {}
                            for key, value in item_dict.items():
                                if isinstance(value, list):
                                    row[key] = ', '.join(str(v) for v in value if v)
                                else:
                                    row[key] = value
                            writer.writerow(row)
                    spider.logger.info(f'Exported {len(items_list)} {item_type} to {filename}')


class DuplicatesPipeline:
    """Pipeline to filter duplicate items based on URL"""
    
    def __init__(self):
        self.seen_urls = set()
    
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get('url')
        
        if url and url in self.seen_urls:
            spider.logger.debug(f'Duplicate item found: {url}')
            raise DropItem(f'Duplicate item found: {url}')
        else:
            if url:
                self.seen_urls.add(url)
            return item


class ValidationPipeline:
    """Pipeline to validate items have required fields"""
    
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Check for required fields based on item type
        if 'PublisherItem' in str(type(item)):
            if not adapter.get('name'):
                raise DropItem(f'Missing required field: name in {item}')
        
        elif 'SeriesItem' in str(type(item)):
            if not adapter.get('title'):
                raise DropItem(f'Missing required field: title in {item}')
        
        elif 'ComicItem' in str(type(item)):
            if not adapter.get('title'):
                raise DropItem(f'Missing required field: title in {item}')
        
        elif 'GenreItem' in str(type(item)):
            if not adapter.get('name'):
                raise DropItem(f'Missing required field: name in {item}')
        
        elif 'CharacterItem' in str(type(item)):
            if not adapter.get('name'):
                raise DropItem(f'Missing required field: name in {item}')
        
        elif 'ArtistItem' in str(type(item)):
            if not adapter.get('name'):
                raise DropItem(f'Missing required field: name in {item}')
        
        return item
