import re
import time
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from src.models import News
from src.scrapers.base import BaseScraper

class EigaScraper(BaseScraper):
    def __init__(self, db, keyword, start_date, end_date):
        super().__init__(db, keyword, start_date, end_date)
        self.source_name = "eiga"
        self.base_url = "https://eiga.com"

    def _parse_date(self, url: str):
        match = re.search(r"/news/(\d{8})/", url)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        return None

    def scrape(self):
        page_num = 1
        print(f"\n▶ [{self.source_name}] '{self.keyword}' 뉴스 수집 시작...")

        with httpx.Client(base_url=self.base_url) as client:
            while True:
                target_path = f"/search/{self.keyword}/news/{page_num}/"
                print(f"  [{self.source_name} | {page_num}페이지] 탐색 중... ", end="")

                response = client.get(target_path)
                if response.status_code != 200:
                    print("접속 실패로 중단합니다.")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                news_section = soup.find(id="rslt-news")
                
                # 섹션이 없으면 빈 리스트 반환
                links = news_section.select("div p.link > a") if news_section else []

                added_count = 0
                for link in links:
                    href = link.get('href')
                    if not href:
                        continue

                    full_url = f"https://eiga.com{href}" if href.startswith("/") else href
                    pub_date = self._parse_date(full_url)

                    # 날짜 조건 필터링 및 중복 확인
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
                
                # [심플한 종료 조건] 새로 추가된 기사가 0개면 루프 탈출
                if added_count == 0:
                    print("  -> 수집할 새 기사가 없으므로 검색을 중단합니다.")
                    break
                
                page_num += 1
                time.sleep(1.5)
