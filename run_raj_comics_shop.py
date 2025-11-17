#!/usr/bin/env python3
"""
Quick start script to run the Raj Comics spider
"""
import subprocess
import sys

if __name__ == '__main__':
    print("Starting Raj Comics scraper...")
    print("=" * 50)
    
    # Run the spider
    result = subprocess.run(
        [sys.executable, '-m', 'scrapy', 'crawl', 'raj_comics_shop'],
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

