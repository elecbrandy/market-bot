from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any
from datetime import date
from crawl4ai import AsyncWebCrawler
from src.utils.logger import get_logger

class BaseScraper(ABC):
    def __init__(self, crawler: AsyncWebCrawler, keyword: str, start_date: date, end_date: date, seen_urls: set[str], max_items: int = 0):
        self.crawler = crawler
        self.keyword = keyword
        self.start_date = start_date
        self.end_date = end_date
        self.seen_urls = seen_urls
        self.max_items = max_items
        self.source_name = "unknown"
        self.logger = get_logger(self.source_name)

    @abstractmethod
    async def scrape(self) -> AsyncGenerator[Dict[str, Any], None]:
        """비동기 크롤링 로직: 수집된 기사 데이터를 dictionary 형태로 yield."""
        yield {}