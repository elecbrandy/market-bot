import re
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, date
from datetime import timedelta
import uuid
from crawl4ai import CrawlerRunConfig, CacheMode
from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger

# 크롤링 설정 정의
prtimes_config = {
    "base_url": "https://prtimes.jp",
    "search_path": "/main/action.php?run=html&page=searchkey&search_word={keyword}&search_pattern=1",
    "selectors": {
        "list_container": "#__next > div > div > main > div > div > section > div.release-card-list_container__RfZzG",
        "article_item": "article",
        "article_title": "a > div > h3",
        "article_link": "a",
        "article_date": "a > div > span > time",
        "article_body": "#press-release-body > div",
        "load_more_btn": "#__next > div > div > main > div > div > section > div.release-more-button_more__WeIJc > button"
    },
    "exclude": "",
    "regex": {
        "date_extract": r"(\d{4})年(\d{1,2})月(\d{1,2})日"
    }
}

class PRTimesScraper(BaseScraper):
    """ PR Times에서 기사를 크롤링하는 스크래퍼입니다. """

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "prtimes"
        self.config = prtimes_config
        self.logger = get_logger(self.source_name)

        # 상태 관리 변수 초기화
        self.yielded_count = 0
        self.previous_article_count = 0          # 이전까지 로드된 기사 개수 ('더보기'로 추가된 기사 식별용)
        self.consecutive_seen_count = 0          # 연속 중복 기사 발견 횟수 (Early Stop용)
        self.sem = asyncio.Semaphore(getattr(self, 'sem_num', 5)) # BaseScraper의 sem_num 활용 (없을 시 기본 5)
        
        # PR Times 전용: 동적 로딩을 위한 세션 ID 및 상태
        self.session_id = f"prtimes_session_{uuid.uuid4().hex[:8]}"
        self.is_first_request = True             # 첫 번째 목록 요청 여부 플래그

    async def scrape(self):
        """ 검색 결과 페이지를 더보기 버튼으로 확장하며 기사 페이지를스크래핑 """
        
        while not self._is_done():
            
            # 1. 기사 목록 HTML 가져오기 (초기 로드 or '더보기' 클릭)
            html = await self._fetch_search_list()
            if not html:
                break

            # 2. 방금 새로 추가된 기사 노드들만 추출
            new_articles = self._extract_new_articles(html)
            if not new_articles:
                self.logger.info("새로운 기사가 없습니다. 수집을 종료합니다.")
                break

            # 3. 새 기사들을 분석하여 Task 생성
            tasks, reached_stop_condition = self._prepare_tasks(new_articles)
            if tasks:
                # 비동기 Task 병렬 실행 및 결과 반환
                async for article_data in self._execute_tasks(tasks):
                    yield article_data

            # 4. 루프 탈출 조건 체크 (날짜 제한 도달 or 연속 중복 횟수 초과)
            max_seen = getattr(self, 'max_consecutive_seen', 5)
            if reached_stop_condition or self.consecutive_seen_count >= max_seen:
                break

            # 다음 루프 준비: 더보기 버튼 클릭을 위한 플래그 전환 및 대기
            self.is_first_request = False
            await asyncio.sleep(1)

    def _is_done(self) -> bool:
        """ 최대 수집 개수(max_items) 도달 여부 체크 """
        return self.max_items > 0 and self.yielded_count >= self.max_items

    async def _fetch_search_list(self) -> str | None:
        """ 검색 목록 페이지 HTML 가져오기 (초기 로드 or '더보기' 클릭) """
        encoded_keyword = urllib.parse.quote(self.keyword)
        target_url = f"{self.config['base_url']}{self.config['search_path'].format(keyword=encoded_keyword)}"

        if self.is_first_request:
            # 초기 로딩
            run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, session_id=self.session_id)
        else:
            # 두 번째 이후부터는 더보기 버튼 클릭 JS 주입
            js_code = f"""
            var btn = document.querySelector('{self.config["selectors"]["load_more_btn"]}');
            if (btn) {{ btn.click(); }}
            """
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                session_id=self.session_id,
                js_code=js_code,
                delay_before_return_html=2.0
            )

        result = await self.crawler.arun(url=target_url, config=run_config)
        return result.html if result.success else None

    def _extract_new_articles(self, html: str) -> list:
        """ 전체 HTML에서 이전에 파싱하지 않은 '새롭게 로드된 기사'만 잘라내어 반환합니다. """
        soup = BeautifulSoup(html, "html.parser")
        list_container = soup.select_one(self.config["selectors"]["list_container"])
        
        if not list_container:
            self.logger.warning("리스트 컨테이너를 찾을 수 없습니다.")
            return []

        articles = list_container.select(self.config["selectors"]["article_item"])
        
        # 새롭게 불러온 기사가 있다면 슬라이싱을 통해 필터링
        if len(articles) > self.previous_article_count:
            new_articles = articles[self.previous_article_count:]
            self.previous_article_count = len(articles)
            return new_articles
        
        return []

    def _parse_date(self, article_node) -> date | None:
        """ 기사 노드에서 날짜를 추출합니다. ('57分前', '8時間前', 또는 '2026年3月10日') """
        time_tag = article_node.select_one(self.config["selectors"]["article_date"])
        date_text = time_tag.get_text(strip=True) if time_tag else ""
        
        if not date_text:
            return None

        # 1. '분 전' 처리 (현재 시간에서 N분 빼기)
        if "分前" in date_text:
            match = re.search(r"(\d+)分前", date_text)
            if match:
                minutes = int(match.group(1))
                return (datetime.now() - timedelta(minutes=minutes)).date()
                
        # 2. '시간 전' 처리 (현재 시간에서 N시간 빼기)
        elif "時間前" in date_text:
            match = re.search(r"(\d+)時間前", date_text)
            if match:
                hours = int(match.group(1))
                return (datetime.now() - timedelta(hours=hours)).date()
                
        # 3. 기타 '前'이 붙은 예외 상황 (안전장치)
        elif "前" in date_text:
            return date.today()
        
        # 4. 일반 날짜 처리 ('2026年3月10日' 형식)
        date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text)
        if date_match:
            return date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            
        return None

    def _prepare_tasks(self, new_articles: list) -> tuple:
        """ 수집할 기사들을 선별하고 비동기 크롤링 task 리스트를 반환 """
        tasks = []
        reached_stop_condition = False
        article_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

        for article in new_articles:
            link_tag = article.select_one(self.config["selectors"]["article_link"])
            if not link_tag or not link_tag.get("href"):
                continue

            full_url = urllib.parse.urljoin(self.config['base_url'], link_tag.get("href"))
            pub_date = self._parse_date(article)

            # 날짜 및 중복(Early Stop) 검사 로직
            if pub_date and pub_date < self.start_date:
                self.logger.info("지정된 수집 기간(시작일) 이전 기사에 도달하여 수집을 종료합니다.")
                reached_stop_condition = True
                break
            
            if self._should_skip(full_url, pub_date):
                max_seen = getattr(self, 'max_consecutive_seen', 5)
                if self.consecutive_seen_count >= max_seen:
                    self.logger.info(f"연속 {max_seen}번 중복 기사 발견, 수집을 조기 종료합니다.")
                    reached_stop_condition = True
                    break
                continue

            # 제목 추출 및 키워드 필터링
            title_tag = article.select_one(self.config["selectors"]["article_title"])
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            if self.keyword not in title:
                self.logger.debug(f"Skipping: keyword not in title — {title}")
                continue

            tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config))
        
        return tasks, reached_stop_condition

    def _should_skip(self, url: str, pub_date: date) -> bool:
        """ 기사를 스킵해야 하는지 판단합니다 (미래 날짜 및 중복 URL). """
        if pub_date and pub_date > self.end_date:
            return True
        
        if url in self.seen_urls:
            self.consecutive_seen_count += 1
            return True
            
        self.consecutive_seen_count = 0  
        return False

    async def _execute_tasks(self, tasks: list):
        """ 생성된 태스크들을 실행하고 결과를 Yield 합니다. """
        results = await asyncio.gather(*tasks)
        for data in results:
            if data and not self._is_done():
                self.seen_urls.add(data["url"])
                self.yielded_count += 1
                yield data

    async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig) -> dict | None:
        """ 개별 기사의 본문을 추출합니다. """
        async with self.sem:
            result = await self.crawler.arun(url=url, config=config)
            
            if result.success and result.html:
                article_soup = BeautifulSoup(result.html, "html.parser")
                body_elem = article_soup.select_one(self.config["selectors"]["article_body"])
                
                content = ""
                if body_elem:
                    p_tags = body_elem.select("p")
                    content = "\n\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

                return {
                    "source": self.source_name,
                    "keyword": self.keyword,
                    "url": url,
                    "title": title,
                    "content": content,
                    "published_date": pub_date,
                }
            return None
