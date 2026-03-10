SITE_CONFIG = {
    "eiga": {
        "base_url": "https://eiga.com",
        "search_path": "/search/{keyword}/news/{page}/",
        "selectors": {
            "news_container": "#rslt-news",
            "article_link": "div p.link > a",
            "article_body": "div.news-detail, div.txt-block",
        },
        "regex": {
            "date_extract": r"/news/(\d{8})/"
        }
    },
    "prtimes": {
        "base_url": "https://prtimes.jp",
        "search_path": "/main/html/searchform/keyword/{keyword}/page/{page}",
        "selectors": {
            "news_container": "div.list-article",
            "article_link": "h3.title-item > a",
        },
        "regex": {
            "date_extract": r"(\d{4}-\d{2}-\d{2})"
        }
    },
}