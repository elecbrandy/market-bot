import re
import time
import httpx
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from src.models import News
from src.scrapers.base import BaseScraper

class OriconScraper(BaseScraper):
    def __init__(self, db, keyword, start_date, end_date):
        super().__init__(db, keyword, start_date, end_date)
        self.source_name = "oricon"
        self.base_url = "https://www.oricon.co.jp"

    def _parse_date(self, date_str: str):
        """ '2025-03-10' 형태의 날짜 텍스트를 파싱하여 date 객체로 반환 """
        if not date_str:
            return None
        
        # 정규식을 이용해 YYYY-MM-DD 형식만 안전하게 추출 (번역 태그 등에 의한 공백 무시)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        return None

    def scrape(self):
        page_num = 1
        print(f"\n▶ [{self.source_name}] '{self.keyword}' 뉴스 수집 시작...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        # 1. 키워드를 Shift-JIS로 URL 인코딩
        try:
            encoded_keyword = urllib.parse.quote(self.keyword, encoding="shift_jis")
        except UnicodeEncodeError:
            print(f"  ⚠ Shift-JIS로 변환할 수 없는 문자가 포함되어 있습니다: {self.keyword}")
            return

        with httpx.Client(base_url=self.base_url, headers=headers, follow_redirects=True) as client:
            while True:
                # 2. 인코딩된 키워드를 URL에 삽입
                target_path = f"/search/result.php?p={page_num}&types=article&search_string={encoded_keyword}"
                print(f"  [{self.source_name} | {page_num}페이지] 탐색 중... ", end="")

                try:
                    response = client.get(target_path)
                    
                    if response.status_code != 200:
                        print(f"접속 실패(상태 코드: {response.status_code})로 중단합니다.")
                        break
                except Exception as e:
                    print(f"요청 중 에러 발생: {e}")
                    break

                # 3. 받아온 응답 텍스트를 Shift-JIS로 명시적 디코딩
                response.encoding = "shift_jis"
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 기존 Selector 탐색 로직
                articles = soup.select("#content-main > article > div.block-title-list > article")
                
                if not articles:
                    print("  -> 더 이상 기사가 없습니다. 수집을 종료합니다.")
                    break

                added_count = 0
                for article in articles:
                    # 링크 추출
                    link_tag = article.select_one("a")
                    if not link_tag:
                        continue
                    
                    href = link_tag.get("href")
                    if not href:
                        continue

                    full_url = f"https://www.oricon.co.jp{href}" if href.startswith("/") else href
                    
                    # 날짜 추출 (font 태그 등은 제외하고 안전하게 time 태그 내부 텍스트 추출)
                    time_tag = article.select_one("time")
                    date_str = time_tag.text if time_tag else ""
                    pub_date = self._parse_date(date_str)

                    # 날짜 조건 필터링 및 DB 중복 확인
                    if pub_date and self.start_date <= pub_date <= self.end_date:
                        existing = self.db.query(News).filter(News.url == full_url).first()
                        if not existing:
                            new_article = News(
                                source=self.source_name,
                                keyword=self.keyword,
                                url=full_url,
                                published_date=pub_date
                            )
                            self.db.add(new_article)
                            added_count += 1
                
                self.db.commit()
                print(f"-> {added_count}개 기사 저장 완료.")
                
                # 기존 eiga.py와 동일하게 새로 추가된 기사가 0개면 루프 탈출
                if added_count == 0:
                    print("  -> 수집할 새 기사가 없으므로 검색을 중단합니다.")
                    break
                
                page_num += 1
                time.sleep(1.5) # 서버 부하 방지를 위한 딜레이