from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from crawl4ai import AsyncWebCrawler

# asyncio 임포트
import asyncio

from src.models import News
from src.utils.config import ScraperConfig
from src.utils.logger import get_logger, get_console

logger  = get_logger("runner")
console = get_console()

async def load_seen_urls(db: Session) -> set[str]:
    """
    DB에 이미 저장된 뉴스 URL을 모두 불러와서 집합으로 반환합니다.
    """
    return await asyncio.to_thread(lambda: {row[0] for row in db.query(News.url).all()})

async def save_batch(db: Session, batch: list[dict]) -> None:
    if not batch:
        return 0
    
    def _insert():
        stmt = insert(News).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
        result = db.execute(stmt)
        db.commit()
        return result.rowcount

    # 비동기 흐름을 막지 않기 위해 별도 스레드에서 DB 쓰기
    return await asyncio.to_thread(_insert)

async def run_scraper(
    crawler:       AsyncWebCrawler,
    db:            Session,
    ScraperClass,
    keyword:       str,
    config:        ScraperConfig,
    seen_urls:     set[str],
) -> int:
    """
    단일 스크래퍼에 대해 주어진 키워드로 크롤링을 실행하고, 결과를 DB에 저장합니다.
    """

    # Scraper 인스턴스 생성
    scraper = ScraperClass(crawler, keyword, config.start_date, config.end_date, seen_urls, config.max_items)
    added_count = 0
    batch = []
    batch_size = 50

    # Scraper 실행 및 DB 저장
    async for news_data in scraper.scrape():
        batch.append({
            "source":         news_data["source"],
            "keyword":        news_data["keyword"],
            "url":            news_data["url"],
            "title":          news_data["title"],
            "content":        news_data["content"],
            "published_date": news_data["published_date"],
        })
        
        logger.info(f"[green]Scraped[/green] [{news_data['published_date']}] {news_data['title'][:45]}")

        if len(batch) >= batch_size:
            saved = await save_batch(db, batch)
            added_count += saved
            batch.clear()

    # 남은 데이터 처리
    if batch:
        saved = await save_batch(db, batch)
        added_count += saved

    logger.info(
        f"[bold]{ScraperClass.__name__}[/bold] / [cyan]{keyword}[/cyan] "
        f"— [bold green]{added_count}[/bold green] items saved to DB."
    )
    console.print()
    return added_count


async def run_all(
    crawler:         AsyncWebCrawler,
    db:              Session,
    scraper_classes: list,
    config:          ScraperConfig,
) -> None:
    """
    모든 스크래퍼에 대해 키워드 조합을 순차적으로 실행합니다.
    """
    seen_urls = await load_seen_urls(db)
    logger.info(f"[bold]{len(seen_urls)}[/bold] URLs already in DB — will skip duplicates.")

    # 각 키워드와 스크래퍼 조합에 대해 순차적으로 실행 (Task 리스트에 담는 대신 바로 await 호출)
    for keyword in config.keywords:
        for ScraperClass in scraper_classes:
            await run_scraper(crawler, db, ScraperClass, keyword, config, seen_urls)