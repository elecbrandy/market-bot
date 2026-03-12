import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from datetime import date

from crawl4ai import CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

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
            "article_link": "div > h2 > a",
            "article_body": "div.richtext",
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

        md_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.45,         # 텍스트 밀도와 링크 밀도를 계산해 노이즈를 날리는 기준 (보통 0.4~0.5 사이)
                threshold_type="fixed",
                min_word_threshold=7   # 단어가 너무 적은 쓰레기 블록 무시
            ),
            options={
                "ignore_links": True,   # [텍스트](https...) 형태에서 URL 날리고 '텍스트'만 유지 (소셜 공유 버튼 초토화)
                "ignore_images": True,  # ![이미지](https...) 제거 (광고 배너 초토화)
            }
        )

        article_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            css_selector=self.config["selectors"].get("article_body"),
            # excluded_selector=self.config.get("exclude"),
            markdown_generator=md_generator
        )

        # 💡 [무한루프 방지] 이전 페이지 URL 집합
        previous_page_urls = set()
        
        # 💡 [Early Stop] 연속 중복 카운터 및 제한 횟수 설정
        consecutive_seen_count = 0
        MAX_CONSECUTIVE_SEEN = 5  # 이미 수집한 기사가 연속 5번 나오면 스크랩 중단

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

            tasks = []
            reached_old_date = False
            reached_seen_limit = False  # Early Stop 달성 여부 플래그
            current_page_urls = set()   # 현재 페이지 URL 수집용

            for link in links:
                href = link.get("href")
                if not href: continue

                full_url = f"https://eiga.com{href}" if href.startswith("/") else href
                current_page_urls.add(full_url)
                
                pub_date = self._parse_date(full_url)

                if pub_date:
                    if pub_date < self.start_date:
                        reached_old_date = True
                        break
                    if pub_date > self.end_date:
                        continue

                # 💡 Early Stop 적용: 이미 본 기사인지 체크
                if full_url in self.seen_urls:
                    consecutive_seen_count += 1
                    if consecutive_seen_count >= MAX_CONSECUTIVE_SEEN:
                        self.logger.info(f"이미 수집한 기사가 연속 {MAX_CONSECUTIVE_SEEN}번 발견되어 조기 종료(Early Stop)합니다.")
                        reached_seen_limit = True
                        break
                    continue
                else:
                    # 새로운 기사를 발견하면 연속 카운터 초기화
                    consecutive_seen_count = 0
                
                # _fetch_article 메서드를 활용하여 Task 리스트에 추가
                title = link.get_text(strip=True)
                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

            # 💡 무한 루프 방지 적용: 이전 페이지와 목록이 완전히 같다면 마지막 페이지로 간주
            if current_page_urls and current_page_urls == previous_page_urls:
                self.logger.info("마지막 페이지에 도달했습니다 (이전 페이지와 동일). 수집을 종료합니다.")
                break
            
            # 다음 루프 비교를 위해 현재 페이지 URL 상태 업데이트
            previous_page_urls = current_page_urls

            # 2. 수집된 Task들을 비동기로 한꺼번에 실행
            if tasks:
                results = await asyncio.gather(*tasks)
                for article_data in results:
                    if article_data and (self.max_items == 0 or yielded_count < self.max_items):
                        self.seen_urls.add(article_data["url"])
                        yielded_count += 1
                        yield article_data

            # 날짜 제한이거나 Early Stop 조건에 걸렸으면 루프 완전 탈출
            if reached_old_date or reached_seen_limit:
                break

            page_num += 1
            await asyncio.sleep(1) # 페이지 단위 요청 간격만 유지
