"""
Spider for scraping Bullseye Press website (https://bullseyepress.in/)
This spider extracts publisher info, comics, series, and artist information.
"""
from comic_scraper.spiders.base_spider import BaseComicSpider
from comic_scraper.items import PublisherItem, ComicItem, SeriesItem, ArtistItem
from comic_scraper.utils.helpers import clean_text, normalize_list, extract_numbers, parse_date
from comic_scraper.constants import MIN_PAGES, MAX_PAGES
import re


class BullseyePressSpider(BaseComicSpider):
    """
    Spider to scrape Bullseye Press website.
    Extracts publisher information, comics, series, and artist data.
    
    Usage:
        scrapy crawl bullseye_press
    """
    
    name = 'bullseye_press'
    allowed_domains = ['bullseyepress.in']
    start_urls = ['https://bullseyepress.in/shop/']
    
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
        Parse the shop page and extract comic listings.
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
        
        # Strategy 1: Find all product links using various WooCommerce selectors
        product_selectors = [
            'li.product a::attr(href)',
            '.product a::attr(href)',
            'article.product a::attr(href)',
            '.woocommerce-loop-product__link::attr(href)',
            '.woocommerce ul.products li.product a::attr(href)',
            '.products li.product a::attr(href)',
            'a.woocommerce-LoopProduct-link::attr(href)',
            '.product-item a::attr(href)',
            'a[href*="/product/"]::attr(href)',
        ]
        
        for selector in product_selectors:
            links = response.css(selector).getall()
            for link in links:
                if link and '/product/' in link:
                    full_url = response.urljoin(link)
                    if full_url not in self.visited_urls:
                        product_links.add(full_url)
        
        # Strategy 2: Find all links that contain /product/ in the URL
        all_links = response.css('a::attr(href)').getall()
        for link in all_links:
            if link and '/product/' in link:
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
        if not product_links and '/page/' in response.url:
            self.logger.info(f"No products found on {response.url}, stopping pagination")
            return
        
        # Only handle pagination if we found products on this page
        if not product_links:
            self.logger.info(f"No products found on {response.url}, skipping pagination")
            return
        
        # Handle pagination - only follow links that actually exist on the page
        pagination_links = set()
        
        # Strategy 1: Next page link (most reliable - only exists if there's a next page)
        next_selectors = [
            'a.next::attr(href)',
            '.next.page-numbers::attr(href)',
            '.woocommerce-pagination a.next::attr(href)',
            'a[rel="next"]::attr(href)',
            '.pagination a.next::attr(href)',
            '.woocommerce-pagination .next::attr(href)',
        ]
        for selector in next_selectors:
            next_link = response.css(selector).get()
            if next_link:
                full_url = response.urljoin(next_link)
                # Make sure it's a valid URL and not already visited
                if full_url and full_url not in self.visited_urls and full_url != response.url:
                    pagination_links.add(full_url)
                    break  # Found a next link, no need to check other selectors
        
        # Strategy 2: Get page number links, but only if they're greater than current page
        # This prevents going backwards or to invalid pages
        if not pagination_links:
            # Extract current page number
            current_page = 1
            page_match = re.search(r'/page/(\d+)/?', response.url)
            if page_match:
                current_page = int(page_match.group(1))
            else:
                page_match = re.search(r'[?&]paged?=(\d+)', response.url)
                if page_match:
                    current_page = int(page_match.group(1))
            
            # Get all page number links
            page_number_selectors = [
                '.page-numbers a::attr(href)',
                '.woocommerce-pagination a::attr(href)',
                '.pagination a::attr(href)',
                'nav.pagination a::attr(href)',
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
                    link_page_match = re.search(r'/page/(\d+)/?', full_url)
                    if not link_page_match:
                        link_page_match = re.search(r'[?&]paged?=(\d+)', full_url)
                    
                    if link_page_match:
                        link_page = int(link_page_match.group(1))
                        # Only follow if it's the next page or a future page (not past pages)
                        if link_page > current_page:
                            pagination_links.add(full_url)
                            break  # Found a valid next page link
        
        # Strategy 4: Construct next page URL manually if no pagination links found
        # This ensures we continue pagination even if links aren't detected
        if not pagination_links:
            # Extract current page number
            current_page = 1
            base_url = response.url.split('?')[0].rstrip('/')
            
            # Check if URL contains page number
            page_match = re.search(r'/page/(\d+)/?', response.url)
            if page_match:
                current_page = int(page_match.group(1))
                # Remove /page/X/ from base URL
                base_url = re.sub(r'/page/\d+/?$', '', base_url)
            else:
                page_match = re.search(r'[?&]paged?=(\d+)', response.url)
                if page_match:
                    current_page = int(page_match.group(1))
            
            # Construct next page URL
            next_page = current_page + 1
            
            # Handle different base URL patterns
            if '/shop' in base_url:
                # If base URL contains /shop, construct /shop/page/X/ or /page/X/
                if base_url.endswith('/shop'):
                    next_page_url = f"{base_url}/page/{next_page}/"
                elif base_url.endswith('/shop/'):
                    next_page_url = f"{base_url}page/{next_page}/"
                else:
                    # Remove /shop/ and add /page/X/
                    base_without_shop = base_url.replace('/shop', '').rstrip('/')
                    next_page_url = f"{base_without_shop}/page/{next_page}/"
            else:
                # Default: add /page/2/ etc. to root
                next_page_url = f"{base_url}/page/{next_page}/"
            
            if next_page_url not in self.visited_urls and next_page_url != response.url:
                pagination_links.add(next_page_url)
                self.logger.info(f"Constructed next page URL: {next_page_url}")
        
        # Strategy 3: Load more button (AJAX pagination) - only if it exists
        if not pagination_links:
            load_more_selectors = [
                'a.load-more::attr(href)',
                'button.load-more::attr(data-url)',
                '.load-more::attr(data-url)',
                '[data-page]::attr(data-url)',
            ]
            for selector in load_more_selectors:
                load_more = response.css(selector).get()
                if load_more:
                    full_url = response.urljoin(load_more)
                    if full_url and full_url not in self.visited_urls and full_url != response.url:
                        pagination_links.add(full_url)
                        break
        
        # Only follow pagination if we found a valid next page link and haven't got 404
        if pagination_links and not self.got_404:
            self.logger.info(f"Found {len(pagination_links)} pagination link(s) on {response.url}")
            # Only follow the first/next pagination link to avoid duplicates
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
        item['name'] = 'Bullseye Press'
        item['website'] = 'https://bullseyepress.in'
        item['url'] = 'https://bullseyepress.in'
        
        # Try to extract description from about page or footer
        description = response.css('.site-description::text, footer p::text').get()
        if not description:
            description = 'Indian comic book publisher'
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
            title = response.css('h1.product_title::text, h1.entry-title::text, .product-title::text').get()
            if not title:
                title = response.css('h1::text').get()
            item['title'] = clean_text(title)
            
            # Extract publisher
            item['publisher'] = 'Bullseye Press'
            
            # Extract price information
            # WooCommerce typically structures prices as:
            # <span class="price">
            #   <del><span class="woocommerce-Price-amount">₹449</span></del>  (original price)
            #   <ins><span class="woocommerce-Price-amount">₹404</span></ins>  (discounted price)
            # </span>
            
            # Strategy 1: Extract original price from <del> tag (strikethrough)
            original_price = response.css('.price del .woocommerce-Price-amount::text, .price del .amount::text, .price del bdi::text, .original-price::text').get()
            if original_price:
                original_price_value = extract_numbers(original_price)
                if original_price_value:
                    item['original_price'] = original_price_value
            
            # Strategy 2: Extract discounted price from <ins> tag or regular price element
            discounted_price = response.css('.price ins .woocommerce-Price-amount::text, .price ins .amount::text, .price ins bdi::text').get()
            if not discounted_price:
                # If no <ins> tag, check regular price element (might be the only price)
                discounted_price = response.css('.price .woocommerce-Price-amount::text, .price .amount::text, .current-price::text').get()
            
            if discounted_price:
                discounted_price_value = extract_numbers(discounted_price)
                if discounted_price_value:
                    item['price'] = discounted_price_value
            
            # Strategy 3: Fallback - if we didn't get both prices, try extracting all price elements
            # Get all price amounts and determine which is original vs discounted
            if not item.get('original_price') or not item.get('price'):
                all_prices = response.css('.price .woocommerce-Price-amount::text, .price .amount::text, .price bdi::text').getall()
                price_values = []
                for price_text in all_prices:
                    price_val = extract_numbers(price_text)
                    if price_val and price_val not in price_values:
                        price_values.append(price_val)
                
                if len(price_values) >= 2:
                    # Higher price is usually the original, lower is discounted
                    price_values.sort(reverse=True)
                    if not item.get('original_price'):
                        item['original_price'] = price_values[0]
                    if not item.get('price'):
                        item['price'] = price_values[1]
                elif len(price_values) == 1:
                    # Only one price found - it's the current price (no discount)
                    if not item.get('price'):
                        item['price'] = price_values[0]
            
            # Extract description (actual story/plot description)
            # Check multiple locations where description might appear:
            # 1. Short description area (above tabs)
            # 2. Description tab panel (in WooCommerce tabs)
            # 3. Description section after heading
            description_text = []
            
            # Strategy 1: Check short description area (above tabs)
            short_desc = response.css('.woocommerce-product-details__short-description p::text, .product-short-description p::text').getall()
            if short_desc:
                description_text.extend(short_desc)
            
            # Strategy 2: Check Description tab panel (WooCommerce tabs)
            desc_tab = response.css('.woocommerce-Tabs-panel--description p::text, .woocommerce-tabs .description p::text').getall()
            if desc_tab:
                description_text.extend(desc_tab)
            
            # Strategy 3: Check for description after "Description" heading (more general approach)
            # Look for content after h2 or h3 with "Description" text using XPath
            desc_after_heading = response.xpath('//h2[contains(text(), "Description")]/following-sibling::*[1]//p/text() | //h3[contains(text(), "Description")]/following-sibling::*[1]//p/text()').getall()
            if desc_after_heading:
                description_text.extend(desc_after_heading)
            
            # Strategy 4: If no paragraph text found, try getting direct text (but exclude table content)
            if not description_text:
                # Get text from short description area
                all_text = response.css('.woocommerce-product-details__short-description::text, .product-short-description::text').getall()
                # Also check description tab
                desc_tab_text = response.css('.woocommerce-Tabs-panel--description::text, .woocommerce-tabs .description::text').getall()
                all_text.extend(desc_tab_text)
                # Also try getting text after Description heading
                desc_heading_text = response.xpath('//h2[contains(text(), "Description")]/following-sibling::*[1]//text() | //h3[contains(text(), "Description")]/following-sibling::*[1]//text()').getall()
                all_text.extend(desc_heading_text)
                # Filter out text that's part of tables or additional info
                description_text = [t for t in all_text if t.strip() and len(t.strip()) > 10]
            
            # Filter out text that's clearly not description (like "Add to cart", "Wishlist", etc.)
            filtered_description = []
            skip_keywords = [
                'add to cart', 'wishlist', 'share', 'category', 'reviews', 
                'logged in customers', 'writer', 'art', 'pages', 'quantity',
                'there are no reviews', 'only logged in'
            ]
            
            for text in description_text:
                text_clean = clean_text(text)
                if text_clean and len(text_clean) > 20:  # Only keep substantial text (story descriptions)
                    text_lower = text_clean.lower()
                    # Skip if it contains skip keywords or looks like metadata
                    is_metadata = any(keyword in text_lower for keyword in skip_keywords)
                    # Skip if it's too short or looks like a label
                    is_label = len(text_clean.split()) <= 3 and ':' in text_clean
                    
                    if not is_metadata and not is_label:
                        filtered_description.append(text_clean)
            
            if filtered_description:
                # Join and clean up the description
                full_description = ' '.join(filtered_description)
                # Remove any trailing metadata that might have slipped through
                full_description = re.sub(r'\s*(Writer|Art|Pages|Category).*$', '', full_description, flags=re.IGNORECASE)
                item['description'] = clean_text(full_description)
            elif description_text:
                # Fallback: use all text but clean it
                item['description'] = clean_text(' '.join(description_text))
        
            # Extract additional information from the "Additional information" tab/table
            # This contains Writer, Art, Pages, etc.
            additional_info_section = response.css('.woocommerce-Tabs-panel--additional_information, .product_meta')
            
            # Dictionary to store all additional info
            additional_info_dict = {}
            
            if additional_info_section:
                # Extract data from table rows
                rows = additional_info_section.css('tr')
                
                for row in rows:
                    # Get cells in the row
                    cells = row.css('td, th')
                    if len(cells) >= 2:
                        # First cell is the label, second cell is the value
                        label = cells[0].css('::text').get()
                        value = cells[1].css('::text').get()
                        
                        # If direct text extraction didn't work, try getting all text from cells
                        if not label:
                            label = ' '.join(cells[0].css('*::text').getall())
                        if not value:
                            value = ' '.join(cells[1].css('*::text').getall())
                        
                        if label and value:
                            label_clean = clean_text(label).strip()
                            value_clean = clean_text(value).strip()
                            
                            if label_clean and value_clean:
                                # Store in additional_info dict (use original case for label)
                                additional_info_dict[label_clean] = value_clean
                
                # Store the complete additional info dictionary
                if additional_info_dict:
                    item['additional_info'] = additional_info_dict
                
                # Also populate individual fields for backward compatibility
                # Use case-insensitive matching to find keys
                writer_text = None
                art_text = None
                colorist_text = None
                
                # Search through all keys case-insensitively
                for key, value in additional_info_dict.items():
                    key_lower = key.lower()
                    
                    # Match Writer
                    if not writer_text and key_lower in ['writer', 'writers']:
                        writer_text = value
                    
                    # Match Art/Artist/Artwork
                    if not art_text and key_lower in ['art', 'artist', 'artwork', 'artists']:
                        art_text = value
                    
                    # Match Colorist/Colors
                    if not colorist_text and key_lower in ['colorist', 'colors', 'colourist', 'colours', 'colorists']:
                        colorist_text = value
                
                # Extract Writer
                if writer_text:
                    # Writer field might contain multiple writers, split by comma, &, or space
                    writer_names = [w.strip() for w in re.split(r'[,&]', writer_text) if w.strip()]
                    if writer_names:
                        item['writers'] = normalize_list(writer_names)
                
                # Extract Art/Artist/Artwork
                if art_text:
                    # Art field might contain multiple artists, split by comma, &, or space
                    art_names = [a.strip() for a in re.split(r'[,&]', art_text) if a.strip()]
                    if art_names:
                        # Set artists from additional info (this takes precedence)
                        item['artists'] = normalize_list(art_names)
                
                # Extract Colorist/Colors
                if colorist_text:
                    # Colorist field might contain multiple colorists, split by comma, &, or space
                    colorist_names = [c.strip() for c in re.split(r'[,&]', colorist_text) if c.strip()]
                    if colorist_names:
                        item['colorists'] = normalize_list(colorist_names)
                
                # Extract Pages (if not already extracted)
                pages_text = additional_info_dict.get('Pages') or additional_info_dict.get('pages')
                if pages_text and not item.get('pages'):
                    # Extract number from text (handles cases like "68 Pages", "68", etc.)
                    pages_value = extract_numbers(pages_text)
                    if pages_value:
                        try:
                            pages_int = int(pages_value)
                            # Validate page count using constants
                            if MIN_PAGES <= pages_int <= MAX_PAGES:
                                item['pages'] = pages_int
                        except (ValueError, TypeError):
                            pass
            
            # Extract product image (cover image)
            cover_image = response.css('.woocommerce-product-gallery__image img::attr(src), .product-image img::attr(src), img.wp-post-image::attr(src)').get()
            if cover_image:
                cover_image_url = response.urljoin(cover_image)
                item['cover_image_url'] = cover_image_url
                
                # Extract uploaded_date from cover_image_url
                # Pattern: /wp-content/uploads/{year}/{month}/...
                # Example: https://bullseyepress.in/wp-content/uploads/2024/10/WhatsApp-Image-2024-10-30-at-10.41.34-PM-1-600x897.jpeg
                uploaded_date_match = re.search(r'/wp-content/uploads/(\d{4})/(\d{1,2})/', cover_image_url)
                if uploaded_date_match:
                    year = int(uploaded_date_match.group(1))
                    month = int(uploaded_date_match.group(2))
                    day = 25  # Default day as specified
                    # Format as YYYY-MM-DD
                    item['listing_date'] = f"{year:04d}-{month:02d}-{day:02d}"
            
            # Extract series information from title
            # Titles like "Raj Rahman 2", "Yagyaa Origins – Issue 5" contain series info
            if item.get('title'):
                series_match = re.search(r'^([^–\-0-9]+)', item['title'])
                if series_match:
                    series_name = clean_text(series_match.group(1))
                    
                    # Clean up series name by removing common suffixes and metadata
                    # First, remove language indicators (English, Hindi) from anywhere in the name
                    series_name = re.sub(r'\s+English\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+English\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    
                    # Then remove other suffixes like: Issue, Hardcover, Paperback, Variant Cover, etc.
                    invalid_suffixes = [
                        r'\s+Issue\s*$',  # "Issue" at the end
                        r'\s+issue\s*$',  # "issue" at the end
                        r'\s+Hardcover\s*$',  # "Hardcover" at the end
                        r'\s+Paperback\s*$',  # "Paperback" at the end
                        r'\s+Variant\s+Cover\s*$',  # "Variant Cover" at the end
                        r'\s+Variant\s*$',  # "Variant" at the end
                        r'\s+Regular\s+Cover\s*$',  # "Regular Cover" at the end
                        r'\s+English\s+Hardcover\s*$',  # "English Hardcover" at the end
                        r'\s+Hindi\s+Hardcover\s*$',  # "Hindi Hardcover" at the end
                        r'\s+English\s+Paperback\s*$',  # "English Paperback" at the end
                        r'\s+Hindi\s+Paperback\s*$',  # "Hindi Paperback" at the end
                        r'\s+Combo\s+Issue\s*$',  # "Combo Issue" at the end
                        r'\s+Combo\s*$',  # "Combo" at the end
                    ]
                    
                    for suffix_pattern in invalid_suffixes:
                        series_name = re.sub(suffix_pattern, '', series_name, flags=re.IGNORECASE).strip()
                    
                    # List of invalid series values to completely filter out
                    invalid_series_values = [
                        'Issue', 'issue', 'English', 'Hindi', 'Variant Cover', 'Variant',
                        'Regular Cover', 'Issue 2', 'Issue 3', 'Issue 1-4', 'Combo of',
                        'English Hardcover', 'Hindi Hardcover', 'English Paperback', 'Hindi Paperback'
                    ]
                    
                    # Check if the cleaned series name is valid
                    if series_name and series_name not in invalid_series_values:
                        # Additional check: if series name is too short or just numbers, skip it
                        if len(series_name) > 2 and not series_name.isdigit():
                            item['series'] = series_name
                        # If invalid, don't set series field (it won't appear in output)
                    
                    # Extract issue number
                    issue_match = re.search(r'Issue\s+(\d+)', item['title'], re.IGNORECASE)
                    if issue_match:
                        try:
                            item['issue'] = int(issue_match.group(1))
                        except ValueError:
                            pass
                    else:
                        # Try to extract number from title (e.g., "Raj Rahman 2")
                        num_match = re.search(r'\b(\d+)\b', item['title'])
                        if num_match:
                            try:
                                item['issue'] = int(num_match.group(1))
                            except ValueError:
                                pass
            
            # Extract language from title and description
            # Common languages: Hindi, English, and other possible variations
            language = None
            title_text = item.get('title', '')
            desc_text = item.get('description', '')
            
            # Search in title first (more reliable)
            language_match = re.search(r'\b(Hindi|English|हिंदी|Eng|Hin)\b', title_text, re.IGNORECASE)
            if language_match:
                lang = language_match.group(1)
                # Normalize language names
                if lang.lower() in ['hindi', 'hin', 'हिंदी']:
                    language = 'Hindi'
                elif lang.lower() in ['english', 'eng']:
                    language = 'English'
                else:
                    language = lang.capitalize()
            
            # If not found in title, search in description
            if not language:
                language_match = re.search(r'\b(Hindi|English|हिंदी|Eng|Hin)\b', desc_text, re.IGNORECASE)
                if language_match:
                    lang = language_match.group(1)
                    # Normalize language names
                    if lang.lower() in ['hindi', 'hin', 'हिंदी']:
                        language = 'Hindi'
                    elif lang.lower() in ['english', 'eng']:
                        language = 'English'
                    else:
                        language = lang.capitalize()
            
            # Also check for language in product meta or categories
            if not language:
                meta_text = response.css('.product_meta, .product-categories').get() or ''
                language_match = re.search(r'\b(Hindi|English|हिंदी|Eng|Hin)\b', meta_text, re.IGNORECASE)
                if language_match:
                    lang = language_match.group(1)
                    if lang.lower() in ['hindi', 'hin', 'हिंदी']:
                        language = 'Hindi'
                    elif lang.lower() in ['english', 'eng']:
                        language = 'English'
                    else:
                        language = lang.capitalize()
            
            if language:
                item['language'] = language
            
            # Extract binding information (Hardbound, Paperback, Hardcover, etc.)
            binding = None
            title_text = item.get('title', '')
            
            # Strategy 1: Extract from title (most common location)
            # Look for binding keywords in title
            binding_patterns = [
                (r'\b(hardbound|hard\s*bound)\b', 'Hardbound'),
                (r'\b(paperback|paper\s*back)\b', 'Paperback'),
                (r'\b(hardcover|hard\s*cover)\b', 'Hardcover'),
                (r'\b(softcover|soft\s*cover)\b', 'Softcover'),
            ]
            
            for pattern, binding_value in binding_patterns:
                if re.search(pattern, title_text, re.IGNORECASE):
                    binding = binding_value
                    break
            
            # Strategy 2: Check additional_info section
            if not binding and item.get('additional_info'):
                additional_info_dict = item.get('additional_info', {})
                # Check all values in additional_info for binding keywords
                for key, value in additional_info_dict.items():
                    value_lower = str(value).lower()
                    if 'hardbound' in value_lower or 'hard bound' in value_lower:
                        binding = 'Hardbound'
                        break
                    elif 'paperback' in value_lower or 'paper back' in value_lower:
                        binding = 'Paperback'
                        break
                    elif 'hardcover' in value_lower or 'hard cover' in value_lower:
                        binding = 'Hardcover'
                        break
                    elif 'softcover' in value_lower or 'soft cover' in value_lower:
                        binding = 'Softcover'
                        break
            
            # Strategy 3: Check description as fallback
            if not binding:
                desc_text = item.get('description', '')
                if desc_text:
                    for pattern, binding_value in binding_patterns:
                        if re.search(pattern, desc_text, re.IGNORECASE):
                            binding = binding_value
                            break
            
            if binding:
                item['binding'] = binding
            
            # Extract variant information (e.g., "Regular Cover", "Action figure variant")
            variant_match = re.search(r'(variant|cover|hardbound|paperback|hardcover)', item.get('title', ''), re.IGNORECASE)
            
            # Extract page count from multiple sources
            page_count = None
            
            # Try to extract from CSS selectors first (most reliable)
            page_count_text = response.css('.page-count::text, [data-pages]::attr(data-pages), .pages::text, [data-page-count]::attr(data-page-count)').get()
            if page_count_text:
                try:
                    page_count = int(clean_text(page_count_text))
                except (ValueError, TypeError):
                    pass
            
            # If not found, try to extract from description
            if not page_count:
                desc_text = item.get('description', '')
                if desc_text:
                    # Pattern 1: Look for explicit "64 pages", "64 pgs", "64 p." patterns
                    page_match = re.search(r'\b(\d+)\s*(?:pages?|pgs?|p\.?)\b', desc_text, re.IGNORECASE)
                    if page_match:
                        try:
                            num = int(page_match.group(1))
                            # Validate page count using constants
                            if MIN_PAGES <= num <= MAX_PAGES:
                                page_count = num
                        except (ValueError, TypeError):
                            pass
                    
                    # Pattern 2: Look for standalone numbers at the end (common pattern: "Name Name Name 64")
                    if not page_count:
                        # Split description and check the last few words
                        words = desc_text.strip().split()
                        # Check last 3 words for a number that could be page count
                        for word in reversed(words[-3:]):
                            # Remove any trailing punctuation
                            clean_word = word.strip('.,;:!?')
                            if clean_word.isdigit():
                                num = int(clean_word)
                                # Validate page count using constants
                                if MIN_PAGES <= num <= MAX_PAGES:
                                    page_count = num
                                    break
                    
                    # Pattern 3: Look for any number in description (fallback)
                    if not page_count:
                        numbers = re.findall(r'\b(\d+)\b', desc_text)
                        if numbers:
                            # Prefer numbers that appear after names (likely page count)
                            for num_str in reversed(numbers):  # Check from end first
                                num = int(num_str)
                                # Validate page count using constants
                                if MIN_PAGES <= num <= MAX_PAGES:
                                    page_count = num
                                    break
            
            # Also check product meta and additional info sections
            if not page_count:
                meta_text = response.css('.product_meta, .woocommerce-Tabs-panel--additional_information').get() or ''
                if meta_text:
                    # Look for explicit page mentions
                    page_match = re.search(r'\b(\d+)\s*(?:pages?|pgs?|p\.?)\b', meta_text, re.IGNORECASE)
                    if page_match:
                        try:
                            num = int(page_match.group(1))
                            # Validate page count using constants
                            if MIN_PAGES <= num <= MAX_PAGES:
                                page_count = num
                        except (ValueError, TypeError):
                            pass
            
            # Also check the full response text for page information
            if not page_count:
                full_text = response.text
                # Look for patterns like "Pages: 64", "64 pages", etc.
                page_match = re.search(r'(?:pages?|pgs?)[:\s]+(\d+)\b', full_text, re.IGNORECASE)
                if page_match:
                    try:
                        num = int(page_match.group(1))
                        # Validate page count using constants
                        if MIN_PAGES <= num <= MAX_PAGES:
                            page_count = num
                    except (ValueError, TypeError):
                        pass
            
            if page_count:
                item['pages'] = page_count
            
            # Extract additional product details from WooCommerce tabs
            # Check for additional information tabs
            additional_info = response.css('.woocommerce-Tabs-panel--additional_information, .product_meta').get()
            
            # Extract SKU, ISBN if available
            isbn = response.css('.sku::text, [data-isbn]::attr(data-isbn)').get()
            if isbn:
                item['isbn'] = clean_text(isbn)
            
            # Extract artist information from product data
            # Note: Artists from additional_info are already extracted above and take precedence
            artists = []
            
            # Invalid keywords to filter out (cache, UI elements, etc.)
            invalid_keywords = [
                'litespeed', 'cache', 'comments', 'feed', 'quantity', 
                'logged', 'customers', 'purchased', 'product', 'review',
                'there', 'are', 'no', 'reviews', 'yet', 'only', 'may', 'leave',
                'hand', 'painted', 'variant', 'cover', 'wraparound', 'poster',
                'homage', 'action', 'figure', 'regular', 'hardbound', 'paperback',
                'hardcover', 'english', 'hindi', 'issue', 'shot', 'one'
            ]
            
            # Strategy 1: Extract from title if it mentions "by [Artist]"
            title_text = item.get('title', '')
            if title_text:
                # Pattern: "Title by Artist Name" or "Title variant by Artist"
                # Handle patterns like "Title - variant by Artist Name" or "Title by Artist Name"
                by_match = re.search(r'\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', title_text, re.IGNORECASE)
                if by_match:
                    artist_name = clean_text(by_match.group(1))
                    artist_lower = artist_name.lower()
                    is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                    if artist_name and len(artist_name) > 2 and not is_invalid:
                        artists.append(artist_name)
            
            # Strategy 1b: Extract from URL slug if title doesn't have "by"
            # Example: "raj-rahman-2-english-regular-cover-by-deepjoy-subba"
            if not artists:
                url_slug = response.url.split('/')[-2] if response.url.endswith('/') else response.url.split('/')[-1]
                by_in_url = re.search(r'-by-([a-z]+(?:-[a-z]+)+)', url_slug, re.IGNORECASE)
                if by_in_url:
                    # Convert "deepjoy-subba" to "Deepjoy Subba"
                    artist_slug = by_in_url.group(1)
                    artist_name = ' '.join(word.capitalize() for word in artist_slug.split('-'))
                    artist_lower = artist_name.lower()
                    is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                    if artist_name and len(artist_name) > 2 and not is_invalid:
                        artists.append(artist_name)
            
            # Strategy 2: Extract from product description (only if no artists found yet)
            # This is less reliable as descriptions often contain character names, not artist names
            # Only use this as a last resort if artists weren't found in additional_info or title
            if not item.get('artists') and not artists:
                desc_text = item.get('description', '')
                if desc_text:
                    # Remove common review text that appears at the end
                    desc_text = re.sub(r'There are no reviews yet.*', '', desc_text, flags=re.IGNORECASE)
                    desc_text = re.sub(r'Only logged in customers.*', '', desc_text, flags=re.IGNORECASE)
                    
                    # Look for explicit artist mentions in description
                    # Pattern: "by Artist Name" or "Artist: Name" or "Art by Name"
                    explicit_artist_patterns = [
                        r'\b(?:by|artist|art by|artwork by|illustrated by|drawn by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
                        r'(?:artist|artwork|illustrator)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
                    ]
                    
                    for pattern in explicit_artist_patterns:
                        artist_match = re.search(pattern, desc_text, re.IGNORECASE)
                        if artist_match:
                            artist_name = clean_text(artist_match.group(1))
                            artist_lower = artist_name.lower()
                            is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                            if artist_name and len(artist_name) > 2 and not is_invalid:
                                artists.append(artist_name)
                                break
                    
                    # Only extract from description text if we found explicit mentions
                    # Don't extract random capitalized words as they're likely character names
            
            # Strategy 3: Extract from product meta fields (WooCommerce specific)
            product_meta = response.css('.product_meta, .woocommerce-product-details__short-description').get() or ''
            if product_meta:
                # Look for explicit meta labels only (avoid generic capitalized names)
                meta_text = ' '.join(response.css('.product_meta *::text, .woocommerce-product-details__short-description *::text').getall())
                if meta_text:
                    explicit_meta_patterns = [
                        r'\b(?:artist|art|art by|artwork by|illustrated by|drawn by)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
                    ]
                    for pattern in explicit_meta_patterns:
                        m = re.search(pattern, meta_text, re.IGNORECASE)
                        if m:
                            name = clean_text(m.group(1))
                            name_lower = name.lower()
                            is_invalid = any(keyword in name_lower for keyword in invalid_keywords)
                            if not is_invalid and len(name) > 3 and name not in artists:
                                artists.append(name)
            
            # Strategy 4: Extract cover artist from title if mentioned
            if title_text:
                cover_patterns = [
                    r'cover\s+(?:by|artist)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    r'variant\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                ]
                for pattern in cover_patterns:
                    cover_match = re.search(pattern, title_text, re.IGNORECASE)
                    if cover_match:
                        cover_artist = clean_text(cover_match.group(1))
                        if cover_artist and len(cover_artist) > 2:
                            item['cover_artist'] = cover_artist
                            if cover_artist not in artists:
                                artists.append(cover_artist)
                            break
            
            # Clean and deduplicate artists
            # Only set artists from description if they weren't already set from additional_info
            if artists and not item.get('artists'):
                # Remove duplicates while preserving order and filter invalid entries
                seen = set()
                unique_artists = []
                for artist in artists:
                    artist_clean = clean_text(artist)
                    artist_lower = artist_clean.lower()
                    
                    # Final validation: check length, duplicates, and invalid keywords
                    is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                    
                    if (artist_lower not in seen and 
                        len(artist_clean) > 2 and 
                        not is_invalid and
                        artist_clean.strip()):
                        seen.add(artist_lower)
                        unique_artists.append(artist_clean)
                
                if unique_artists:
                    item['artists'] = normalize_list(unique_artists)
            
            # Extract genre (could be manga, comic, etc.)
            # Check product categories
            categories = response.css('.product-categories a::text, .posted_in a::text').getall()
            if categories:
                # Filter out "Uncategorized" and empty values
                genres = [clean_text(cat) for cat in categories if cat and clean_text(cat).lower() != 'uncategorized']
                # Only set genre if we have valid genres (not empty)
                if genres:
                    item['genre'] = normalize_list(genres)
                else:
                    # Set empty array if no valid genres found
                    item['genre'] = []
            else:
                # Set empty array if no categories found
                item['genre'] = []
            
            # Store URL
            item['url'] = response.url
            
            item = self.add_scraped_timestamp(item)
            item = self.clean_item(item)
        
        except Exception as e:
            self.logger.error(f"Error parsing product detail for {response.url}: {e}", exc_info=True)
            # Try to create a minimal item with at least URL and title if possible
            if item is None:
                try:
                    item = ComicItem()
                    item['url'] = response.url
                    title = response.css('h1::text').get()
                    if title:
                        item['title'] = clean_text(title)
                        item['publisher'] = 'Bullseye Press'
                except:
                    return
        
        # Always yield item if it has a title, even if some fields failed to extract
        if item and item.get('title'):
            try:
                yield item
            except Exception as e:
                self.logger.error(f"Error yielding item for {response.url}: {e}", exc_info=True)
        else:
            self.logger.warning(f"Skipping item without title from {response.url}")
        
        # Also create a SeriesItem if we can extract series information
        if item and item.get('series'):
            try:
                series_item = SeriesItem()
                series_item['title'] = item['series']
                series_item['publisher'] = 'Bullseye Press'
                series_item['url'] = response.url
                series_item = self.add_scraped_timestamp(series_item)
                series_item = self.clean_item(series_item)
                yield series_item
            except Exception as e:
                self.logger.error(f"Error creating SeriesItem for {response.url}: {e}", exc_info=True)

