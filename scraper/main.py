import asyncio
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / '.env')

from crawl4ai import AsyncWebCrawler, BrowserConfig
from rich.rule import Rule
from rich.table import Table

from src.utils.config import load_config
from src.database import init_db, SessionLocal
from src.runner import run_all
from src.utils.logger import get_console
from src.scrapers.base import BaseScraper

console = get_console()

# Scraper 클래스 목록
SCRAPER_CLASSES = BaseScraper.registry

async def main():
    config = load_config()

    # Summary 출력
    console.print(Rule("[bold green] Scraper Starting [/bold green]"))
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="bold cyan")
    summary.add_column(style="white")
    summary.add_row("Keywords",   ", ".join(config.keywords))
    summary.add_row("Sources",    ", ".join(cls.__name__ for cls in SCRAPER_CLASSES))
    summary.add_row("Date Range", f"{config.start_date}  →  {config.end_date}")
    summary.add_row("Max Items",  str(config.max_items) if config.max_items else "unlimited")
    console.print(summary)
    console.print()

    # DB 연결
    init_db()
    db = SessionLocal()

    # Scraping 실행
    try:
        async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
            await run_all(crawler, db, SCRAPER_CLASSES, config)
    except Exception as e:
        from src.utils.logger import get_logger
        get_logger("main").error(f"Scraping failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

    console.print(Rule("[bold green] Scraping Completed [/bold green]"))


if __name__ == "__main__":
    asyncio.run(main())