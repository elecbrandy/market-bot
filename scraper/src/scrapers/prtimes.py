# import re
# import asyncio
# import urllib.parse
# from bs4 import BeautifulSoup
# from datetime import datetime, date
# import uuid

# from crawl4ai import CrawlerRunConfig, CacheMode

# from src.scrapers.base import BaseScraper
# from src.utils.logger import get_logger


# class PRTimesScraper(BaseScraper):
#     """
#     PR Times에서 기사를 크롤링하는 스크래퍼입니다.
#      - 검색 URL: https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word={keyword}&search_pattern=1
#      - 기사 URL 구조: /main/html/rd/p/... 형태
#      - 본문 선택자: #press-release-body > div 안의 모든 p 태그
#      - 리스트 확장: '더보기' 버튼 클릭을 통한 동적 렌더링 (session_id, js_code 활용)
#      - 날짜 포맷: 2026年3月10日 10時00分 -> 2026-03-10
#     """
#     source_name = "prtimes"
#     BASE_DOMAIN  = "prtimes.jp"

#     config = {
#         "base_url": "https://prtimes.jp",
#         "search_path": "/main/action.php?run=html&page=searchkey&search_word={keyword}&search_pattern=1",
#         "selectors": {
#             "list_container": "#__next > div > div > main > div > div > section > div.release-card-list_container__RfZzG",
#             "article_item": "article",
#             "article_title": "a > div > h3",
#             "article_link": "a",
#             "article_date": "a > div > span > time",
#             "article_body": "#press-release-body > div",
#             "load_more_btn": "#__next > div > div > main > div > div > section > div.release-more-button_more__WeIJc > button"
#         },
#         "exclude": "",
#     }

#     def __init__(self, crawler, keyword, start_date, end_date, seen_urls, max_items=0):
#         super().__init__(crawler, keyword, start_date, end_date, seen_urls, max_items)
#         self.source_name = "prtimes"
#         self.logger      = get_logger(self.source_name)

#     async def _fetch_article(self, url: str, pub_date: date, title: str, config: CrawlerRunConfig, sem: asyncio.Semaphore):
#         """
#         개별 기사 페이지(상세)를 크롤링하여 본문 p 태그의 텍스트만 추출합니다.
#         """
#         async with sem:
#             result = await self.crawler.arun(url=url, config=config)
#             if result.success:
#                 article_soup = BeautifulSoup(result.html, "html.parser")

#                 # 본문 래퍼 탐색
#                 body_elem = article_soup.select_one(self.config["selectors"]["article_body"])
                
#                 content = ""
#                 if body_elem:
#                     # 내부의 모든 p 태그만 추출
#                     p_tags = body_elem.select("p")
#                     content = "\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])

#                 return {
#                     "source": self.source_name,
#                     "keyword": self.keyword,
#                     "url": url,
#                     "title": title,
#                     "content": content,
#                     "published_date": pub_date,
#                 }
#             return None

#     async def scrape(self):
#         """
#         더보기 버튼을 클릭하며 PR Times 검색 결과를 순회하고 각 기사를 크롤링합니다.
#         """
#         yielded_count = 0
#         sem = asyncio.Semaphore(5)  # 동시 요청 수 제한
        
#         # PR Times는 보통 UTF-8 인코딩을 사용
#         encoded_keyword = urllib.parse.quote(self.keyword)
#         target_url = f"{self.config['base_url']}{self.config['search_path'].format(keyword=encoded_keyword)}"
        
#         # 세션 ID를 생성하여 "더보기" 버튼 클릭 간 브라우저 상태를 유지
#         session_id = f"prtimes_session_{uuid.uuid4().hex[:8]}"
        
#         # 개별 기사 접속용 설정 (캐시 바이패스, 상태유지 불필요)
#         article_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

#         # 초기 목록 조회 설정
#         list_run_config = CrawlerRunConfig(
#             cache_mode=CacheMode.BYPASS, 
#             session_id=session_id
#         )

#         previous_article_count = 0
        
#         # 💡 [Early Stop] 연속 중복 카운터 설정
#         consecutive_seen_count = 0
#         MAX_CONSECUTIVE_SEEN = 5

#         while True:
#             if self.max_items > 0 and yielded_count >= self.max_items:
#                 break

#             # 현재 상태의 목록 HTML 수집 (최초 접속 또는 더보기 클릭 후)
#             result = await self.crawler.arun(url=target_url, config=list_run_config)
#             if not result.success:
#                 break

#             soup = BeautifulSoup(result.html, "html.parser")
#             list_container = soup.select_one(self.config["selectors"]["list_container"])

#             if not list_container:
#                 self.logger.warning("리스트 컨테이너를 찾을 수 없습니다.")
#                 break

#             articles = list_container.select(self.config["selectors"]["article_item"])
            
#             # 새롭게 불러온 기사가 없다면(더보기 버튼을 눌렀는데도 갯수가 그대로라면) 종료
#             if len(articles) <= previous_article_count:
#                 self.logger.info("새로운 기사가 없습니다. 수집을 종료합니다.")
#                 break
            
#             # 새로 추가된 기사들만 처리하기 위해 슬라이싱
#             new_articles = articles[previous_article_count:]
#             previous_article_count = len(articles)

#             tasks = []
#             reached_old_date = False
#             reached_seen_limit = False # Early Stop 달성 여부 플래그

#             for article in new_articles:
#                 link_tag = article.select_one(self.config["selectors"]["article_link"])
#                 if not link_tag:
#                     continue

#                 href = link_tag.get("href")
#                 if not href:
#                     continue

#                 full_url = urllib.parse.urljoin(self.config['base_url'], href)

#                 # 날짜 추출 및 파싱 ("2026年3月10日 10時00分" 형식)
#                 time_tag = article.select_one(self.config["selectors"]["article_date"])
#                 date_text = time_tag.get_text(strip=True) if time_tag else ""
                
#                 date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text)
#                 if not date_match:
#                     continue

#                 pub_date = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))

#                 # 시작일보다 과거의 기사면 루프 종료 플래그 설정
#                 if pub_date < self.start_date:
#                     reached_old_date = True
#                     break
#                 # 종료일보다 미래의 기사면 스킵
#                 if pub_date > self.end_date:
#                     continue

#                 # 💡 Early Stop 적용
#                 if full_url in self.seen_urls:
#                     consecutive_seen_count += 1
#                     if consecutive_seen_count >= MAX_CONSECUTIVE_SEEN:
#                         self.logger.info(f"이미 수집한 기사가 연속 {MAX_CONSECUTIVE_SEEN}번 발견되어 조기 종료(Early Stop)합니다.")
#                         reached_seen_limit = True
#                         break
#                     continue
#                 else:
#                     consecutive_seen_count = 0

#                 # 제목 추출
#                 title_tag = article.select_one(self.config["selectors"]["article_title"])
#                 title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

#                 if self.keyword not in title:
#                     self.logger.debug(f"Skipping: keyword not in title — {title}")
#                     continue

#                 tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

#             if tasks:
#                 results = await asyncio.gather(*tasks)
#                 for article_data in results:
#                     if article_data and (self.max_items == 0 or yielded_count < self.max_items):
#                         self.seen_urls.add(article_data["url"])
#                         yielded_count += 1
#                         yield article_data

#             # 💡 Early Stop 조건이거나 시작일에 도달했으면 while 무한루프(더보기 클릭) 탈출
#             if reached_old_date or reached_seen_limit:
#                 if reached_old_date:
#                     self.logger.info("지정된 수집 기간(시작일) 이전 기사에 도달하여 수집을 종료합니다.")
#                 break

#             # 더보기 버튼 클릭을 위한 JS 스크립트 실행 (다음 루프 준비)
#             js_code = f"""
#             var btn = document.querySelector('{self.config["selectors"]["load_more_btn"]}');
#             if (btn) {{
#                 btn.click();
#             }}
#             """
            
#             # 다음 루프에서는 해당 세션 안에서 버튼을 클릭하도록 config 갱신
#             list_run_config = CrawlerRunConfig(
#                 cache_mode=CacheMode.BYPASS,
#                 session_id=session_id,
#                 js_code=js_code,
#                 delay_before_return_html=2.0
#             )
#             await asyncio.sleep(1)
