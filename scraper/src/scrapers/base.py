from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from datetime import date

class BaseScraper(ABC):
    def __init__(self, db: Session, keyword: str, start_date: date, end_date: date):
        self.db = db
        self.keyword = keyword
        self.start_date = start_date
        self.end_date = end_date
        self.source_name = "unknown" # 각 클래스에서 자신의 소스 이름을 정의

    @abstractmethod
    def scrape(self):
        """이 메서드 안에 각 사이트별 크롤링 로직을 할 것."""
        pass