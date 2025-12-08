"""
Spider for scraping ComicsAdda website (https://comicsadda.com/)
This spider extracts publisher info, comics, series, and artist information.
OpenCart-based e-commerce platform.
"""
from comic_scraper.spiders.base_spider import BaseComicSpider
from comic_scraper.items import PublisherItem, ComicItem, SeriesItem, ArtistItem
from comic_scraper.utils.helpers import clean_text, normalize_list, extract_numbers, parse_date
from comic_scraper.constants import MIN_PAGES, MAX_PAGES
import re


class ComicsAddaSpider(BaseComicSpider):
    """
    Spider to scrape ComicsAdda website.
    Extracts publisher information, comics, series, and artist data.
    
    Usage:
        scrapy crawl comics_adda
    """
    
    name = 'comics_adda'
    allowed_domains = ['comicsadda.com']
    start_urls = ['https://comicsadda.com/']
    
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'RANDOMIZE_DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'ROBOTSTXT_OBEY': False,  # Some sites don't have proper robots.txt
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visited_urls = set()
        self.publisher_yielded = False
        self.got_404 = False  # Flag to track if we got a 404 error
    
    def parse(self, response):
        """
        Parse the homepage/shop page and extract comic listings.
        Also extract publisher information.
        """
        # Check for 404 error - stop pagination if we get 404
        if response.status == 404:
            self.got_404 = True
            self.logger.warning(f"Got 404 error on {response.url}, stopping pagination")
            return
        
        # Extract publisher information only once
        if not self.publisher_yielded:
            yield self.extract_publisher_info(response)
            self.publisher_yielded = True
        
        # Multiple strategies to find product links
        product_links = set()
        
        # Strategy 1: Find all product links using OpenCart selectors
        product_selectors = [
            '.product-layout a::attr(href)',
            '.product-grid a::attr(href)',
            '.product-item a::attr(href)',
            '.product-thumb a::attr(href)',
            'a[href*="/product/"]::attr(href)',
            'a[href*="route=product/product"]::attr(href)',
            '.product-list a::attr(href)',
        ]
        
        for selector in product_selectors:
            links = response.css(selector).getall()
            for link in links:
                if link and ('/product/' in link or 'route=product/product' in link):
                    full_url = response.urljoin(link)
                    if full_url not in self.visited_urls:
                        product_links.add(full_url)
        
        # Strategy 2: Find all links that contain product in the URL
        all_links = response.css('a::attr(href)').getall()
        for link in all_links:
            if link and ('/product/' in link or 'route=product/product' in link):
                full_url = response.urljoin(link)
                if full_url not in self.visited_urls and full_url not in product_links:
                    product_links.add(full_url)
        
        self.logger.info(f"Found {len(product_links)} product links on {response.url}")
        
        # Follow all product links
        for product_link in product_links:
            self.visited_urls.add(product_link)
            yield response.follow(
                product_link,
                callback=self.parse_product_detail,
                dont_filter=True
            )
        
        # Stop pagination if no products found on a paginated page
        if not product_links and ('page=' in response.url or '/page/' in response.url):
            self.logger.info(f"No products found on {response.url}, stopping pagination")
            return
        
        # Handle pagination - OpenCart typically uses ?page=X or route=product/category&page=X
        pagination_links = set()
        
        # Strategy 1: Next page link
        next_selectors = [
            'a[rel="next"]::attr(href)',
            '.pagination .next::attr(href)',
            '.pagination a:contains("Next")::attr(href)',
            '.pagination a:contains(">")::attr(href)',
        ]
        for selector in next_selectors:
            next_link = response.css(selector).get()
            if next_link:
                full_url = response.urljoin(next_link)
                if full_url and full_url not in self.visited_urls and full_url != response.url:
                    pagination_links.add(full_url)
                    break
        
        # Strategy 2: Get page number links
        if not pagination_links:
            # Extract current page number
            current_page = 1
            page_match = re.search(r'[?&]page=(\d+)', response.url)
            if page_match:
                current_page = int(page_match.group(1))
            
            # Get all page number links
            page_number_selectors = [
                '.pagination a::attr(href)',
                '.pagination li a::attr(href)',
            ]
            for selector in page_number_selectors:
                links = response.css(selector).getall()
                for link in links:
                    if not link:
                        continue
                    full_url = response.urljoin(link)
                    if full_url == response.url or full_url in self.visited_urls:
                        continue
                    
                    # Extract page number from the link
                    link_page_match = re.search(r'[?&]page=(\d+)', full_url)
                    if link_page_match:
                        link_page = int(link_page_match.group(1))
                        # Only follow if it's the next page or a future page
                        if link_page > current_page:
                            pagination_links.add(full_url)
                            break
        
        # Strategy 3: Construct next page URL manually
        if not pagination_links:
            current_page = 1
            base_url = response.url.split('?')[0]
            
            # Check if URL contains page number
            page_match = re.search(r'[?&]page=(\d+)', response.url)
            if page_match:
                current_page = int(page_match.group(1))
            
            # Construct next page URL
            next_page = current_page + 1
            if '?' in response.url:
                next_page_url = f"{base_url}?page={next_page}"
            else:
                next_page_url = f"{base_url}?page={next_page}"
            
            if next_page_url not in self.visited_urls and next_page_url != response.url:
                pagination_links.add(next_page_url)
                self.logger.info(f"Constructed next page URL: {next_page_url}")
        
        # Only follow pagination if we found a valid next page link and haven't got 404
        if pagination_links and not self.got_404:
            self.logger.info(f"Found {len(pagination_links)} pagination link(s) on {response.url}")
            for pagination_link in pagination_links:
                if pagination_link not in self.visited_urls:
                    self.visited_urls.add(pagination_link)
                    yield response.follow(
                        pagination_link,
                        callback=self.parse,
                        dont_filter=True,
                        errback=self.handle_http_error
                    )
                    break  # Only follow one pagination link at a time
        else:
            if self.got_404:
                self.logger.info(f"Stopped pagination due to 404 error")
            else:
                self.logger.info(f"No more pagination links found on {response.url}, reached end of pages")
    
    def handle_http_error(self, failure):
        """Handle HTTP errors, especially 404"""
        if failure.value.response:
            status = failure.value.response.status
            url = failure.value.response.url
            if status == 404:
                self.got_404 = True
                self.logger.warning(f"Got 404 error on {url}, stopping pagination")
            else:
                self.logger.error(f"HTTP error {status} on {url}")
        else:
            self.logger.error(f"Request failed: {failure}")
    
    def extract_publisher_info(self, response):
        """Extract publisher information from the website"""
        item = PublisherItem()
        item['name'] = 'ComicsAdda'
        item['website'] = 'https://comicsadda.com'
        item['url'] = 'https://comicsadda.com'
        
        # Try to extract description from about page or footer
        description = response.css('.about-us p::text, footer p::text, .site-description::text').get()
        if not description:
            description = 'Online comic book store offering a wide range of Indian and international comics'
        item['description'] = clean_text(description)
        
        item = self.add_scraped_timestamp(item)
        item = self.clean_item(item)
        return item
    
    def parse_product_detail(self, response):
        """
        Parse individual product/comic detail page.
        Extract comprehensive comic information.
        """
        item = None
        try:
            item = ComicItem()
            
            # Extract title
            title = response.css('h1::text, .product-title::text, .product-name h1::text').get()
            if not title:
                title = response.css('h1.product-title::text').get()
            item['title'] = clean_text(title)
            
            # Extract publisher - ComicsAdda is a seller/retailer, Brand field contains the actual publisher
            publisher = None
            
            # Strategy 1: Extract from Brand/Manufacturer field (most reliable in OpenCart)
            # OpenCart typically displays brand as: <span>Brand:</span> <a href="...">Brand Name</a>
            brand_selectors = [
                'a[href*="manufacturer"]::text',  # Brand link with manufacturer in href
                'a[href*="brand"]::text',  # Brand link alternative
                '.manufacturer a::text',  # Manufacturer link
                '.brand a::text',  # Brand link
                'span:contains("Brand") + a::text',  # Brand label followed by link
                'span:contains("Manufacturer") + a::text',  # Manufacturer label followed by link
                'td:contains("Brand") + td a::text',  # Brand in table with link
                'td:contains("Manufacturer") + td a::text',  # Manufacturer in table with link
                '.manufacturer::text',  # Direct text (fallback)
                '.brand::text',  # Direct text (fallback)
                '[itemprop="brand"]::text',  # Schema.org brand
                '.product-brand::text',  # Product brand class
            ]
            
            for selector in brand_selectors:
                brand_text = response.css(selector).get()
                if brand_text:
                    brand_text = clean_text(brand_text)
                    if brand_text and brand_text.lower() not in ['comicsadda', 'comics adda', 'n/a', 'none', '']:
                        publisher = brand_text
                        break
            
            # Strategy 2: Extract from product attributes table (Brand/Manufacturer column)
            if not publisher:
                # Look for Brand or Manufacturer in attribute tables
                attribute_rows = response.css('.attribute tr, .product-attributes tr, table.attribute tr, .product-info tr')
                for row in attribute_rows:
                    # Get all text from the row
                    row_text = ' '.join(row.css('::text').getall()).lower()
                    key = clean_text(' '.join(row.css('td:first-child::text, th:first-child::text').getall()))
                    # Try to get value from link first (OpenCart often uses links), then fallback to text
                    value_links = row.css('td:last-child a::text, td:nth-child(2) a::text').getall()
                    value_text = row.css('td:last-child::text, td:nth-child(2)::text').getall()
                    value = clean_text(' '.join(value_links if value_links else value_text))
                    
                    if key and value:
                        key_lower = key.lower()
                        # Check if this row is about brand/manufacturer
                        if ('brand' in key_lower or 'manufacturer' in key_lower or 'publisher' in key_lower):
                            if value.lower() not in ['comicsadda', 'comics adda', 'n/a', 'none', '']:
                                publisher = value
                                break
                    
                    # Also check if brand/manufacturer appears in the row text
                    if not publisher and ('brand' in row_text or 'manufacturer' in row_text):
                        # Try to extract the value part
                        value_cells = row.css('td:last-child a::text, td:last-child::text, td:nth-child(2) a::text, td:nth-child(2)::text').getall()
                        for val in value_cells:
                            val_clean = clean_text(val)
                            if val_clean and val_clean.lower() not in ['comicsadda', 'comics adda', 'n/a', 'none', '']:
                                publisher = val_clean
                                break
                        if publisher:
                            break
            
            # Strategy 3: Extract from product description (look for PUBLISHED/PRODUCED BY patterns)
            if not publisher:
                desc_text = ' '.join(response.css('.product-description::text, .description::text, #tab-description::text').getall())
                if desc_text:
                    # Look for "PUBLISHED BY" or "PRODUCED BY" patterns
                    published_match = re.search(r'published\s+by\s+([^\.\n]+)', desc_text, re.IGNORECASE)
                    if published_match:
                        publisher = clean_text(published_match.group(1))
                    else:
                        produced_match = re.search(r'produced\s+by\s+([^\.\n]+)', desc_text, re.IGNORECASE)
                        if produced_match:
                            publisher = clean_text(produced_match.group(1))
            
            # Set publisher - ComicsAdda is a seller, not a publisher
            # Filter out invalid publisher values like "Brands", "Individual", etc.
            invalid_publishers = ['brands', 'individual', 'comicsadda', 'comics adda', 'n/a', 'none', '']
            if publisher and publisher.lower() not in invalid_publishers:
                item['publisher'] = publisher
            else:
                item['publisher'] = 'Unknown'
            
            # Extract price information
            # OpenCart structure for this site:
            # <ul class="list-unstyled">
            #   <li><span style="text-decoration: line-through;">₹2,898.00INR</span></li>  (original price)
            #   <li><h2>₹2,339.00INR</h2></li>  (discounted price)
            # </ul>
            
            # Reset prices to ensure we extract from the correct product area
            item['price'] = None
            item['original_price'] = None
            
            # Strategy 1: Extract from list-unstyled structure (most common for this site)
            # Original price: span with line-through in list-unstyled
            original_price_text = response.css('ul.list-unstyled li span[style*="line-through"]::text, ul.list-unstyled li span:contains("₹")::text').get()
            if not original_price_text:
                # Try to get from first span in list-unstyled
                original_price_text = response.css('ul.list-unstyled li:first-child span::text').get()
            
            # Discounted price: h2 in list-unstyled
            discounted_price_text = response.css('ul.list-unstyled li h2::text').get()
            
            if original_price_text:
                price_num = extract_numbers(original_price_text)
                if price_num:
                    try:
                        item['original_price'] = float(price_num)
                    except (ValueError, TypeError):
                        pass
            
            if discounted_price_text:
                price_num = extract_numbers(discounted_price_text)
                if price_num:
                    try:
                        item['price'] = float(price_num)
                    except (ValueError, TypeError):
                        pass
            
            # Strategy 2: If we have both prices, we're done. Otherwise, extract all prices from list-unstyled
            if not item.get('price') or not item.get('original_price'):
                all_list_prices = response.css('ul.list-unstyled li span::text, ul.list-unstyled li h2::text').getall()
                price_values = []
                for price_text in all_list_prices:
                    if not price_text:
                        continue
                    price_num = extract_numbers(price_text)
                    if price_num:
                        try:
                            price_val = float(price_num)
                            if 10 <= price_val <= 100000:
                                price_values.append(price_val)
                        except (ValueError, TypeError):
                            pass
                
                if price_values:
                    unique_prices = sorted(list(set(price_values)))
                    if len(unique_prices) >= 2:
                        # Lower is discounted, higher is original
                        if not item.get('price'):
                            item['price'] = unique_prices[0]
                        if not item.get('original_price'):
                            item['original_price'] = unique_prices[1]
                    elif len(unique_prices) == 1:
                        if not item.get('price'):
                            item['price'] = unique_prices[0]
                        if not item.get('original_price'):
                            item['original_price'] = unique_prices[0]
            
            # Strategy 3: Fallback to OpenCart standard selectors
            if not item.get('price'):
                price_new_text = response.css('.price-new::text, .product-info .price-new::text').get()
                if price_new_text:
                    price_num = extract_numbers(price_new_text)
                    if price_num:
                        try:
                            item['price'] = float(price_num)
                        except (ValueError, TypeError):
                            pass
            
            if not item.get('original_price'):
                price_old_text = response.css('.price-old::text, .product-info .price-old::text').get()
                if price_old_text:
                    price_num = extract_numbers(price_old_text)
                    if price_num:
                        try:
                            item['original_price'] = float(price_num)
                        except (ValueError, TypeError):
                            pass
            
            # Final fallback: set missing prices
            if item.get('original_price') and not item.get('price'):
                item['price'] = item['original_price']
            if item.get('price') and not item.get('original_price'):
                item['original_price'] = item['price']
            
            # Extract description
            description_text = []
            
            # Strategy 1: Get description from product description section
            desc_selectors = [
                '.product-description::text',
                '.description::text',
                '#tab-description::text',
                '.tab-content .description::text',
            ]
            for selector in desc_selectors:
                desc_parts = response.css(selector).getall()
                if desc_parts:
                    description_text.extend([clean_text(d) for d in desc_parts if clean_text(d)])
                    break
            
            # Strategy 2: Get all text from description tab
            if not description_text:
                desc_tab = response.css('#tab-description, .tab-description, .product-description')
                if desc_tab:
                    desc_text = ' '.join(desc_tab.css('::text').getall())
                    if desc_text:
                        description_text.append(clean_text(desc_text))
            
            if description_text:
                item['description'] = ' '.join(description_text)
            
            # Extract series information from title
            if item.get('title'):
                title = item['title']
                
                # Extract series name - stop at Issue, Vol./Volume, Stage, colon, dash, or hash
                series_match = re.search(r'^(.+?)(?:\s+Issue\s+\d+|\s+Vol\.|\s+Vol\s+\d+|\s+Volume\s+\d+|\s+Volume\s+|\s+Stage\s+\d+|[:–\-#]|\(Pre Booking\)|\(Prebooking\))', title, re.IGNORECASE)
                if not series_match:
                    # Fallback: if no Issue/Vol./Stage found, stop at colon, dash, or hash
                    series_match = re.search(r'^([^:–\-#(]+)', title)
                
                if series_match:
                    series_name = clean_text(series_match.group(1))
                    
                    # Clean up series name by removing common suffixes
                    series_name = re.sub(r'\s+English\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+English\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Issue\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Vol\.?\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Volume\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Stage\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    
                    # Remove other suffixes
                    invalid_suffixes = [
                        r'\s+Issue\s*$',
                        r'\s+Hardcover\s*$',
                        r'\s+Paperback\s*$',
                        r'\s+Variant\s*$',
                        r'\s+Regular\s+Cover\s*$',
                        r'\s+Pre\s+Booking\s*$',
                        r'\s+Prebooking\s*$',
                    ]
                    
                    for suffix_pattern in invalid_suffixes:
                        series_name = re.sub(suffix_pattern, '', series_name, flags=re.IGNORECASE).strip()
                    
                    # Check if the cleaned series name is valid
                    invalid_series_values = [
                        'Issue', 'issue', 'English', 'Hindi', 'Variant', 'Pre Booking', 'Prebooking'
                    ]
                    
                    if series_name and series_name not in invalid_series_values:
                        if len(series_name) > 2 and not series_name.isdigit():
                            item['series'] = series_name
                    
                    # Extract issue number
                    issue_match = re.search(r'Issue[-\s]*(\d+)', title, re.IGNORECASE)
                    if issue_match:
                        try:
                            item['issue'] = int(issue_match.group(1))
                        except ValueError:
                            pass
                    else:
                        # Try to extract number from title (e.g., "Vol. 3")
                        vol_match = re.search(r'Vol\.?\s*(\d+)', title, re.IGNORECASE)
                        if vol_match:
                            try:
                                item['issue'] = int(vol_match.group(1))
                            except ValueError:
                                pass
            
            # Extract language
            language = None
            title_lower = item.get('title', '').lower()
            desc_lower = item.get('description', '').lower() if item.get('description') else ''
            
            if 'hindi' in title_lower or 'hindi' in desc_lower:
                language = 'Hindi'
            elif 'english' in title_lower or 'english' in desc_lower:
                language = 'English'
            elif 'malayalam' in title_lower or 'malayalam' in desc_lower:
                language = 'Malayalam'
            elif 'bangla' in title_lower or 'bengali' in title_lower:
                language = 'Bengali'
            
            if language:
                item['language'] = language
            
            # Extract binding information
            binding = None
            title_lower = item.get('title', '').lower()
            desc_lower = item.get('description', '').lower() if item.get('description') else ''
            
            # Check title and description for binding keywords
            binding_patterns = [
                (r'\b(hardbound|hard\s*bound|hb)\b', 'Hardbound'),
                (r'\b(paperback|paper\s*back|pb)\b', 'Paperback'),
                (r'\b(hardcover|hard\s*cover|hc)\b', 'Hardcover'),
                (r'\b(softcover|soft\s*cover)\b', 'Softcover'),
                (r'\b(deluxe\s*edition)\b', 'Deluxe Edition'),
            ]
            
            for pattern, binding_value in binding_patterns:
                if re.search(pattern, title_lower) or (desc_lower and re.search(pattern, desc_lower)):
                    binding = binding_value
                    break
            
            if binding:
                item['binding'] = binding
            
            # Extract pages from description and other sources
            pages = None
            desc_text = item.get('description', '') if item.get('description') else ''
            title_text = item.get('title', '')
            
            # Strategy 1: Look for pages in description with various patterns
            if desc_text:
                # Pattern 1: "Pages: 48", "Pages 48", "48 Pages", "Page: 48", "Page 48"
                pages_patterns = [
                    r'pages?[:\s]+(\d+)',  # "Pages: 48" or "Pages 48"
                    r'(\d+)\s*pages?',  # "48 Pages" or "48 pages"
                    r'page\s+count[:\s]+(\d+)',  # "Page Count: 48"
                    r'no\s+of\s+pages?[:\s]+(\d+)',  # "No of Pages: 48"
                    r'number\s+of\s+pages?[:\s]+(\d+)',  # "Number of Pages: 48"
                ]
                
                for pattern in pages_patterns:
                    pages_match = re.search(pattern, desc_text, re.IGNORECASE)
                    if pages_match:
                        try:
                            pages = int(pages_match.group(1))
                            # Validate page count using constants
                            if MIN_PAGES <= pages <= MAX_PAGES:
                                break
                        except (ValueError, TypeError):
                            continue
            
            # Strategy 2: Look for pages in title
            if not pages and title_text:
                pages_match = re.search(r'(\d+)\s*pages?', title_text, re.IGNORECASE)
                if pages_match:
                    try:
                        pages = int(pages_match.group(1))
                    except ValueError:
                        pass
            
            # Strategy 3: Extract from raw description HTML/text (before cleaning)
            if not pages:
                # Get raw description from response
                raw_desc_text = ' '.join(response.css('.product-description::text, .description::text, #tab-description::text').getall())
                if raw_desc_text:
                    # Try same patterns on raw description
                    pages_patterns = [
                        r'pages?[:\s]+(\d+)',
                        r'(\d+)\s*pages?',
                        r'page\s+count[:\s]+(\d+)',
                        r'no\s+of\s+pages?[:\s]+(\d+)',
                        r'number\s+of\s+pages?[:\s]+(\d+)',
                    ]
                    
                    for pattern in pages_patterns:
                        pages_match = re.search(pattern, raw_desc_text, re.IGNORECASE)
                        if pages_match:
                            try:
                                pages = int(pages_match.group(1))
                                # Validate page count using constants
                                if MIN_PAGES <= pages <= MAX_PAGES:
                                    break
                            except (ValueError, TypeError):
                                continue
            
            # Validate page count using constants before setting
            if pages and MIN_PAGES <= pages <= MAX_PAGES:
                item['pages'] = pages
            
            # Extract cover image - prioritize highest quality and filter out placeholder images
            # OpenCart typically has multiple image sizes: thumbnail (300x300), medium, large, and original
            cover_image = None
            
            # List of known placeholder/fallback image patterns to exclude
            placeholder_patterns = [
                'caravan/img-20230503-wa0003',  # Generic placeholder
                'placeholder',
                'no-image',
                'default',
                'calogor.png',  # Generic catalog placeholder
            ]
            
            def is_placeholder_image(url):
                """Check if image is a placeholder"""
                if not url:
                    return True
                url_lower = url.lower()
                return any(pattern in url_lower for pattern in placeholder_patterns)
            
            def construct_larger_image_url(url):
                """Try to construct larger image URL from thumbnail URL"""
                if not url:
                    return None
                
                # OpenCart image URL patterns:
                # Thumbnail: /image/cache/catalog/.../image-300x300.jpg
                # Original: /image/catalog/.../image.jpg (remove /cache/ and size suffix)
                # Larger cached: /image/cache/catalog/.../image-700x700.jpg
                
                url_lower = url.lower()
                
                # If it's a cached thumbnail, try to get larger versions
                if '/image/cache/catalog/' in url_lower:
                    # Try 700x700 first (common large size) - preserve original case
                    larger_url = re.sub(r'-\d+x\d+\.(jpg|jpeg|png|webp)', r'-700x700.\1', url, flags=re.IGNORECASE)
                    if larger_url != url:
                        return larger_url
                    
                    # Try 800x800 - preserve original case
                    larger_url = re.sub(r'-\d+x\d+\.(jpg|jpeg|png|webp)', r'-800x800.\1', url, flags=re.IGNORECASE)
                    if larger_url != url:
                        return larger_url
                
                # Try to get original (remove cache and size suffix) - preserve case
                if '/image/cache/catalog/' in url_lower:
                    # Remove /cache/ from path (case-insensitive)
                    original_url = re.sub(r'/image/cache/catalog/', '/image/catalog/', url, flags=re.IGNORECASE)
                    # Remove size suffix like -300x300, -700x700, etc.
                    original_url = re.sub(r'-\d+x\d+\.(jpg|jpeg|png|webp)', r'.\1', original_url, flags=re.IGNORECASE)
                    return original_url
                
                return None
            
            # Function to get image quality score (higher is better)
            def get_image_quality_score(url):
                """Score image quality based on URL patterns"""
                if not url or is_placeholder_image(url):
                    return -1  # Reject placeholders
                
                url_lower = url.lower()
                score = 0
                
                # Prefer larger images
                if '-300x300' in url_lower or '-300x' in url_lower:
                    score = 1  # Thumbnail - lowest priority
                elif '-600x600' in url_lower or '-600x' in url_lower:
                    score = 2  # Medium
                elif '-700x700' in url_lower or '-700x' in url_lower:
                    score = 5  # Large (700x700) - preferred
                elif '-800x800' in url_lower or '-800x' in url_lower:
                    score = 6  # Extra large (800x800)
                elif '-1000x' in url_lower or '-1200x' in url_lower:
                    score = 7  # Very large
                elif any(size in url_lower for size in ['-300x', '-600x', '-700x', '-800x', '-1000x', '-1200x']):
                    # Has size suffix but not common sizes - medium priority
                    score = 2
                else:
                    # No size suffix - likely original/highest quality
                    score = 8  # Original/highest quality
                
                return score
            
            # Strategy 1: Look for thumbnail link (most reliable for this site)
            # Structure: <ul class="thumbnails"><li><a class="thumbnail" href="...700x700.jpg">
            thumbnail_link = response.css('ul.thumbnails a.thumbnail::attr(href)').get()
            if thumbnail_link and not is_placeholder_image(thumbnail_link):
                cover_image = thumbnail_link
            else:
                # Also try the img src inside thumbnail
                thumbnail_img = response.css('ul.thumbnails img::attr(src)').get()
                if thumbnail_img and not is_placeholder_image(thumbnail_img):
                    # Try to construct larger version
                    larger_url = construct_larger_image_url(thumbnail_img)
                    if larger_url:
                        cover_image = larger_url
                    else:
                        cover_image = thumbnail_img
            
            # Strategy 2: Look for high-quality image attributes in main product image area
            if not cover_image:
                # OpenCart main product image is usually in .col-sm-6 or .product-info area
                main_product_area = response.css('.col-sm-6:first-child, .col-sm-8, .product-info, .product-image, #product, .col-md-6:first-child')
                
                high_quality_selectors = [
                    'img::attr(data-zoom-image)',
                    'img::attr(data-large-image)',
                    'img::attr(data-full-image)',
                    'img::attr(data-src)',
                    'img::attr(src)',
                ]
                
                for area in main_product_area:
                    for selector in high_quality_selectors:
                        img_url = area.css(selector).get()
                        if img_url and not is_placeholder_image(img_url):
                            # Try to get larger version
                            larger_url = construct_larger_image_url(img_url)
                            if larger_url:
                                cover_image = larger_url
                            else:
                                cover_image = img_url
                            break
                    if cover_image:
                        break
            
            # Strategy 3: Get main product image from product image container
            if not cover_image:
                # Look specifically in product image containers with multiple selectors
                product_image_selectors = [
                    '.product-image img::attr(data-zoom-image)',
                    '.product-image img::attr(data-large-image)',
                    '.product-image img::attr(data-full-image)',
                    '.image img::attr(data-zoom-image)',
                    '#product-image img::attr(data-zoom-image)',
                    'img.product-image::attr(data-zoom-image)',
                    '.product-image img::attr(src)',
                    '.image img::attr(src)',
                    '#product-image img::attr(src)',
                    'img.product-image::attr(src)',
                    '.thumbnails img::attr(data-zoom-image)',
                    '.thumbnails img::attr(src)',
                ]
                
                for selector in product_image_selectors:
                    img_url = response.css(selector).get()
                    if img_url and not is_placeholder_image(img_url):
                        # Try to get larger version
                        larger_url = construct_larger_image_url(img_url)
                        if larger_url:
                            cover_image = larger_url
                        else:
                            cover_image = img_url
                        break
            
            # Strategy 4: Get all images from product area, filter and select best
            if not cover_image:
                all_images = []
                
                # Collect from main product area only
                for area in main_product_area:
                    images = area.css('img::attr(src), img::attr(data-src), img::attr(data-zoom-image)').getall()
                    for img_url in images:
                        if img_url and img_url not in all_images and not is_placeholder_image(img_url):
                            all_images.append(img_url)
                
                if all_images:
                    # Try to construct larger versions for thumbnails
                    processed_images = []
                    for img_url in all_images:
                        larger_url = construct_larger_image_url(img_url)
                        if larger_url and larger_url not in processed_images:
                            processed_images.append(larger_url)
                        elif img_url not in processed_images:
                            processed_images.append(img_url)
                    
                    # Filter and sort by quality
                    valid_images = [img for img in processed_images if not is_placeholder_image(img)]
                    if valid_images:
                        valid_images.sort(key=get_image_quality_score, reverse=True)
                        cover_image = valid_images[0]
            
            # Strategy 5: Get images from left column (product image area) - exclude right column (product info)
            if not cover_image:
                # OpenCart typically has product image in left column
                left_column_images = response.css('.col-sm-6:first-child img::attr(src), .col-md-6:first-child img::attr(src), .col-lg-6:first-child img::attr(src)').getall()
                valid_images = [img for img in left_column_images if img and not is_placeholder_image(img)]
                if valid_images:
                    # Try to get larger version of first valid image
                    first_img = valid_images[0]
                    larger_url = construct_larger_image_url(first_img)
                    cover_image = larger_url if larger_url else first_img
            
            # Strategy 6: Fallback - get ANY image from page (excluding related products area)
            if not cover_image:
                # Exclude related products, thumbnails from other products
                excluded_areas = response.css('.related-products, .product-related, .product-layout, .product-grid')
                excluded_urls = set()
                for area in excluded_areas:
                    excluded_urls.update(area.css('img::attr(src)').getall())
                
                # Get all images from page
                all_page_images = response.css('img::attr(src), img::attr(data-src)').getall()
                # Filter out excluded images and placeholders
                valid_images = []
                for img_url in all_page_images:
                    if img_url and img_url not in excluded_urls:
                        # Only include images from comicsadda.com/image/ path
                        if '/image/' in img_url.lower():
                            # Prefer non-placeholder images, but include placeholders as last resort
                            if not is_placeholder_image(img_url):
                                valid_images.insert(0, img_url)  # Add to front
                            else:
                                valid_images.append(img_url)  # Add to end
                
                if valid_images:
                    # Try to get larger version of first valid image
                    first_img = valid_images[0]
                    larger_url = construct_larger_image_url(first_img)
                    cover_image = larger_url if larger_url else first_img
            
            # Strategy 7: Last resort - get first image from product area even if it might be placeholder
            if not cover_image:
                # Get first image from product area
                first_img = response.css('.col-sm-6:first-child img::attr(src), .product-info img::attr(src), .product-image img::attr(src)').get()
                if first_img and '/image/' in first_img.lower():
                    larger_url = construct_larger_image_url(first_img)
                    cover_image = larger_url if larger_url else first_img
            
            # Set the cover image URL (use the best quality image we found)
            if cover_image:
                item['cover_image_url'] = response.urljoin(cover_image)
            
            # Extract additional info from product attributes/description
            additional_info = {}
            
            # Try to extract from product attributes table
            attribute_rows = response.css('.attribute tr, .product-attributes tr')
            for row in attribute_rows:
                key = clean_text(' '.join(row.css('td:first-child::text, th:first-child::text').getall()))
                value = clean_text(' '.join(row.css('td:last-child::text, th:last-child::text').getall()))
                if key and value:
                    additional_info[key] = value
            
            # Extract pages from additional info if not already found
            if not item.get('pages') and additional_info:
                pages_text = additional_info.get('Pages') or additional_info.get('pages') or additional_info.get('Page Count')
                if pages_text:
                    pages_value = extract_numbers(pages_text)
                    if pages_value:
                        try:
                            item['pages'] = int(pages_value)
                        except (ValueError, TypeError):
                            pass
            
            # Extract binding from additional info if not already found
            if not item.get('binding') and additional_info:
                binding_text = additional_info.get('Binding') or additional_info.get('binding')
                if binding_text:
                    binding_text_lower = str(binding_text).lower().strip()
                    if 'hardbound' in binding_text_lower or 'hard bound' in binding_text_lower:
                        item['binding'] = 'Hardbound'
                    elif 'paperback' in binding_text_lower or 'paper back' in binding_text_lower:
                        item['binding'] = 'Paperback'
                    elif 'hardcover' in binding_text_lower or 'hard cover' in binding_text_lower:
                        item['binding'] = 'Hardcover'
                    elif 'softcover' in binding_text_lower:
                        item['binding'] = 'Softcover'
            
            if additional_info:
                item['additional_info'] = additional_info
            
            # Extract URL
            item['url'] = response.url
            
            # Extract release date if available
            release_date = None
            # Try to extract from description or additional info
            date_patterns = [
                r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',  # DD-MM-YYYY or DD/MM/YYYY
                r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
            ]
            
            desc_text = item.get('description', '') if item.get('description') else ''
            for pattern in date_patterns:
                date_match = re.search(pattern, desc_text)
                if date_match:
                    release_date = parse_date(date_match.group(1))
                    if release_date:
                        item['release_date'] = release_date
                        break
            
            # Set genre as empty array (can be extracted later if needed)
            item['genre'] = []
            
            # Add timestamp and clean
            item = self.add_scraped_timestamp(item)
            item = self.clean_item(item)
            
            yield item
            
        except Exception as e:
            self.logger.error(f"Error parsing product {response.url}: {str(e)}")
            if item:
                # Yield partial item if available
                item['url'] = response.url
                item = self.add_scraped_timestamp(item)
                item = self.clean_item(item)
                yield item

