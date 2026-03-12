import re
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, date

from crawl4ai import CrawlerRunConfig, CacheMode

from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger


class NatalieScraper(BaseScraper):
    """
    Natalie(natalie.mu)에서 기사를 크롤링하는 스크래퍼입니다.
    """
    source_name = "natalie"
    BASE_DOMAIN = "natalie.mu"

    config = {
        "base_url": "https://natalie.mu",
        "search_path": "/search?context=news&query={keyword}&page={page}",
        "selectors": {
            "list_container": ".NA_card_wrapper",
            "article_item": ".NA_card_wrapper > div > a", 
            "article_title": ".NA_card_text p.NA_card_title",
            "article_date": ".NA_card_text .NA_card_date",
            "article_body": "#app > div.NA_layout_2col > div.NA_layout_2col_left > main > article > div.NA_article_body",
        },
        # 1차 필터링: Crawl4AI exclude selector를 통한 렌더링 단계 제거
        "exclude": (
            ".inner-photo, a, .comment-btn, ._ap_apex_ad, .block-banner, "
            ".NA_article_fig, .NA_article_link, .NA_article_tagad, "
            ".NA_article_gallery, .NA_article_copyright, .NA_article_socialfav, "
            ".NA_article_social, .NA_article_tag, "
            "[spottype='fixed_mc'], [data-cmp='app-user-favorite']"
        ),
    }

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "natalie"
        self.logger      = get_logger(self.source_name)

    def _parse_date(self, date_text: str) -> date:
        """
        Natalie 기사 날짜 파싱. 연도가 없는 경우 올해 연도를 부여하되,
        그 결과가 오늘 날짜보다 미래라면 작년 기사로 처리합니다.
        """
        date_str = date_text.split(" ")[0].strip()
        
        try:
            if "年" in date_str:
                return datetime.strptime(date_str, "%Y年%m月%d日").date()
            else:
                current_date = datetime.now().date()
                parsed_date = datetime.strptime(date_str, "%m月%d日").date()
                candidate_date = parsed_date.replace(year=current_date.year)
                
                # 💡 버그 수정: 부여된 날짜가 오늘보다 미래면 작년으로 처리
                if candidate_date > current_date:
                    return candidate_date.replace(year=current_date.year - 1)
                return candidate_date
        except ValueError as e:
            self.logger.warning(f"Failed to parse date '{date_text}': {e}")
            return None

    async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig, sem: asyncio.Semaphore):
        """
        개별 기사 본문을 파싱할 때 불필요한 노드를 DOM에서 완전히 제거한 후 텍스트를 추출합니다.
        """
        async with sem:
            result = await self.crawler.arun(url=url, config=config)
            
            if result.success and result.html:
                soup = BeautifulSoup(result.html, "html.parser")
                
                # 2차 필터링: BeautifulSoup 단계에서 불필요한 태그 완벽히 도려내기
                unwanted_selectors = [
                    ".NA_article_fig", ".NA_article_link", ".NA_article_tagad",
                    ".NA_article_gallery", ".NA_article_copyright", ".NA_article_socialfav",
                    ".NA_article_social", ".NA_article_tag",
                    "[spottype='fixed_mc']", "[data-cmp='app-user-favorite']"
                ]
                
                for selector in unwanted_selectors:
                    for el in soup.select(selector):
                        el.decompose()  # 트리에서 해당 노드 및 하위 요소 완전히 삭제
                
                # 불순물이 제거된 상태에서 <p> 태그 찾기
                paragraphs = soup.find_all("p")
                
                if paragraphs:
                    content = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                else:
                    content = soup.get_text(separator="\n\n", strip=True)

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
        page_num = 1
        yielded_count = 0
        sem = asyncio.Semaphore(5)

        encoded_keyword = urllib.parse.quote(self.keyword)

        article_run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            css_selector=self.config["selectors"]["article_body"],
            excluded_selector=self.config["exclude"]
        )

        # 💡 [무한루프 방지] 이전 페이지 URL 집합
        previous_page_urls = set()
        
        # 💡 [Early Stop] 연속 중복 카운터
        consecutive_seen_count = 0
        MAX_CONSECUTIVE_SEEN = 5

        while True:
            if self.max_items > 0 and yielded_count >= self.max_items:
                break

            search_path = self.config["search_path"].format(keyword=encoded_keyword, page=page_num)
            target_url  = f"{self.config['base_url']}{search_path}"

            list_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            result = await self.crawler.arun(url=target_url, config=list_run_config)

            if not result.success:
                self.logger.warning(f"Failed to fetch search page {page_num}: {target_url}")
                break

            soup = BeautifulSoup(result.html, "html.parser")
            list_container = soup.select_one(self.config["selectors"]["list_container"])

            if not list_container:
                self.logger.debug("No list container found. Ending scrape.")
                break

            articles = soup.select(self.config["selectors"]["article_item"])
            if not articles:
                self.logger.debug("No articles found on this page. Ending scrape.")
                break

            tasks = []
            reached_old_date = False
            reached_seen_limit = False
            current_page_urls = set()

            for article in articles:
                href = article.get("href")
                if not href:
                    continue
                
                if "/tag/" in href:
                    continue

                full_url = urllib.parse.urljoin(self.config["base_url"], href)
                current_page_urls.add(full_url)

                date_tag = article.select_one(self.config["selectors"]["article_date"])
                date_text = date_tag.get_text(strip=True) if date_tag else ""
                
                pub_date = self._parse_date(date_text)
                if not pub_date:
                    continue

                if pub_date < self.start_date:
                    reached_old_date = True
                    break
                if pub_date > self.end_date:
                    continue

                # 💡 Early Stop 적용
                if full_url in self.seen_urls:
                    consecutive_seen_count += 1
                    if consecutive_seen_count >= MAX_CONSECUTIVE_SEEN:
                        self.logger.info(f"이미 수집한 기사가 연속 {MAX_CONSECUTIVE_SEEN}번 발견되어 조기 종료(Early Stop)합니다.")
                        reached_seen_limit = True
                        break
                    continue
                else:
                    consecutive_seen_count = 0

                title_tag = article.select_one(self.config["selectors"]["article_title"])
                title = title_tag.get_text(separator=" ", strip=True) if title_tag else "No Title"

                if self.keyword not in title:
                    self.logger.debug(f"Skipping: keyword not in title — {title}")
                    continue

                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

            # 💡 무한 루프 방지: 이전 페이지와 완전 동일한 기사 목록이라면 탐색 종료
            if current_page_urls and current_page_urls == previous_page_urls:
                self.logger.info("마지막 페이지에 도달했습니다 (이전 페이지와 동일). 수집을 종료합니다.")
                break
            
            previous_page_urls = current_page_urls

            if tasks:
                results = await asyncio.gather(*tasks)
                for article_data in results:
                    if article_data and (self.max_items == 0 or yielded_count < self.max_items):
                        self.seen_urls.add(article_data["url"])
                        yielded_count += 1
                        yield article_data

            if reached_old_date or reached_seen_limit:
                if reached_old_date:
                    self.logger.info("Reached articles older than start_date. Stopping crawler.")
                break

            page_num += 1
            await asyncio.sleep(1)
