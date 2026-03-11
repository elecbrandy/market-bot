import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from datetime import date

from crawl4ai import CrawlerRunConfig, CacheMode

from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger


class EigaScraper(BaseScraper):
    """
    Eiga.com에서 영화 관련 뉴스를 크롤링하는 스크래퍼입니다.
     - 검색 URL: https://eiga.com/search/?q={keyword}&p={page}
     - 기사 URL에서 날짜 추출: /news/20240101/ → 2024-01-01
     - 기사 본문은 CSS 선택자 ".article-body"로 추출
    """
    source_name = "eiga"

    config = {
        "base_url": "https://eiga.com",
        "search_path": "/search/{keyword}/news/{page}/",
        "selectors": {
            "news_container": "#rslt-news",
            "article_link": "div p.link > a",
            "article_body": "div.news-detail, div.txt-block",
        },
        "regex": {
            "date_extract": r"/news/(\d{8})/"
        }
    }
    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "eiga"
        self.config      = self.config
        self.logger      = get_logger(self.source_name)

    def _parse_date(self, url: str):
        """
        기사 URL에서 날짜를 추출하는 메소드입니다.
        """
        match = re.search(self.config["regex"]["date_extract"], url)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        return None
    
    async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig, sem: asyncio.Semaphore):
        """
        개별 기사 페이지를 크롤링하여 기사 데이터를 반환하는 메소드입니다.
        """
        async with sem:
            result = await self.crawler.arun(url=url, config=config)
            if result.success:
                return {
                    "source": self.source_name,
                    "keyword": self.keyword,
                    "url": url,
                    "title": title,
                    "content": result.markdown.strip() if result.markdown else "",
                    "published_date": pub_date,
                }
            return None

    async def scrape(self):
        """
        Eiga.com에서 검색 결과 페이지를 순회하며 기사 링크를 수집하고, 각 기사 페이지를 크롤링하여 데이터를 yield 합니다.
        """
        page_num = 1
        yielded_count = 0
        sem = asyncio.Semaphore(5)  # 한 번에 5개의 기사만 동시 크롤링 (서버 부하 방지)

        article_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            css_selector=self.config["selectors"].get("article_body"),
        )

        while True:
            if self.max_items > 0 and yielded_count >= self.max_items:
                break

            search_path = self.config["search_path"].format(keyword=self.keyword, page=page_num)
            target_url  = f"{self.config['base_url']}{search_path}"

            list_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            result = await self.crawler.arun(url=target_url, config=list_run_config)

            if not result.success:
                break

            soup = BeautifulSoup(result.html, "html.parser")
            news_section = soup.select_one(self.config["selectors"]["news_container"])
            links = news_section.select(self.config["selectors"]["article_link"]) if news_section else []

            if not links:
                break

            # 1. 크롤링할 대상 Task를 먼저 수집
            tasks = []
            reached_old_date = False

            for link in links:
                href = link.get("href")
                if not href: continue

                full_url = f"https://eiga.com{href}" if href.startswith("/") else href
                pub_date = self._parse_date(full_url)

                if pub_date:
                    if pub_date < self.start_date:
                        reached_old_date = True
                        break
                    if pub_date > self.end_date:
                        continue

                if full_url in self.seen_urls:
                    continue
                
                # _fetch_article 메서드를 활용하여 Task 리스트에 추가
                title = link.text.strip()
                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

            # 2. 수집된 Task들을 비동기로 한꺼번에 실행
            if tasks:
                results = await asyncio.gather(*tasks)
                for article_data in results:
                    if article_data and (self.max_items == 0 or yielded_count < self.max_items):
                        self.seen_urls.add(article_data["url"])
                        yielded_count += 1
                        yield article_data

            if reached_old_date:
                break

            page_num += 1
            await asyncio.sleep(1) # 페이지 단위 요청 간격만 유지