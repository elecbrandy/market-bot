import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from src.database import init_db, SessionLocal
from src.models import News
from crawl4ai import AsyncWebCrawler, BrowserConfig
from sqlalchemy.dialects.postgresql import insert
from src.utils.logger import get_logger, log_progress
from src.scrapers.eiga import EigaScraper
# from src.scrapers.prtimes import PrtimesScraper


async def main():
    # Load Keywords 
    raw_keywords = os.getenv("SEARCH_KEYWORDS", "怪獣8号")
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

    # Set Date Range
    start_date = datetime.strptime(os.getenv("START_DATE", "20200101"), "%Y%m%d").date()
    end_date = datetime.strptime(os.getenv("END_DATE", "20991231"), "%Y%m%d").date()

    # Set max items per keyword (optional)
    max_items = int(os.getenv("MAX_ITEMS_PER_KEYWORD", "0"))  # 0 means no limit

    init_db()
    db = SessionLocal()
    logger = get_logger("main")

    scraper_classes = [
        EigaScraper,
        # PrtimesScraper,
    ]

    logger.info(f"Scraping started: {len(keywords)} keywords, {len(scraper_classes)} sources")
    browser_config = BrowserConfig(headless=True, verbose=False)

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            logger.info("Loading existing URLs from database...")
            seen_records = db.query(News.url).all()
            global_seen_urls = {record[0] for record in seen_records}

            total_tasks = len(keywords) * len(scraper_classes)
            task_count = 0
            for keyword in keywords:
                logger.info(f"Processing keyword: {keyword}")
                for ScraperClass in scraper_classes:
                    # If the URL has already been seen (from any keyword), the scraper will skip it.
                    scraper = ScraperClass(crawler, keyword, start_date, end_date, global_seen_urls, max_items)
                    
                    added_count = 0
                    async for news_data in scraper.scrape():
                        stmt = insert(News).values(
                            source=news_data["source"],
                            keyword=news_data["keyword"],
                            url=news_data["url"],
                            title=news_data["title"],
                            content=news_data["content"],
                            published_date=news_data["published_date"]
                        )
                        
                        # Ignore conflicts based on the 'url' column
                        stmt = stmt.on_conflict_do_nothing(index_elements=['url'])
                        
                        db.execute(stmt)
                        added_count += 1
                        
                        db.commit() 
                        logger.info(f"Saved: {news_data['title'][:30]}...")
                    logger.info(f"Finished {scraper.source_name} for '{keyword}'. Added: {added_count} items.")
                    task_count += 1
                    log_progress(logger, task_count, total_tasks, prefix="Overall Progress:")

    except Exception as e:
        logger.error(f"An error occurred while scraping: {e}")
        db.rollback()
    finally:
        db.close()
        logger.info("Scraping completed.")

if __name__ == "__main__":
    asyncio.run(main())