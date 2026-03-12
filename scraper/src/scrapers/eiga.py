import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from datetime import date
from crawl4ai import CrawlerRunConfig, CacheMode
from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger

# 크롤링 설정 정의    
eiga_config = {
    "base_url": "https://eiga.com",
    "search_path": "/search/{keyword}/news/{page}/",
    "selectors": {
        "news_container": "#rslt-news",
        "article_link": "div > h2 > a",
        "article_body": "div.richtext",
    },
    "exclude": (
        "figure, iframe"
    ),
    "regex": {
        "date_extract": r"/news/(\d{8})/"
    }
}

class EigaScraper(BaseScraper):
    """ Eiga.com에서 영화 관련 뉴스를 크롤링하는 스크래퍼입니다. """

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "eiga"               # 스크래퍼 이름 설정
        self.config = eiga_config               # 크롤링 설정 초기화
        self.logger = get_logger(self.source_name)

        # 상태 관리 변수 초기화
        self.yielded_count = 0                  # yield된 기사 수 카운터 초기화
        self.previous_page_urls = set()         # 이전 페이지의 기사 URL 집합 (무한 루프 방지용)
        self.consecutive_seen_count = 0         # 연속으로 이미 본 기사가 나오는 횟수 카운터 (Early Stop용)
        self.sem = asyncio.Semaphore(self.sem_num)   # 한 번에 5개의 기사만 동시 크롤링 (서버 부하 방지)

    
    async def scrape(self):
        """ 검색 결과 페이지를 순회하며 링크를 수집하고, 각 기사 페이지를 스크래핑"""
        
        page_num = 1    # 페이지 번호 초기화

        while not self._is_done():
            
            # 1. 페이지 데이터 가져오기
            links = await self._fetch_search_page(page_num)
            if not links or self._is_duplicate(links):
                break

            # 2. 링크 목록에서 기사 데이터 수집 Task 생성
            tasks, reached_old_date = self._prepare_tasks(links)
            if tasks:
                    # 생성된 Task들을 비동기로 한꺼번에 실행하여 기사 데이터 수집
                    async for article_data in self._execute_tasks(tasks):
                        yield article_data

            # 루프 탈출 여부 결정
            # - reached_old_date: 날짜 제한에 걸린 기사 발견 여부
            # - consecutive_seen_count: 이미 본 기사가 연속으로 나오는 횟수
            if reached_old_date or self.consecutive_seen_count >= self.max_consecutive_seen:
                break

            page_num += 1
            await asyncio.sleep(1)

    def _is_done(self) -> bool:
        """ 루프 종료 조건 체크 """
        return self.max_items > 0 and self.yielded_count >= self.max_items
    
    def _is_duplicate(self, links: list) -> bool:
        """ 무한루프 방지를 위한 페이지 중복 체크 """

        # 현재 페이지에서 추출된 기사 URL 집합 생성
        current_urls = {link.get("href") for link in links if link.get("href")}
        if current_urls == self.previous_page_urls:
            self.logger.info("마지막 페이지 도달, 수집을 종료합니다.")
            return True
        self.previous_page_urls = current_urls
        return False
    
    def _parse_date(self, url: str) -> date | None:
        """ 기사 URL에서 날짜를 추출 """

        match = re.search(self.config["regex"]["date_extract"], url)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        return None
    
    def _prepare_tasks(self, links) -> tuple:
        """수집할 기사들을 선별하고 tasks 리스트 작성"""
        tasks = []
        reached_old_date = False
        
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            css_selector=self.config["selectors"].get("article_body"),
            excluded_selector=self.config["exclude"]
        )

        for link in links:
            url = self._build_full_url(link.get("href"))
            pub_date = self._parse_date(url)

            # 날짜 및 중복 검사 로직
            if pub_date and pub_date < self.start_date:
                reached_old_date = True
                break
            
            if self._should_skip(url, pub_date):
                continue

            tasks.append(self._fetch_article(url, pub_date, link.get_text(strip=True), run_config,))
        
        return tasks, reached_old_date
    
    def _should_skip(self, url, pub_date):
        """기사를 스킵해야 하는지 판단 (중복 및 날짜 범위)"""
        # 1. 미래 날짜 필터링
        if pub_date and pub_date > self.end_date:
            return True
        
        # 2. 중복 체크 및 Early Stop 카운터
        if url in self.seen_urls:
            self.consecutive_seen_count += 1
            return True
        self.consecutive_seen_count = 0  
        return False

    async def _execute_tasks(self, tasks):
        """비동기 태스크 실행 및 결과 처리"""
        results = await asyncio.gather(*tasks)
        for data in results:
            if data and not self._is_done():
                self.seen_urls.add(data["url"])
                self.yielded_count += 1
                yield data

    def _build_full_url(self, href):
        if not href: return ""
        return f"https://eiga.com{href}" if href.startswith("/") else href

    
    async def _fetch_search_page(self, page_num: int) -> list:
        """ 검색 결과 페이지에서 기사 링크를 추출하는 메소드 """
        search_path = self.config["search_path"].format(keyword=self.keyword, page=page_num)
        target_url = f"{self.config['base_url']}{search_path}"
        
        result = await self.crawler.arun(url=target_url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
        if not result.success:
            return []
            
        soup = BeautifulSoup(result.html, "html.parser")
        news_section = soup.select_one(self.config["selectors"]["news_container"])
        return news_section.select(self.config["selectors"]["article_link"]) if news_section else []

    async def _fetch_article(self,
                             url: str,                  # 기사 URL
                             pub_date: date,            # 기사 날짜 (URL에서 추출)
                             title: str,                # 기사 제목 (목록 페이지에서 추출)
                             config: CrawlerRunConfig,  # 크롤링 설정 (본문 추출용)
        ) -> dict | None:
        """ 개별 기사의 본문을 추출합니다. """

        # 세마포어로 동시 크롤링 제어
        async with self.sem:
            
            # 크롤링 실행
            result = await self.crawler.arun(url=url, config=config)
            
            # 결과가 성공적이고 HTML이 존재하는 경우에만 본문 추출 시도
            if result.success and result.html:
                soup = BeautifulSoup(result.html, "html.parser")

                # 본문 추출 전에 제외할 요소 제거 (예: 이미지, 광고 등)
                exclude_selectors = self.config.get("exclude")
                if exclude_selectors:
                    for s in soup.select(exclude_selectors):
                        s.decompose()

                # 기사 본문 추출
                paragraphs = soup.find_all("p")
                if paragraphs:
                    content = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                else:
                    content = soup.get_text(separator="\n\n", strip=True)

                return {
                    "source": self.source_name,     # 스크래퍼 이름
                    "keyword": self.keyword,        # 검색 키워드
                    "url": url,                     # 기사 URL
                    "title": title,                 # 기사 제목
                    "content": content,             # 기사 본문
                    "published_date": pub_date,     # 기사 날짜
                }
            return None    
