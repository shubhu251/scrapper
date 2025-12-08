"""
Spider for scraping Holy Cow Entertainment website (https://www.holycow.in/)
This spider extracts publisher info, comics, series, and artist information.
"""
from comic_scraper.spiders.base_spider import BaseComicSpider
from comic_scraper.items import PublisherItem, ComicItem, SeriesItem, ArtistItem
from comic_scraper.utils.helpers import clean_text, normalize_list, extract_numbers, parse_date
from comic_scraper.constants import MIN_PAGES, MAX_PAGES
import re


class HolyCowSpider(BaseComicSpider):
    """
    Spider to scrape Holy Cow Entertainment website.
    Extracts publisher information, comics, series, and artist data.
    
    Usage:
        scrapy crawl holy_cow
    """
    
    name = 'holy_cow'
    allowed_domains = ['holycow.in']
    start_urls = ['https://www.holycow.in/shop/']
    
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
        
        # Strategy 3: Construct next page URL manually if no pagination links found
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
        
        # Strategy 4: Load more button (AJAX pagination) - only if it exists
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
        item['name'] = 'Holy Cow Entertainment'
        item['website'] = 'https://www.holycow.in'
        item['url'] = 'https://www.holycow.in'
        
        # Try to extract description from about page or footer
        description = response.css('.site-description::text, footer p::text, .about-description::text').get()
        if not description:
            description = 'Pioneering and unique publisher of comics in India'
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
            item['publisher'] = 'Holy Cow Entertainment'
            
            # Extract price information
            # WooCommerce typically structures prices as:
            # <span class="price">
            #   <del><span class="woocommerce-Price-amount">₹599</span></del>  (original price)
            #   <ins><span class="woocommerce-Price-amount">₹539</span></ins>  (discounted price)
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
            description_text = []
            
            # Strategy 1: Get all paragraphs from description tab panel (most reliable)
            # Use XPath to get all p tags within the description panel, excluding the h2 heading
            desc_tab_paragraphs = response.xpath(
                '//div[contains(@class, "woocommerce-Tabs-panel--description")]//p[not(ancestor::table)]//text()'
            ).getall()
            if desc_tab_paragraphs:
                # Clean and filter paragraph text
                desc_tab_paragraphs = [t.strip() for t in desc_tab_paragraphs if t.strip()]
                if desc_tab_paragraphs:
                    description_text.extend(desc_tab_paragraphs)
            
            # Strategy 2: If no paragraphs found, get all text from description tab (excluding h2 heading and tables)
            if not description_text:
                desc_tab_text = response.xpath(
                    '//div[contains(@class, "woocommerce-Tabs-panel--description")]//text()[not(ancestor::h2) and not(ancestor::table)]'
                ).getall()
                desc_tab_text = [t.strip() for t in desc_tab_text if t.strip() and len(t.strip()) > 3]
                if desc_tab_text:
                    description_text.extend(desc_tab_text)
            
            # Strategy 3: Fallback to CSS selector for description tab paragraphs
            if not description_text:
                desc_tab_paragraphs_css = response.css('.woocommerce-Tabs-panel--description p::text, .woocommerce-tabs .description p::text').getall()
                if desc_tab_paragraphs_css:
                    desc_tab_paragraphs_css = [t.strip() for t in desc_tab_paragraphs_css if t.strip()]
                    if desc_tab_paragraphs_css:
                        description_text.extend(desc_tab_paragraphs_css)
            
            # Strategy 4: Check short description area (above tabs)
            if not description_text:
                short_desc = response.css('.woocommerce-product-details__short-description p::text, .product-short-description p::text').getall()
                if short_desc:
                    short_desc = [t.strip() for t in short_desc if t.strip()]
                    if short_desc:
                        description_text.extend(short_desc)
                else:
                    # Try getting all text from short description
                    short_desc_text = response.css('.woocommerce-product-details__short-description::text, .product-short-description::text').getall()
                    short_desc_text = [t.strip() for t in short_desc_text if t.strip() and len(t.strip()) > 3]
                    if short_desc_text:
                        description_text.extend(short_desc_text)
            
            # Strategy 5: Get text from description tab div directly using XPath (handles nested structures)
            if not description_text:
                desc_div_text = response.xpath(
                    '//div[contains(@class, "woocommerce-Tabs-panel--description")]//text()[not(ancestor::h2) and not(ancestor::table) and not(ancestor::h3)]'
                ).getall()
                desc_div_text = [t.strip() for t in desc_div_text if t.strip() and len(t.strip()) > 3]
                if desc_div_text:
                    description_text.extend(desc_div_text)
            
            # Filter out text that's clearly not description (like "Add to cart", "Wishlist", etc.)
            filtered_description = []
            skip_keywords = [
                'add to cart', 'wishlist', 'share', 'quantity', 
                'logged in customers', 'there are no reviews', 
                'only logged in', 'you may also like', 'related products',
                'description'  # Skip the heading text itself
            ]
            
            for text in description_text:
                text_clean = clean_text(text)
                if not text_clean:
                    continue
                
                text_lower = text_clean.lower().strip()
                
                # Skip empty or whitespace-only text
                if not text_lower:
                    continue
                
                # Skip if it's exactly "Description" (the heading)
                if text_lower == 'description':
                    continue
                
                # Skip very short single words that are likely navigation/UI elements
                if len(text_lower.split()) <= 1 and len(text_lower) < 5:
                    continue
                
                # Skip if it's clearly a UI element (short text with skip keywords)
                is_ui_element = any(keyword in text_lower for keyword in skip_keywords) and len(text_clean) < 25
                
                # Skip if it looks like a label (very short with colon, but not part of a sentence)
                is_label = len(text_clean.split()) <= 2 and ':' in text_clean and len(text_clean) < 25 and not text_clean.endswith('.')
                
                # Skip if it's just punctuation or special characters
                text_without_punct = text_clean.replace('.', '').replace(',', '').replace('!', '').replace('?', '').replace(';', '').replace(':', '').replace('&nbsp;', '').strip()
                is_punctuation_only = len(text_without_punct) == 0
                
                if not is_ui_element and not is_label and not is_punctuation_only:
                    filtered_description.append(text_clean)
            
            if filtered_description:
                # Join all text with spaces
                full_description = ' '.join(filtered_description)
                # Clean up multiple spaces and normalize whitespace
                full_description = re.sub(r'\s+', ' ', full_description)
                # Remove any trailing metadata that might have slipped through
                full_description = re.sub(r'\s*(Writer|Art|Pages|Category|Additional Information|Description).*$', '', full_description, flags=re.IGNORECASE)
                # Final cleanup
                item['description'] = clean_text(full_description)
            elif description_text:
                # Fallback: use all text but clean it
                full_description = ' '.join([clean_text(t) for t in description_text if clean_text(t) and clean_text(t).lower() != 'description'])
                full_description = re.sub(r'\s+', ' ', full_description)
                item['description'] = clean_text(full_description)
        
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
                # Example: https://www.holycow.in/wp-content/uploads/2024/10/...
                uploaded_date_match = re.search(r'/wp-content/uploads/(\d{4})/(\d{1,2})/', cover_image_url)
                if uploaded_date_match:
                    year = int(uploaded_date_match.group(1))
                    month = int(uploaded_date_match.group(2))
                    day = 25  # Default day as specified
                    # Format as YYYY-MM-DD
                    item['listing_date'] = f"{year:04d}-{month:02d}-{day:02d}"
            
            # Extract series information from title
            # Titles like "That Man Solomon: Born Again #4", "The Last Asuran Vol. 3: W.O.M.E. Stage 1" contain series info
            if item.get('title'):
                title = item['title']
                
                # Extract series name - stop at Issue, Vol./Volume, Stage, colon, dash, or hash
                # Pattern: match everything from start until we hit Issue, Vol./Volume, Stage, :, –, -, or #
                # Use non-greedy match to stop at the first occurrence
                series_match = re.search(r'^(.+?)(?:\s+Issue\s+\d+|\s+Vol\.|\s+Vol\s+\d+|\s+Volume\s+\d+|\s+Volume\s+|\s+Stage\s+\d+|[:–\-#])', title, re.IGNORECASE)
                if not series_match:
                    # Fallback: if no Issue/Vol./Stage found, stop at colon, dash, or hash
                    series_match = re.search(r'^([^:–\-#]+)', title)
                
                if series_match:
                    series_name = clean_text(series_match.group(1))
                    
                    # Clean up series name by removing common suffixes and metadata
                    # First, remove language indicators (English, Hindi) from anywhere in the name
                    series_name = re.sub(r'\s+English\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+English\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    
                    # Remove Issue, Vol., Volume, Stage patterns that might have been captured
                    series_name = re.sub(r'\s+Issue\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Issue\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Vol\.?\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Vol\.?\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Volume\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Volume\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Stage\s+\d+\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Stage\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    
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
                        r'\s+Box\s+Set\s*$',  # "Box Set" at the end
                        r'\s+Deluxe\s+Edition\s*$',  # "Deluxe Edition" at the end
                    ]
                    
                    for suffix_pattern in invalid_suffixes:
                        series_name = re.sub(suffix_pattern, '', series_name, flags=re.IGNORECASE).strip()
                    
                    # List of invalid series values to completely filter out
                    invalid_series_values = [
                        'Issue', 'issue', 'English', 'Hindi', 'Variant Cover', 'Variant',
                        'Regular Cover', 'Box Set', 'Deluxe Edition', 'Born Again', 'Vol', 'Volume', 'Stage'
                    ]
                    
                    # Check if the cleaned series name is valid
                    if series_name and series_name not in invalid_series_values:
                        # Additional check: if series name is too short or just numbers, skip it
                        if len(series_name) > 2 and not series_name.isdigit():
                            item['series'] = series_name
                        # If invalid, don't set series field (it won't appear in output)
                    
                    # Extract issue number
                    issue_match = re.search(r'#(\d+)', item['title'], re.IGNORECASE)
                    if issue_match:
                        try:
                            item['issue'] = int(issue_match.group(1))
                        except ValueError:
                            pass
                    else:
                        # Try to extract number from title (e.g., "Vol. 3")
                        vol_match = re.search(r'Vol\.\s*(\d+)', item['title'], re.IGNORECASE)
                        if vol_match:
                            try:
                                item['issue'] = int(vol_match.group(1))
                            except ValueError:
                                pass
                        else:
                            # Try to extract standalone number
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
            
            # Strategy 1: Check additional_info section first (most reliable)
            if item.get('additional_info'):
                additional_info_dict = item.get('additional_info', {})
                
                # First, check if there's a "Binding" key directly
                binding_text = additional_info_dict.get('Binding') or additional_info_dict.get('binding')
                if binding_text:
                    binding_text_lower = str(binding_text).lower().strip()
                    # Normalize binding values
                    if 'hardbound' in binding_text_lower or 'hard bound' in binding_text_lower:
                        binding = 'Hardbound'
                    elif 'paperback' in binding_text_lower or 'paper back' in binding_text_lower:
                        binding = 'Paperback'
                    elif 'hardcover' in binding_text_lower or 'hard cover' in binding_text_lower or 'hc' in binding_text_lower:
                        binding = 'Hardcover'
                    elif 'softcover' in binding_text_lower or 'soft cover' in binding_text_lower:
                        binding = 'Softcover'
                    elif 'deluxe' in binding_text_lower:
                        binding = 'Deluxe Edition'
                    else:
                        # If it's a valid binding value but doesn't match patterns, use it as-is (capitalized)
                        binding = binding_text.strip()
                
                # If no "Binding" key, check all values in additional_info for binding keywords
                if not binding:
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
                        elif 'deluxe' in value_lower:
                            binding = 'Deluxe Edition'
                            break
            
            # Strategy 2: Extract from title (fallback)
            if not binding:
                title_text = item.get('title', '')
                binding_patterns = [
                    (r'\b(hardbound|hard\s*bound)\b', 'Hardbound'),
                    (r'\b(paperback|paper\s*back)\b', 'Paperback'),
                    (r'\b(hardcover|hard\s*cover|hc)\b', 'Hardcover'),
                    (r'\b(softcover|soft\s*cover)\b', 'Softcover'),
                    (r'\b(deluxe\s*edition)\b', 'Deluxe Edition'),
                ]
                
                for pattern, binding_value in binding_patterns:
                    if re.search(pattern, title_text, re.IGNORECASE):
                        binding = binding_value
                        break
            
            # Strategy 3: Check description as fallback
            if not binding:
                desc_text = item.get('description', '')
                if desc_text:
                    binding_patterns = [
                        (r'\b(hardbound|hard\s*bound)\b', 'Hardbound'),
                        (r'\b(paperback|paper\s*back)\b', 'Paperback'),
                        (r'\b(hardcover|hard\s*cover|hc)\b', 'Hardcover'),
                        (r'\b(softcover|soft\s*cover)\b', 'Softcover'),
                        (r'\b(deluxe\s*edition)\b', 'Deluxe Edition'),
                    ]
                    for pattern, binding_value in binding_patterns:
                        if re.search(pattern, desc_text, re.IGNORECASE):
                            binding = binding_value
                            break
            
            if binding:
                item['binding'] = binding
            
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
                            page_count = int(page_match.group(1))
                        except (ValueError, TypeError):
                            pass
            
            # Also check product meta and additional info sections
            if not page_count:
                meta_text = response.css('.product_meta, .woocommerce-Tabs-panel--additional_information').get() or ''
                if meta_text:
                    # Look for explicit page mentions
                    page_match = re.search(r'\b(\d+)\s*(?:pages?|pgs?|p\.?)\b', meta_text, re.IGNORECASE)
                    if page_match:
                        try:
                            page_count = int(page_match.group(1))
                        except (ValueError, TypeError):
                            pass
            
            if page_count and page_count > 0:
                item['pages'] = page_count
            
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
                'hardcover', 'english', 'hindi', 'issue', 'shot', 'one', 'box', 'set'
            ]
            
            # Strategy 1: Extract from title if it mentions "by [Artist]"
            title_text = item.get('title', '')
            if title_text:
                # Pattern: "Title by Artist Name" or "Title variant by Artist"
                by_match = re.search(r'\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', title_text, re.IGNORECASE)
                if by_match:
                    artist_name = clean_text(by_match.group(1))
                    artist_lower = artist_name.lower()
                    is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                    if artist_name and len(artist_name) > 2 and not is_invalid:
                        artists.append(artist_name)
            
            # Strategy 1b: Extract from URL slug if title doesn't have "by"
            if not artists:
                url_slug = response.url.split('/')[-2] if response.url.endswith('/') else response.url.split('/')[-1]
                by_in_url = re.search(r'-by-([a-z]+(?:-[a-z]+)+)', url_slug, re.IGNORECASE)
                if by_in_url:
                    # Convert "artist-name" to "Artist Name"
                    artist_slug = by_in_url.group(1)
                    artist_name = ' '.join(word.capitalize() for word in artist_slug.split('-'))
                    artist_lower = artist_name.lower()
                    is_invalid = any(keyword in artist_lower for keyword in invalid_keywords)
                    if artist_name and len(artist_name) > 2 and not is_invalid:
                        artists.append(artist_name)
            
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
            
            # Extract genre - set to empty array for Holy Cow
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
                        item['publisher'] = 'Holy Cow Entertainment'
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
                series_item['publisher'] = 'Holy Cow Entertainment'
                series_item['url'] = response.url
                series_item = self.add_scraped_timestamp(series_item)
                series_item = self.clean_item(series_item)
                yield series_item
            except Exception as e:
                self.logger.error(f"Error creating SeriesItem for {response.url}: {e}", exc_info=True)

