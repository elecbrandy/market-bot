import os
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ScraperConfig:
    keywords:   list[str]
    start_date: date
    end_date:   date
    max_items:  int


def load_config() -> ScraperConfig:
    keywords = [
        k.strip()
        for k in os.getenv("SEARCH_KEYWORDS", "怪獣8号").split(",")
        if k.strip()
    ]
    return ScraperConfig(
        keywords   = keywords,
        start_date = datetime.strptime(os.getenv("START_DATE", "20200101"), "%Y%m%d").date(),
        end_date   = datetime.strptime(os.getenv("END_DATE",   "20991231"), "%Y%m%d").date(),
        max_items  = int(os.getenv("MAX_ITEMS_PER_KEYWORD", "0")),
    )