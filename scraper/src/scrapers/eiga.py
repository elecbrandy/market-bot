# ./scraper/src/scrapers/eiga.py

import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime

# 2026 최신 crawl4ai 임포트
from crawl4ai import CrawlerRunConfig, CacheMode

from src.scrapers.base import BaseScraper
from src.utils.selectors import SITE_CONFIG
from src.utils.logger import get_logger, log_progress

class EigaScraper(BaseScraper):
    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "eiga"
        
        # 💡 해당 사이트의 설정만 뽑아서 인스턴스 변수로 저장
        self.config = SITE_CONFIG[self.source_name]
        
        # 💡 BaseScraper에서 만든 로거를 내 이름('eiga')표를 달아 덮어쓰기
        self.logger = get_logger(self.source_name)

    def _parse_date(self, url: str):
        # 💡 하드코딩된 정규식 대신 config의 정규식 사용
        pattern = self.config["regex"]["date_extract"]
        match = re.search(pattern, url)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        return None

    async def scrape(self):
        page_num = 1
        yielded_count = 0  # 현재까지 수집한 기사 개수
        
        self.logger.info(f"Starting crawl for keyword: '{self.keyword}'")

        # 💡 핵심 본문 영역만 타겟팅하여 추출하는 전용 Config
        article_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            css_selector=self.config["selectors"].get("article_body")
        )

        while True:
            # 💡 조기 종료 조건 1: 페이지 진입 전 최대 수집량 도달 확인
            if self.max_items > 0 and yielded_count >= self.max_items:
                self.logger.info(f"Reached maximum limit ({self.max_items} items). Stopping search.")
                break

            # URL 템플릿 조합
            search_path = self.config["search_path"].format(keyword=self.keyword, page=page_num)
            target_url = f"{self.config['base_url']}{search_path}"
            
            self.logger.info(f"Scanning page {page_num}...")

            # 검색 목록 페이지 접속
            list_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            result = await self.crawler.arun(url=target_url, config=list_run_config)
            
            if not result.success:
                self.logger.warning("Connection failed or end of pages reached.")
                break

            soup = BeautifulSoup(result.html, 'html.parser')
            
            # 💡 Config의 Selector를 사용하여 뉴스 컨테이너와 링크 추출
            news_section = soup.select_one(self.config["selectors"]["news_container"])
            links = news_section.select(self.config["selectors"]["article_link"]) if news_section else []

            if not links:
                self.logger.info("No more articles found on this page.")
                break

            reached_old_date = False
            total_links = len(links)
            current_link = 0

            for link in links:
                # 💡 조기 종료 조건 2: 링크 순회 중 최대 수집량 도달 확인
                if self.max_items > 0 and yielded_count >= self.max_items:
                    break

                current_link += 1
                href = link.get('href')
                if not href: continue

                full_url = f"https://eiga.com{href}" if href.startswith("/") else href
                pub_date = self._parse_date(full_url)

                if pub_date:
                    # 시작일(start_date) 이전 기사에 도달하면 완전 종료 플래그 활성화
                    if pub_date < self.start_date:
                        self.logger.info(f"Reached articles older than {self.start_date}. Stopping.")
                        reached_old_date = True
                        break
                    
                    # 종료일(end_date)보다 미래 기사면 이번 건만 패스
                    if pub_date > self.end_date:
                        continue

                # 중복 확인 (파이썬 메모리 캐시 1차 방어선)
                if full_url in self.seen_urls:
                    self.logger.debug(f"Skipped duplicate URL: {full_url}")
                    continue

                # 💡 진짜 본문 크롤링 (메뉴/푸터 제외)
                article_result = await self.crawler.arun(url=full_url, config=article_run_config)
                
                if article_result.success:
                    clean_content = article_result.markdown.strip() if article_result.markdown else ""
                    
                    # 수집된 데이터를 Generator 형태로 메인 프로세스에 전달
                    yield {
                        "source": self.source_name,
                        "keyword": self.keyword,
                        "url": full_url,
                        "title": link.text.strip(),
                        "content": clean_content,
                        "published_date": pub_date
                    }
                    
                    self.seen_urls.add(full_url)
                    yielded_count += 1
                    
                    # 진행률 출력
                    log_progress(self.logger, current_link, total_links, prefix=f"Page {page_num} Scraping")
                    
                    await asyncio.sleep(1) # 매너 타임

            if reached_old_date:
                break

            page_num += 1
            await asyncio.sleep(1.5)