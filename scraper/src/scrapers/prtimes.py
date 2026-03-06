import time
import random
import re
from datetime import datetime, timedelta, date

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

from src.models import News
from src.scrapers.base import BaseScraper

# Selectors
SEL_ARTICLES = (
    "#__next > div > div > main > div > div > section"
    " > div.release-card-list_container__RfZzG > article"
)
SEL_LINK     = "a"
SEL_DATE     = "time"
SEL_MORE_BTN = (
    "#__next > div > div > main > div > div > section"
    " > div.release-more-button_more__WeIJc > button"
)

def _parse_date(date_text: str):
    """ 다양한 형태의 날짜 텍스트를 파싱하여 date 객체로 반환 """
    if not date_text:
        return None
        
    # 눈에 보이지 않는 공백이나 줄바꿈을 일반 공백으로 치환
    date_text = re.sub(r'\s+', ' ', date_text.strip())
    
    # 1. '本日' (오늘) 처리
    if "本日" in date_text:
        return date.today()
        
    # 2. '昨日' (어제) 처리
    if "昨日" in date_text:
        return date.today() - timedelta(days=1)
        
    # 3. YYYY年M月D日 정규식 추출 (공백이 있어도 무시하도록 \s* 추가)
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", date_text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        
    # 4. 상대 시간 처리 (X時間前, X分前, X日前)
    match_hour = re.search(r"(\d+)\s*時間前", date_text)
    if match_hour:
        return (datetime.now() - timedelta(hours=int(match_hour.group(1)))).date()
        
    match_min = re.search(r"(\d+)\s*分前", date_text)
    if match_min:
        return (datetime.now() - timedelta(minutes=int(match_min.group(1)))).date()
        
    match_day = re.search(r"(\d+)\s*日前", date_text)
    if match_day:
        return (datetime.now() - timedelta(days=int(match_day.group(1)))).date()
        
    return None

class PrtimesScraper(BaseScraper):
    def __init__(self, db, keyword, start_date, end_date):
        super().__init__(db, keyword, start_date, end_date)
        self.source_name = "prtimes"
        self.search_url = (
            "https://prtimes.jp/main/action.php"
            f"?run=html&page=searchkey&search_word={keyword}"
        )

    def scrape(self):
        print(f"\n▶ [{self.source_name}] '{self.keyword}' 수집 시작...")

        added_total = 0
        processed_urls = set()  # 한 번 파싱한 기사를 다시 보지 않도록 기억
        click_count = 0
        MAX_CLICKS = 20
        MAX_ARTICLES = 300
        stop_scraping = False

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            page = context.new_page()

            try:
                page.goto(self.search_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)
            except PlaywrightTimeoutError:
                print(f"  ⚠ 페이지 로드 timeout: {self.search_url}")
                browser.close()
                return

            # --- [핵심] 페이지 청크 단위로 파싱 -> 저장 -> 더보기 누르는 단일 루프 ---
            while click_count <= MAX_CLICKS and not stop_scraping:
                articles = page.query_selector_all(SEL_ARTICLES)
                
                if len(processed_urls) >= MAX_ARTICLES:
                    print(f"  🛑 설정한 최대 기사 개수({MAX_ARTICLES}개) 도달 → 수집 중단")
                    break

                # 현재 보이는 화면의 기사들을 파싱
                for article in articles:
                    link_el = article.query_selector(SEL_LINK)
                    date_el = article.query_selector(SEL_DATE)

                    if not link_el or not date_el:
                        continue

                    url = link_el.get_attribute("href") or ""
                    if url.startswith("/"):
                        url = "https://prtimes.jp" + url

                    # 이미 이번 루프나 이전 루프에서 파싱해서 저장한 URL이면 가볍게 패스
                    if url in processed_urls:
                        continue
                    
                    processed_urls.add(url) # 파싱 완료 목록에 추가

                    raw_text = date_el.inner_text()
                    pub_date = _parse_date(raw_text)

                    if not pub_date:
                        print(f"    ⚠ 날짜 파싱 실패 (원본텍스트: '{raw_text}') -> 스킵")
                        continue

                    # 🛑 [중단 조건 감지] 만약 범위 밖(과거) 기사를 발견했다면?
                    if pub_date < self.start_date:
                        print(f"  🛑 수집 시작일({self.start_date}) 이전 기사 발견({pub_date}) → 상위 루프 스탑!")
                        stop_scraping = True
                        break # 현재 for문을 즉시 탈출 (이후 더보기 안 누름)

                    # 미래 날짜거나 범위 안이면 DB 추가 (end_date 초과 시엔 단순 스킵)
                    if pub_date <= self.end_date:
                        exists = self.db.query(News).filter(News.url == url).first()
                        if not exists:
                            self.db.add(News(
                                source=self.source_name,
                                keyword=self.keyword,
                                url=url,
                                published_date=pub_date,
                            ))
                            added_total += 1

                # 한 턴(현재 띄워진 청크)이 끝날 때마다 DB 커밋
                self.db.commit()

                # 범위 밖 과거 기사 발견으로 중단 플래그가 떴다면, 더보기 누르지 않고 완전히 종료
                if stop_scraping:
                    break

                # 더보기 버튼 소진 확인
                more_btn = page.query_selector(SEL_MORE_BTN)
                if not more_btn or not more_btn.is_visible():
                    print(f"  🛑 더보기 버튼 없음 (전체 결과 로드 완료) → 수집 중단")
                    break

                # 아직 목표 달성 안 했고 과거 기사도 안 나왔으니 다음 페이지(더보기) 전진
                try:
                    current_count = len(articles)
                    more_btn.scroll_into_view_if_needed()
                    time.sleep(random.uniform(0.5, 1.5))
                    more_btn.click()
                    
                    page.wait_for_function(
                        f"document.querySelectorAll('{SEL_ARTICLES}').length > {current_count}",
                        timeout=15000
                    )
                    click_count += 1
                    print(f"  🔄 {click_count}번째 청크 로딩 (더보기 클릭)...")
                    time.sleep(random.uniform(1.0, 2.5))
                except PlaywrightTimeoutError:
                    print(f"  ⚠ 더보기 클릭 후 로딩 지연(Timeout) → 현재까지만 파싱 진행")
                    break

            browser.close()

        print(f"  ✅ [{self.source_name}] '{self.keyword}' → {added_total}개 저장 완료")
