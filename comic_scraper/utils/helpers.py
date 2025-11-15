"""
Helper utilities for the comic scraper project
"""
import re
from datetime import datetime
from typing import Optional, List
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    PYTZ_AVAILABLE = False
except ImportError:
    # Fallback for Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo
        PYTZ_AVAILABLE = False
    except ImportError:
        ZoneInfo = None
        try:
            import pytz
            PYTZ_AVAILABLE = True
        except ImportError:
            PYTZ_AVAILABLE = False


def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean and normalize text content"""
    if not text:
        return None
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text.strip())
    return text if text else None


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """Parse and normalize date strings"""
    if not date_str:
        return None
    
    # Common date formats to try
    date_formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%B %d, %Y',
        '%b %d, %Y',
        '%Y',
    ]
    
    cleaned = clean_text(date_str)
    if not cleaned:
        return None
    
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return cleaned


def extract_numbers(text: Optional[str]) -> Optional[float]:
    """Extract numeric value from text"""
    if not text:
        return None
    
    # Remove currency symbols and extract number
    numbers = re.findall(r'\d+\.?\d*', text.replace(',', ''))
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return None
    return None


def normalize_list(items: Optional[List]) -> List:
    """Normalize list items, removing None and empty values"""
    if not items:
        return []
    if isinstance(items, str):
        # Split by common delimiters
        items = re.split(r'[,;|]', items)
    return [clean_text(str(item)) for item in items if item and clean_text(str(item))]


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format with IST timezone (UTC+5:30)"""
    if ZoneInfo:
        # Use zoneinfo (Python 3.9+)
        ist_time = datetime.now(ZoneInfo("Asia/Kolkata"))
    elif PYTZ_AVAILABLE:
        # Fallback to pytz
        ist = pytz.timezone("Asia/Kolkata")
        ist_time = datetime.now(ist)
    else:
        # Last resort: use UTC and manually add 5:30 offset
        # This shouldn't happen if dependencies are installed correctly
        utc_now = datetime.utcnow()
        from datetime import timedelta
        ist_time = utc_now + timedelta(hours=5, minutes=30)
        # Note: This won't have timezone info, but will have correct time
    
    # Format with timezone offset (+05:30)
    return ist_time.isoformat()


def extract_url_domain(url: str) -> Optional[str]:
    """Extract domain from URL"""
    if not url:
        return None
    match = re.search(r'https?://([^/]+)', url)
    return match.group(1) if match else None

