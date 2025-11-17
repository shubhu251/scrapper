"""
Spider for scraping Raj Comics website (https://rajcomics.shop/)
This spider extracts publisher info, comics, series, and artist information.
"""
from comic_scraper.spiders.base_spider import BaseComicSpider
from comic_scraper.items import PublisherItem, ComicItem, SeriesItem, ArtistItem
from comic_scraper.utils.helpers import clean_text, normalize_list, extract_numbers, parse_date
import re


class RajComicsShopSpider(BaseComicSpider):
    """
    Spider to scrape Raj Comics website.
    Extracts publisher information, comics, series, and artist data.
    
    Usage:
        scrapy crawl raj_comics_shop
    """
    
    name = 'raj_comics_shop'
    allowed_domains = ['rajcomics.shop']
    start_urls = ['https://rajcomics.shop/collections/all']
    
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
        
        # Multiple strategies to find product links (Shopify uses /products/ URLs)
        product_links = set()
        
        # Strategy 1: Find all product links using Shopify selectors
        product_selectors = [
            'a.product-item__link::attr(href)',
            '.product-item a::attr(href)',
            'a[href*="/products/"]::attr(href)',
            '.grid-product__link::attr(href)',
            '.product-card__link::attr(href)',
            'article.product a::attr(href)',
        ]
        
        for selector in product_selectors:
            links = response.css(selector).getall()
            for link in links:
                if link and '/products/' in link:
                    full_url = response.urljoin(link)
                    if full_url not in self.visited_urls:
                        product_links.add(full_url)
        
        # Strategy 2: Find all links that contain /products/ in the URL
        all_links = response.css('a::attr(href)').getall()
        for link in all_links:
            if link and '/products/' in link:
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
        
        # Only handle pagination if we found products on this page
        if not product_links:
            self.logger.info(f"No products found on {response.url}, skipping pagination")
            return
        
        # Handle pagination - Shopify typically uses ?page= parameter
        pagination_links = set()
        
        # Strategy 1: Next page link (most reliable)
        next_selectors = [
            'a.pagination__next::attr(href)',
            '.pagination a.next::attr(href)',
            'a[rel="next"]::attr(href)',
            '.pagination-next::attr(href)',
            'a[aria-label="Next"]::attr(href)',
        ]
        for selector in next_selectors:
            next_link = response.css(selector).get()
            if next_link:
                full_url = response.urljoin(next_link)
                if full_url and full_url not in self.visited_urls and full_url != response.url:
                    pagination_links.add(full_url)
                    break
        
        # Strategy 2: Construct next page URL manually
        if not pagination_links:
            # Extract current page number
            current_page = 1
            page_match = re.search(r'[?&]page=(\d+)', response.url)
            if page_match:
                current_page = int(page_match.group(1))
            
            # Construct next page URL
            next_page = current_page + 1
            base_url = response.url.split('?')[0].rstrip('/')
            
            # Remove existing page parameter if present
            if '?' in response.url:
                base_url = response.url.split('?')[0]
                params = response.url.split('?')[1]
                # Remove page parameter
                params = re.sub(r'[&?]page=\d+', '', params)
                if params:
                    next_page_url = f"{base_url}?{params}&page={next_page}"
                else:
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
        item['name'] = 'Raj Comics'
        item['website'] = 'https://rajcomics.shop'
        item['url'] = 'https://rajcomics.shop'
        
        # Try to extract description from about page or footer
        description = response.css('.site-description::text, footer p::text, .about-description::text').get()
        if not description:
            description = 'Iconic Indian comic book publisher'
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
            title = response.css('h1.product-single__title::text, h1.product__title::text, .product-title h1::text').get()
            if not title:
                title = response.css('h1::text').get()
            item['title'] = clean_text(title)
            
            # Extract publisher
            item['publisher'] = 'Raj Comics'
            
            # Extract price information (Shopify format)
            # Regular price
            regular_price = response.css('.product__price .price--regular::text, .product-single__price .price::text, .price--regular::text').get()
            if not regular_price:
                regular_price = response.css('.product__price::text, .product-single__price::text').get()
            
            if regular_price:
                price_value = extract_numbers(regular_price)
                if price_value:
                    item['price'] = price_value
                    item['original_price'] = price_value  # If no sale price, original = current
            
            # Sale price (if available)
            sale_price = response.css('.product__price .price--sale::text, .product-single__price .price--sale::text, .price--sale::text').get()
            if sale_price:
                sale_price_value = extract_numbers(sale_price)
                if sale_price_value:
                    item['price'] = sale_price_value
                    # Original price should already be set from regular price
            
            # Extract description
            description_text = []
            
            # Strategy 1: Product description section
            desc_sections = response.css('.product__description, .product-single__description, .product-description').getall()
            for section in desc_sections:
                # Get all paragraphs
                paragraphs = response.css('.product__description p::text, .product-single__description p::text, .product-description p::text').getall()
                if paragraphs:
                    description_text.extend(paragraphs)
                else:
                    # Get all text
                    text = response.css('.product__description::text, .product-single__description::text, .product-description::text').getall()
                    text = [t.strip() for t in text if t.strip() and len(t.strip()) > 10]
                    description_text.extend(text)
            
            # Strategy 2: Meta description or other description fields
            if not description_text:
                meta_desc = response.css('meta[name="description"]::attr(content)').get()
                if meta_desc and len(meta_desc) > 50:
                    description_text.append(meta_desc)
            
            if description_text:
                full_description = ' '.join([clean_text(t) for t in description_text if clean_text(t)])
                full_description = re.sub(r'\s+', ' ', full_description)
                item['description'] = clean_text(full_description)
            
            # Extract product image (cover image)
            cover_image = response.css('.product__photo img::attr(src), .product-single__photo img::attr(src), .product__media img::attr(src), img.product-featured-media::attr(src)').get()
            if not cover_image:
                # Try data attributes
                cover_image = response.css('.product__photo img::attr(data-src), .product-single__photo img::attr(data-src)').get()
            
            if cover_image:
                cover_image_url = response.urljoin(cover_image)
                # Remove size parameters from Shopify image URLs
                cover_image_url = re.sub(r'_[0-9]+x[0-9]+\.', '.', cover_image_url)
                item['cover_image_url'] = cover_image_url
                
                # Try to extract date from image URL if possible
                uploaded_date_match = re.search(r'/(\d{4})/(\d{1,2})/', cover_image_url)
                if uploaded_date_match:
                    year = int(uploaded_date_match.group(1))
                    month = int(uploaded_date_match.group(2))
                    day = 25  # Default day
                    item['listing_date'] = f"{year:04d}-{month:02d}-{day:02d}"
            
            # Extract series information from title
            # Titles like "NAGRAJ - Title", "DHRUVA - Title" contain series info
            if item.get('title'):
                title = item['title']
                
                # Extract series name - stop at common delimiters
                series_match = re.search(r'^([^–\-#:]+?)(?:\s*[-–]\s*|\s*:\s*|\s+Issue\s+\d+|\s+Vol\.|\s+Vol\s+\d+)', title, re.IGNORECASE)
                if not series_match:
                    # Fallback: get first word or words before dash/colon
                    series_match = re.search(r'^([^–\-#:]+)', title)
                
                if series_match:
                    series_name = clean_text(series_match.group(1))
                    
                    # Clean up series name
                    series_name = re.sub(r'\s+English\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s+', ' ', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+English\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    series_name = re.sub(r'\s+Hindi\s*$', '', series_name, flags=re.IGNORECASE).strip()
                    
                    # Remove common suffixes
                    invalid_suffixes = [
                        r'\s+Issue\s*$', r'\s+issue\s*$',
                        r'\s+Vol\.?\s*$', r'\s+Volume\s*$',
                        r'\s+Part\s+\d+\s*$', r'\s+PART\s+\d+\s*$',
                    ]
                    for suffix_pattern in invalid_suffixes:
                        series_name = re.sub(suffix_pattern, '', series_name, flags=re.IGNORECASE).strip()
                    
                    invalid_series_values = ['Issue', 'issue', 'English', 'Hindi', 'Vol', 'Volume', 'Part']
                    
                    if series_name and series_name not in invalid_series_values:
                        if len(series_name) > 2 and not series_name.isdigit():
                            item['series'] = series_name
                    
                    # Extract issue number
                    issue_match = re.search(r'Issue\s+(\d+)|#(\d+)|Part\s+(\d+)|PART\s+(\d+)', title, re.IGNORECASE)
                    if issue_match:
                        for group in issue_match.groups():
                            if group:
                                try:
                                    item['issue'] = int(group)
                                    break
                                except ValueError:
                                    pass
            
            # Extract language from title and description
            language = None
            title_text = item.get('title', '')
            desc_text = item.get('description', '')
            
            # Search in title first
            language_match = re.search(r'\b(Hindi|English|हिंदी|Eng|Hin)\b', title_text, re.IGNORECASE)
            if language_match:
                lang = language_match.group(1)
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
                    if lang.lower() in ['hindi', 'hin', 'हिंदी']:
                        language = 'Hindi'
                    elif lang.lower() in ['english', 'eng']:
                        language = 'English'
                    else:
                        language = lang.capitalize()
            
            if language:
                item['language'] = language
            
            # Extract binding information
            binding = None
            title_text = item.get('title', '')
            
            binding_patterns = [
                (r'\b(hardbound|hard\s*bound)\b', 'Hardbound'),
                (r'\b(paperback|paper\s*back)\b', 'Paperback'),
                (r'\b(hardcover|hard\s*cover|hc)\b', 'Hardcover'),
                (r'\b(softcover|soft\s*cover)\b', 'Softcover'),
            ]
            
            for pattern, binding_value in binding_patterns:
                if re.search(pattern, title_text, re.IGNORECASE):
                    binding = binding_value
                    break
            
            if not binding:
                desc_text = item.get('description', '')
                if desc_text:
                    for pattern, binding_value in binding_patterns:
                        if re.search(pattern, desc_text, re.IGNORECASE):
                            binding = binding_value
                            break
            
            if binding:
                item['binding'] = binding
            
            # Extract page count
            page_count = None
            
            # Try to extract from description
            desc_text = item.get('description', '')
            if desc_text:
                page_match = re.search(r'\b(\d+)\s*(?:pages?|pgs?|p\.?)\b', desc_text, re.IGNORECASE)
                if page_match:
                    try:
                        page_count = int(page_match.group(1))
                    except (ValueError, TypeError):
                        pass
            
            if page_count and page_count > 0:
                item['pages'] = page_count
            
            # Extract SKU, ISBN if available
            sku = response.css('.product__sku::text, .product-single__sku::text, [data-sku]::attr(data-sku)').get()
            if sku:
                item['isbn'] = clean_text(sku)
            
            # Extract genre from product tags or collections
            genres = []
            tags = response.css('.product__tags a::text, .product-tags a::text, .tag::text').getall()
            if tags:
                genres = [clean_text(tag) for tag in tags if tag and clean_text(tag).lower() not in ['uncategorized', 'all']]
            
            # Also check product type or vendor
            product_type = response.css('.product__type::text, [data-product-type]::attr(data-product-type)').get()
            if product_type:
                product_type_clean = clean_text(product_type)
                if product_type_clean and product_type_clean not in genres:
                    genres.append(product_type_clean)
            
            if genres:
                item['genre'] = normalize_list(genres)
            else:
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
                        item['publisher'] = 'Raj Comics'
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
                series_item['publisher'] = 'Raj Comics'
                series_item['url'] = response.url
                series_item = self.add_scraped_timestamp(series_item)
                series_item = self.clean_item(series_item)
                yield series_item
            except Exception as e:
                self.logger.error(f"Error creating SeriesItem for {response.url}: {e}", exc_info=True)

