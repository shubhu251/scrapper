# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class PublisherItem(scrapy.Item):
    """Item for publisher information"""
    name = scrapy.Field()
    website = scrapy.Field()
    description = scrapy.Field()
    founded = scrapy.Field()
    headquarters = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()


class SeriesItem(scrapy.Item):
    """Item for comic series information"""
    title = scrapy.Field()
    publisher = scrapy.Field()
    description = scrapy.Field()
    start_date = scrapy.Field()
    end_date = scrapy.Field()
    issue_count = scrapy.Field()
    genre = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()


class ComicItem(scrapy.Item):
    """Item for individual comic book information"""
    title = scrapy.Field()
    series = scrapy.Field()
    issue = scrapy.Field()
    publisher = scrapy.Field()
    release_date = scrapy.Field()
    cover_artist = scrapy.Field()
    writers = scrapy.Field()
    artists = scrapy.Field()
    colorists = scrapy.Field()
    letterers = scrapy.Field()
    editors = scrapy.Field()
    characters = scrapy.Field()
    genre = scrapy.Field()
    language = scrapy.Field()
    binding = scrapy.Field()  # Hardbound, Paperback, Hardcover, etc.
    description = scrapy.Field()
    pages = scrapy.Field()
    price = scrapy.Field()  # Discounted/current price
    original_price = scrapy.Field()  # Original/actual price before discount
    isbn = scrapy.Field()
    cover_image_url = scrapy.Field()
    uploaded_date = scrapy.Field()  # Date extracted from cover_image_url
    additional_info = scrapy.Field()  # Store additional info table data as dict
    url = scrapy.Field()
    scraped_at = scrapy.Field()


class GenreItem(scrapy.Item):
    """Item for genre information"""
    name = scrapy.Field()
    description = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()


class CharacterItem(scrapy.Item):
    """Item for character information"""
    name = scrapy.Field()
    publisher = scrapy.Field()
    first_appearance = scrapy.Field()
    first_appearance_date = scrapy.Field()
    description = scrapy.Field()
    aliases = scrapy.Field()
    powers = scrapy.Field()
    teams = scrapy.Field()
    image_url = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()


class ArtistItem(scrapy.Item):
    """Item for artist information"""
    name = scrapy.Field()
    role = scrapy.Field()  # writer, penciller, inker, colorist, letterer, cover_artist
    bio = scrapy.Field()
    birth_date = scrapy.Field()
    nationality = scrapy.Field()
    notable_works = scrapy.Field()
    image_url = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()
