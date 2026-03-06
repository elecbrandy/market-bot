import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from src.database import init_db, SessionLocal
from src.scrapers.eiga import EigaScraper
from src.scrapers.prtimes import PrtimesScraper
from src.scrapers.oricon import OriconScraper
from src.scrapers.natalie import NatalieScraper
# from src.scrapers.yahoo import YahooScraper  # 추후 추가될 사이트

def main():
    # 1. env load
    raw_keywords = os.getenv("SEARCH_KEYWORDS", "怪獣8号")
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

    start_date = datetime.strptime(os.getenv("START_DATE", "20200101"), "%Y%m%d").date()
    end_date = datetime.strptime(os.getenv("END_DATE", "20991231"), "%Y%m%d").date()

    # 2. DB 세션 생성
    init_db()
    db = SessionLocal()

    # 3. 사용할 스크래퍼 '클래스' 목록 정의
    scraper_classes = [
        NatalieScraper,
        # OriconScraper,
        # PrtimesScraper,
        # EigaScraper,
        # YahooScraper,
        # NatalieScraper,
    ]

    print(f"🚀 스크래핑 시작: 총 {len(keywords)}개 키워드, {len(scraper_classes)}개 사이트 대상")
    print(f"📅 수집 기간: {start_date} ~ {end_date}")

    # 4. M x N 중첩 루프 실행 (키워드 1개당 -> 모든 사이트 순회)
    try:
        for keyword in keywords:
            print(f"\n{'='*50}\n🎯 [Target Keyword]: {keyword}\n{'='*50}")
            
            for ScraperClass in scraper_classes:
                # 각 타겟 사이트별로 새로운 스크래퍼 인스턴스 생성 후 실행
                scraper = ScraperClass(db, keyword, start_date, end_date)
                scraper.scrape()
                
    except Exception as e:
        print(f"\n❌ 스크래핑 도중 에러가 발생했습니다: {e}")
    finally:
        db.close()
        print("\n✅ 모든 스크래핑 작업이 완료되었습니다.")

if __name__ == "__main__":
    main()
