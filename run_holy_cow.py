#!/usr/bin/env python3
"""
Quick start script to run the Holy Cow Entertainment spider
"""
import subprocess
import sys

if __name__ == '__main__':
    print("Starting Holy Cow Entertainment scraper...")
    print("=" * 50)
    
    # Run the spider
    result = subprocess.run(
        [sys.executable, '-m', 'scrapy', 'crawl', 'holy_cow'],
        cwd='.'
    )
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("Scraping completed successfully!")
        print("Check the 'data/' directory for exported files.")
    else:
        print("\n" + "=" * 50)
        print("Scraping encountered errors. Check the output above.")
        sys.exit(result.returncode)

