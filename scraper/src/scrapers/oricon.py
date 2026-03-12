import re
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, date

from crawl4ai import CrawlerRunConfig, CacheMode

from src.scrapers.base import BaseScraper
from src.utils.logger import get_logger


class OriconScraper(BaseScraper):
    """
    Oricon News에서 기사를 크롤링하는 스크래퍼입니다.
     - 검색 URL: https://www.oricon.co.jp/search/result.php?p={page}&types=article&search_string={keyword}
     - 기사 URL 구조: /article/{article_id}/ 형태
     - 본문 원본 URL 선택자: #cont > div.read-more > p > a
       → oricon.co.jp 도메인인 경우만 스크랩, 외부 사이트면 스킵
     - 날짜 포맷: 2025-03-10
    """
    source_name = "oricon"
    BASE_DOMAIN  = "www.oricon.co.jp"

    config = {
        "base_url": "https://www.oricon.co.jp",
        "search_path": "/search/result.php?p={page}&types=article&search_string={keyword}",
        "selectors": {
            "list_container": "#content-main > article > div.block-title-list",
            "article_item": "article",
            "article_link": "a",
            "read_more_link": "#cont > div.read-more > p > a",   # 원본 기사 링크
            "article_body": "#content-main > div > article > div.block-detail-body > div.mod-p",
        },
        "exclude": ".inner-photo, a, .comment-btn, ._ap_apex_ad, .block-banner",
    }

    def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
        super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
        self.source_name = "oricon"
        self.logger      = get_logger(self.source_name)

    def _is_oricon_url(self, url: str) -> bool:
        """URL이 oricon.co.jp 도메인인지 확인합니다."""
        try:
            return urllib.parse.urlparse(url).hostname == self.BASE_DOMAIN
        except Exception:
            return False

    async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig, sem: asyncio.Semaphore):
        """
        개별 기사 페이지를 크롤링합니다.
        read-more 링크가 있으면 해당 URL을 확인하고,
        외부 사이트면 스킵, 오리콘이면 그 URL로 본문을 가져옵니다.
        """
        async with sem:
            # 1단계: 기사 페이지 fetch (read-more 링크 확인용, 캐시 없이)
            peek_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            peek = await self.crawler.arun(url=url, config=peek_config)
            if not peek.success:
                return None

            # read-more 링크 추출
            soup = BeautifulSoup(peek.html, "html.parser")
            read_more_tag = soup.select_one(self.config["selectors"]["read_more_link"])

            if read_more_tag:
                read_more_href = read_more_tag.get("href", "")
                # 상대 경로면 절대 경로로 변환
                read_more_url = urllib.parse.urljoin(self.config["base_url"], read_more_href)

                if not self._is_oricon_url(read_more_url):
                    # 외부 사이트 → 스킵
                    self.logger.debug(f"Skipping external source: {read_more_url} (from {url})")
                    return None

                # 오리콘 내부 URL → 해당 페이지 본문 스크랩 (/full/ 붙임)
                target_url = read_more_url.rstrip("/") + "/full/"
            else:
                # read-more 링크 없음 → 현재 페이지 본문 그대로 사용
                target_url = url.rstrip("/") + "/full/"

            # 2단계: 실제 본문 스크랩
            result = await self.crawler.arun(url=target_url, config=config)
            if result.success:
                article_soup = BeautifulSoup(result.html, "html.parser")

                # 불필요한 요소(광고, 사진, 댓글 버튼 등) HTML 트리에서 제거
                exclude_selector = self.config.get("exclude")
                if exclude_selector:
                    for el in article_soup.select(exclude_selector):
                        el.decompose()

                # 본문 텍스트 추출
                body_elem = article_soup.select_one(self.config["selectors"]["article_body"])
                
                # 본문 요소가 있으면 태그를 모두 제거하고 텍스트만 추출 (줄바꿈으로 구분)
                content = body_elem.get_text(separator="\n", strip=True) if body_elem else ""

                return {
                    "source": self.source_name,
                    "keyword": self.keyword,
                    "url": target_url,
                    "title": title,
                    "content": content,
                    "published_date": pub_date,
                }
            return None

    async def scrape(self):
        """
        Oricon 검색 결과를 순회하며 기사 링크와 날짜를 수집하고, 각 기사를 크롤링합니다.
        """
        page_num = 1
        yielded_count = 0
        sem = asyncio.Semaphore(5)  # 동시 요청 수 제한

        try:
            # 오리콘 서버는 검색 키워드를 Shift-JIS로 인코딩해야 인식
            encoded_keyword = urllib.parse.quote(self.keyword.encode('shift_jis', errors="replace"))
            self.logger.info(f"Searching with Shift-JIS encoded keyword: {self.keyword}")
        except Exception as e:
            self.logger.warning(f"Shift-JIS encoding failed, using UTF-8: {e}")
            encoded_keyword = urllib.parse.quote(self.keyword)

        # 본문 페이지 크롤링용 설정 (마크다운 제너레이터 없이 HTML만 가져오도록 설정)
        article_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

        while True:
            if self.max_items > 0 and yielded_count >= self.max_items:
                break

            search_path = self.config["search_path"].format(keyword=encoded_keyword, page=page_num)
            target_url  = f"{self.config['base_url']}{search_path}"

            list_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            result = await self.crawler.arun(url=target_url, config=list_run_config)

            if not result.success:
                break

            soup = BeautifulSoup(result.html, "html.parser")
            list_container = soup.select_one(self.config["selectors"]["list_container"])

            if not list_container:
                break

            articles = list_container.select(self.config["selectors"]["article_item"])
            if not articles:
                break

            tasks = []
            reached_old_date = False

            for article in articles:
                link_tag = article.select_one(self.config["selectors"]["article_link"])
                if not link_tag:
                    continue

                href = link_tag.get("href")
                if not href:
                    continue

                full_url = f"{self.config['base_url']}{href}" if href.startswith("/") else href

                # 날짜 추출
                time_tag = article.select_one("time")
                date_text = time_tag.get_text(strip=True) if time_tag else article.get_text(strip=True)

                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                if not date_match:
                    continue

                pub_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()

                if pub_date < self.start_date:
                    reached_old_date = True
                    break
                if pub_date > self.end_date:
                    continue

                if full_url in self.seen_urls:
                    continue

                title = link_tag.get("title") or link_tag.get_text(separator=" ", strip=True)
                title = title.replace(date_match.group(1), "").strip()

                if self.keyword not in title:
                    self.logger.debug(f"Skipping: keyword not in title — {title}")
                    continue

                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

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
            await asyncio.sleep(1)
