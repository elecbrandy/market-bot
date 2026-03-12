from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any
from datetime import date
from crawl4ai import AsyncWebCrawler
from src.utils.logger import get_logger
from typing import Type
import os

os.environ["CRAWL4AI_VERBOSE"] = "false" 

SEM_NUM = 5                 # 동시 크롤링할 기사 수 (서버 부하 방지용)
MAX_CONSECUTIVE = 5    # 이미 수집한 기사가 연속 5번 나오면 스크랩 중단

class BaseScraper(ABC):
    """ 모든 스크래퍼가 상속해야 하는 기본 클래스 """
    
    registry: list[Type["BaseScraper"]] = []    # 모든 스크래퍼 클래스의 레지스트리

    def __init_subclass__(cls, **kwargs):
        """ 서브클래스가 정의될 때마다 자동으로 레지스트리에 등록 """
        super().__init_subclass__(**kwargs)

        if cls.__name__ != "BaseScraper":
            # BaseScraper를 제외한 모든 서브클래스를 registry에 등록
            BaseScraper.registry.append(cls)

    def __init__(self, crawler: AsyncWebCrawler, keyword: str, start_date: date, end_date: date, seen_urls: set[str], max_items: int = 0):
        self.crawler: AsyncWebCrawler = crawler                          # 크롤러 인스턴스 저장
        self.keyword: str = keyword                          # 검색 키워드 저장
        self.start_date: date = start_date                    # 크롤링할 기사들의 시작 날짜 저장
        self.end_date: date = end_date                        # 크롤링할 기사들의 종료 날짜 저장
        self.seen_urls: set[str] = seen_urls                      # 이미 수집한 기사 URL 집합 저장 (중복 방지용)
        self.max_items: int = max_items                      # 최대 수집 기사 수 저장 (0이면 무제한)
        self.source_name: str = "unknown"                    # 스크래퍼 이름 (서브클래스에서 설정)
        self.sem_num: int = SEM_NUM                          # 동시 크롤링할 기사 수 (서버 부하 방지용)
        self.max_consecutive_seen: int = MAX_CONSECUTIVE     # 이미 수집한 기사가 연속 5번 나오면 스크랩 중단
        self.logger: Any = get_logger(self.source_name)

    @abstractmethod
    async def scrape(self) -> AsyncGenerator[Dict[str, Any], None]:
        yield {}