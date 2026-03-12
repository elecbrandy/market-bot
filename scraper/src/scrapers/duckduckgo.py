import re
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, date
import uuid

from crawl4ai import CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger


class DuckDuckGoScraper(BaseScraper):
    """
    DuckDuckGo 검색 엔진을 활용하여 키워드 관련 웹 문서를 크롤링하는 범용 스크래퍼입니다.
     - 검색 URL: https://duckduckgo.com/?q={keyword}&df=y (최근 1년 필터 적용)
     - 특징: 외부 사이트(다양한 도메인)로 연결되므로, PruningContentFilter를 사용해 본문만 자동 추출합니다.
    """
    source_name = "duckduckgo"

    config = {
        "base_url": "https://duckduckgo.com",
        "search_path": "/?q={keyword}&df=y", # df=y (최근 1년) 등 시간 필터를 걸어 노이즈를 줄입니다.
        "selectors": {
            "article_item": "[data-testid='result']",
            "article_link": "[data-testid='result-title-a']",
            "article_snippet": "[data-testid='result-snippet']",
            # 더보기 버튼 또는 무한 스크롤 감지용
            "load_more_btn": "button#more-results" 
        }
    }

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "duckduckgo"
        self.logger      = get_logger(self.source_name)

    async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig, sem: asyncio.Semaphore):
        """
        임의의 외부 사이트 페이지를 방문하여 마크다운 본문을 추출합니다.
        CSS 셀렉터 대신 Crawl4AI의 PruningContentFilter 알고리즘을 사용해 본문을 추론합니다.
        """
        async with sem:
            result = await self.crawler.arun(url=url, config=config)
            
            if result.success and result.markdown:
                content = result.markdown.strip()
                
                # 본문이 너무 짧으면 가치가 없는 페이지(또는 캡챠 차단)로 간주
                if len(content) < 50:
                    self.logger.debug(f"Skipping extremely short content at {url}")
                    return None

                return {
                    "source": self.source_name,
                    "keyword": self.keyword,
                    "url": url,
                    "title": title,
                    "content": content,
                    "published_date": pub_date,
                }
            return None

    async def scrape(self):
        yielded_count = 0
        sem = asyncio.Semaphore(5)

        encoded_keyword = urllib.parse.quote(self.keyword)
        target_url = f"{self.config['base_url']}{self.config['search_path'].format(keyword=encoded_keyword)}"

        session_id = f"ddg_session_{uuid.uuid4().hex[:8]}"

        # 💡 [범용 본문 추출 설정] 다양한 사이트를 대응하기 위한 노이즈 제거 필터
        md_generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.45,
                threshold_type="fixed",
                min_word_threshold=10
            ),
            options={"ignore_links": True, "ignore_images": True}
        )

        article_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            markdown_generator=md_generator
            # 특정 css_selector를 지정하지 않고 AI 필터에 온전히 맡깁니다.
        )

        list_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            session_id=session_id
        )

        previous_page_urls = set()
        consecutive_seen_count = 0
        MAX_CONSECUTIVE_SEEN = 5
        
        # 검색 엔진 특성상 최대 페이지(스크롤)를 너무 많이 가지 않도록 하드 리밋 설정
        max_scroll_attempts = 10 
        scroll_count = 0

        while scroll_count < max_scroll_attempts:
            if self.max_items > 0 and yielded_count >= self.max_items:
                break

            result = await self.crawler.arun(url=target_url, config=list_run_config)
            if not result.success:
                self.logger.warning("DuckDuckGo 검색 결과 페이지 로드에 실패했습니다.")
                break

            soup = BeautifulSoup(result.html, "html.parser")
            articles = soup.select(self.config["selectors"]["article_item"])

            if not articles:
                self.logger.debug("검색된 결과 항목이 없습니다.")
                break

            tasks = []
            reached_seen_limit = False
            current_page_urls = set()

            for article in articles:
                link_tag = article.select_one(self.config["selectors"]["article_link"])
                if not link_tag:
                    continue

                full_url = link_tag.get("href")
                if not full_url or full_url.startswith("javascript:"):
                    continue
                
                # DuckDuckGo의 광고 링크나 내부 리다이렉트 필터링
                if "duckduckgo.com/y.js" in full_url or "ad_provider" in full_url:
                    continue

                current_page_urls.add(full_url)

                # 외부 사이트는 날짜를 특정하기 어려우므로, 오늘 날짜로 통일하거나 크롤링 시점의 날짜 부여
                # (DuckDuckGo는 날짜 메타데이터를 깔끔하게 제공하지 않는 경우가 많음)
                pub_date = date.today()

                if pub_date < self.start_date or pub_date > self.end_date:
                    continue

                if full_url in self.seen_urls:
                    consecutive_seen_count += 1
                    if consecutive_seen_count >= MAX_CONSECUTIVE_SEEN:
                        self.logger.info(f"이미 수집한 웹사이트가 연속 {MAX_CONSECUTIVE_SEEN}번 발견되어 조기 종료(Early Stop)합니다.")
                        reached_seen_limit = True
                        break
                    continue
                else:
                    consecutive_seen_count = 0

                title = link_tag.get_text(separator=" ", strip=True)
                
                # 제목에 키워드가 없는 경우 무분별한 외부 수집을 막기 위해 필터링
                if self.keyword.lower() not in title.lower():
                    continue

                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

            # 무한 루프 방지: 새로 긁어온 URL 목록이 이전 스크롤 상태와 완전히 같다면 더 이상 항목이 없는 것
            if current_page_urls and current_page_urls.issubset(previous_page_urls):
                self.logger.info("더 이상 새로운 검색 결과가 표시되지 않습니다. 수집을 종료합니다.")
                break
            
            previous_page_urls.update(current_page_urls)

            if tasks:
                results = await asyncio.gather(*tasks)
                for article_data in results:
                    if article_data and (self.max_items == 0 or yielded_count < self.max_items):
                        self.seen_urls.add(article_data["url"])
                        yielded_count += 1
                        yield article_data

            if reached_seen_limit:
                break

            # 스크롤을 내리거나 "더보기" 버튼을 누르는 자바스크립트 실행
            js_code = f"""
            var btn = document.querySelector('{self.config["selectors"]["load_more_btn"]}');
            if (btn && btn.offsetHeight > 0) {{
                btn.click();
            }} else {{
                window.scrollTo(0, document.body.scrollHeight);
            }}
            """
            
            list_run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                session_id=session_id,
                js_code=js_code,
                delay_before_return_html=2.0 # 클릭/스크롤 후 렌더링 대기
            )
            
            scroll_count += 1
            await asyncio.sleep(1)