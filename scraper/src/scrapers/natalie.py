import re
import time
from datetime import date, datetime
import httpx
from bs4 import BeautifulSoup

from src.models import News
from src.scrapers.base import BaseScraper

class NatalieScraper(BaseScraper):
    def __init__(self, db, keyword, start_date, end_date):
        super().__init__(db, keyword, start_date, end_date)
        self.source_name = "natalie"
        self.base_url = "https://natalie.mu"

    def _parse_date(self, date_text: str):
        """
        'YYYY年M月D日' 또는 'M月D日' 형태의 날짜 텍스트를 파싱하여 date 객체로 반환
        """
        if not date_text:
            return None
        date_text = date_text.strip()
        
        # 1. 과거 기사인 경우 (YYYY年M月D日)
        match_full = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text)
        if match_full:
            return date(int(match_full.group(1)), int(match_full.group(2)), int(match_full.group(3)))
            
        # 2. 올해 기사인 경우 (M月D日) - 올해 연도를 기본값으로 보완
        match_short = re.search(r"(\d{1,2})月(\d{1,2})日", date_text)
        if match_short:
            current_year = date.today().year
            return date(current_year, int(match_short.group(1)), int(match_short.group(2)))
            
        return None

    def scrape(self):
        page_num = 1
        print(f"\n▶ [{self.source_name}] '{self.keyword}' 뉴스 수집 시작...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        with httpx.Client(base_url=self.base_url, headers=headers, follow_redirects=True) as client:
            while True:
                print(f"  [{self.source_name} | {page_num}페이지] 탐색 중... ", end="")
                
                # 검색 URL 파라미터 구성
                params = {
                    "context": "news",
                    "query": self.keyword,
                    "page": page_num
                }

                try:
                    response = client.get("/search", params=params)
                    if response.status_code != 200:
                        print(f"접속 실패(상태 코드: {response.status_code})로 중단합니다.")
                        break
                except Exception as e:
                    print(f"요청 중 에러 발생: {e}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                
                # # CSS 셀렉터로 기사 카드 목록 파싱
                # cards = soup.select("div.NA_card_wrapper > div")
                
                # if not cards:
                #     print("  -> 더 이상 기사가 없습니다. 수집을 종료합니다.")
                #     break

                # added_count = 0
                # for card in cards:
                #     link_tag = card.select_one("a")
                #     if not link_tag:
                #         continue
                        
                #     href = link_tag.get("href")
                #     if not href:
                #         continue

                #     # URL 절대경로 처리
                #     full_url = f"https://natalie.mu{href}" if href.startswith("/") else href
                    
                #     # 기사 제목 추출
                #     title_tag = card.select_one("p.NA_card_title")
                #     title_text = title_tag.text.strip() if title_tag else ""
                    
                #     # 기사 날짜 추출
                #     date_tag = card.select_one("div.NA_card_date")
                #     date_str = date_tag.text.strip() if date_tag else ""
                #     pub_date = self._parse_date(date_str)

                #     # 날짜 조건 필터링 및 DB 중복 확인
                #     if pub_date and self.start_date <= pub_date <= self.end_date:
                #         existing = self.db.query(News).filter(News.url == full_url).first()
                #         if not existing:
                #             new_article = News(
                #                 source=self.source_name,
                #                 keyword=self.keyword,
                #                 title=title_text,   # DB에 제목도 함께 저장 (모델에 title 필드가 있으므로 활용)
                #                 url=full_url,
                #                 published_date=pub_date
                #             )
                #             self.db.add(new_article)
                #             added_count += 1
                # ... 상단 코드 동일 ...
                
                # CSS 셀렉터로 기사 카드 목록 파싱
                cards = soup.select("div.NA_card_wrapper > div")
                
                if not cards:
                    print("  -> 더 이상 기사가 없습니다. 수집을 종료합니다.")
                    break

                added_count = 0
                for card in cards:
                    # 1. 기사 제목을 가장 먼저 정확히 찾습니다.
                    title_tag = card.select_one("p.NA_card_title")
                    if not title_tag:
                        continue
                    title_text = title_tag.text.strip()
                    
                    # 2. 제목 요소의 상위 부모 중 <a> 태그를 찾아 URL을 추출합니다. (태그 링크와의 혼동 방지)
                    link_tag = title_tag.find_parent("a")
                    if not link_tag:
                        continue
                        
                    href = link_tag.get("href")
                    if not href:
                        continue

                    # URL 절대경로 처리
                    full_url = f"https://natalie.mu{href}" if href.startswith("/") else href
                    
                    # 3. 기사 날짜 추출
                    date_tag = card.select_one("div.NA_card_date")
                    date_str = date_tag.text.strip() if date_tag else ""
                    pub_date = self._parse_date(date_str)

                    # 4. 날짜 조건 필터링 및 DB 중복 확인
                    if pub_date and self.start_date <= pub_date <= self.end_date:
                        existing = self.db.query(News).filter(News.url == full_url).first()
                        if not existing:
                            new_article = News(
                                source=self.source_name,
                                keyword=self.keyword,
                                title=title_text,
                                url=full_url,
                                published_date=pub_date
                            )
                            self.db.add(new_article)
                            added_count += 1
                
                self.db.commit()

                self.db.commit()
                print(f"-> {added_count}개 기사 저장 완료.")
                
                # 페이지 내에서 새로 수집된 기사가 없으면 검색 중단 (이전 기사들에 도달했다고 판단)
                if added_count == 0:
                    print("  -> 수집할 새 기사가 없으므로 검색을 중단합니다.")
                    break
                
                page_num += 1
                time.sleep(1.5)  # 서버 부하 방지를 위한 딜레이
