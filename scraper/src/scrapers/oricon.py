import re
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, date
from crawl4ai import CrawlerRunConfig, CacheMode
from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger

# 크롤링 설정 정의
oricon_config = {
    "base_url": "https://www.oricon.co.jp",
    "search_path": "/search/result.php?p={page}&types=article&search_string={keyword}",
    "selectors": {
        "list_container": "#content-main > article > div.block-title-list",
        "article_item": "article",
        "article_link": "a",
        "read_more_link": "div.read-more a", 
        "article_body": "#content-main > div > article > div.block-detail-body > div.mod-p",
        "news_jp_body": "div.main__postBody > article > div", 
    },
    "exclude": ".inner-photo, a, .comment-btn, ._ap_apex_ad, .block-banner",
}

class OriconScraper(BaseScraper):
    """ Oricon에서 뉴스를 크롤링하는 스크래퍼입니다. """

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "oricon"
        self.config = oricon_config
        self.logger = get_logger(self.source_name)

        self.yielded_count = 0
        self.previous_page_urls = set()
        self.consecutive_seen_count = 0
        self.max_consecutive_seen = 5
        self.sem = asyncio.Semaphore(5)

    @property
    def encoded_keyword(self) -> str:
        try:
            encoded = urllib.parse.quote(self.keyword.encode('shift_jis', errors="replace"))
            return encoded
        except Exception as e:
            self.logger.warning(f"Shift-JIS encoding failed, using UTF-8: {e}")
            return urllib.parse.quote(self.keyword)

    async def scrape(self):
        page_num = 1
        self.logger.info(f"Searching with encoded keyword: {self.keyword}")

        while not self._is_done():
            articles = await self._fetch_search_page(page_num)
            if not articles or self._is_duplicate(articles):
                break

            tasks, reached_old_date = self._prepare_tasks(articles)
            if tasks:
                async for article_data in self._execute_tasks(tasks):
                    yield article_data

            if reached_old_date or self.consecutive_seen_count >= self.max_consecutive_seen:
                if self.consecutive_seen_count >= self.max_consecutive_seen:
                    self.logger.info(f"이미 수집한 기사가 연속 {self.max_consecutive_seen}번 발견되어 조기 종료합니다.")
                break

            page_num += 1
            await asyncio.sleep(1)

    def _is_done(self) -> bool:
        return self.max_items > 0 and self.yielded_count >= self.max_items
    
    def _is_duplicate(self, articles: list) -> bool:
        current_urls = set()
        for article in articles:
            link_tag = article.select_one(self.config["selectors"]["article_link"])
            if link_tag and link_tag.get("href"):
                current_urls.add(link_tag.get("href"))

        if current_urls and current_urls == self.previous_page_urls:
            self.logger.info("마지막 페이지 도달 (이전 페이지와 동일). 수집을 종료합니다.")
            return True
            
        self.previous_page_urls = current_urls
        return False
    
    def _parse_date_and_title(self, article, link_tag) -> tuple[date | None, str]:
        time_tag = article.select_one("time")
        date_text = time_tag.get_text(strip=True) if time_tag else article.get_text(strip=True)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        
        pub_date = None
        if date_match:
            pub_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()

        title = link_tag.get("title") or link_tag.get_text(separator=" ", strip=True)
        if date_match:
            title = title.replace(date_match.group(1), "").strip()

        return pub_date, title
    
    def _prepare_tasks(self, articles) -> tuple:
        tasks = []
        reached_old_date = False
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

        for article in articles:
            link_tag = article.select_one(self.config["selectors"]["article_link"])
            if not link_tag or not link_tag.get("href"):
                continue

            url = self._build_full_url(link_tag.get("href"))
            pub_date, title = self._parse_date_and_title(article, link_tag)

            if pub_date and pub_date < self.start_date:
                reached_old_date = True
                break
            
            if self._should_skip(url, pub_date, title):
                continue

            tasks.append(self._fetch_article(url, pub_date, title, run_config))
        
        return tasks, reached_old_date
    
    def _should_skip(self, url: str, pub_date: date | None, title: str) -> bool:
        if pub_date and pub_date > self.end_date:
            return True
        if self.keyword not in title:
            self.logger.debug(f"Skipping: keyword not in title — {title}")
            return True
        if url in self.seen_urls:
            self.consecutive_seen_count += 1
            return True
            
        self.consecutive_seen_count = 0  
        return False

    async def _execute_tasks(self, tasks):
        results = await asyncio.gather(*tasks)
        for data in results:
            if data and not self._is_done():
                self.seen_urls.add(data["original_url"]) # 중복 검사는 최초 수집 URL 기준
                self.yielded_count += 1
                
                # yield 할 때 내부 로직용 키(original_url) 제거 후 전달
                data.pop("original_url", None)
                yield data

    def _build_full_url(self, href: str) -> str:
        if not href: return ""
        return f"{self.config['base_url']}{href}" if href.startswith("/") else href

    async def _fetch_search_page(self, page_num: int) -> list:
        search_path = self.config["search_path"].format(keyword=self.encoded_keyword, page=page_num)
        target_url = f"{self.config['base_url']}{search_path}"
        
        result = await self.crawler.arun(url=target_url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
        if not result.success:
            return []
            
        soup = BeautifulSoup(result.html, "html.parser")
        list_container = soup.select_one(self.config["selectors"]["list_container"])
        
        return list_container.select(self.config["selectors"]["article_item"]) if list_container else []

    async def _fetch_article(self, original_url: str, pub_date: date, title: str, config: CrawlerRunConfig) -> dict | None:
        """ 2-Depth 요약 페이지 확인 및 본문 추출 로직 (안전성 강화) """
        async with self.sem:
            try:
                self.logger.info(f"[시작] 요약 페이지 요청: {original_url}")
                
                # 1. 요약 페이지 접속 (30초 타임아웃 강제 지정)
                result = await asyncio.wait_for(
                    self.crawler.arun(url=original_url, config=config),
                    timeout=30.0
                )
                
                if not result.success or not result.html:
                    self.logger.warning(f"[실패] 요약 페이지 로드 불가: {original_url}")
                    return None
                    
                soup = BeautifulSoup(result.html, "html.parser")
                read_more_tag = soup.select_one(self.config["selectors"]["read_more_link"])
                
                target_url = original_url
                is_news_jp = False
                
                if read_more_tag and read_more_tag.get("href"):
                    next_href = read_more_tag.get("href")
                    
                    if "news.jp" in next_href:
                        target_url = next_href
                        is_news_jp = True
                    else:
                        target_url = self._build_full_url(next_href)
                        
                    self.logger.info(f"[진입] 2-Depth 본문 요청: {target_url}")
                    
                    # 3. 실제 본문 페이지로 2차 크롤링 (30초 타임아웃)
                    result = await asyncio.wait_for(
                        self.crawler.arun(url=target_url, config=config),
                        timeout=30.0
                    )
                    
                    if not result.success or not result.html:
                        self.logger.warning(f"[실패] 본문 페이지 로드 불가: {target_url}")
                        return None
                        
                    soup = BeautifulSoup(result.html, "html.parser")

                # 불필요한 요소 제거 (공통)
                exclude_selectors = self.config.get("exclude")
                if exclude_selectors:
                    for s in soup.select(exclude_selectors):
                        s.decompose()

                # 4. 사이트에 따른 본문 추출 분기
                content = ""
                if is_news_jp:
                    content_container = soup.select_one(self.config["selectors"]["news_jp_body"])
                    if content_container:
                        paragraphs = content_container.find_all("p")
                        content = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    else:
                        content = soup.get_text(separator="\n\n", strip=True)
                else:
                    content_container = soup.select_one(self.config["selectors"]["article_body"])
                    if content_container:
                        content = content_container.get_text(separator="\n\n", strip=True)
                    else:
                        content = soup.get_text(separator="\n\n", strip=True)

                self.logger.info(f"[완료] 스크랩 성공: {title[:15]}...")
                
                return {
                    "source": self.source_name,
                    "keyword": self.keyword,
                    "url": target_url,          
                    "original_url": original_url, 
                    "title": title,
                    "content": content,
                    "published_date": pub_date,
                }

            except asyncio.TimeoutError:
                self.logger.error(f"[타임아웃] 페이지 응답 없음 (30초 초과): {original_url}")
                return None
            except Exception as e:
                self.logger.error(f"[에러] {original_url} 처리 중 예외 발생: {e}")
                return None
