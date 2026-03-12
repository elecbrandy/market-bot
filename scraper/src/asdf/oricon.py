async def scrape(self):
        """
        Oricon 검색 결과를 순회하며 기사 링크와 날짜를 수집하고, 각 기사를 크롤링합니다.
        Early Stop 및 무한 루프 방지 로직이 적용되어 있습니다.
        """
        page_num = 1
        yielded_count = 0
        sem = asyncio.Semaphore(5)  # 동시 요청 수 제한

        try:
            # 오리콘 서버는 검색 키워드를 Shift-JIS로 인코딩해야 인식
            encoded_keyword = urllib.parse.quote(self.keyword.encode('shift_jis', errors="replace"))
            self.logger.info(f"Searching with Shift-JIS encoded keyword: {self.keyword}")
        except Exception as e:
            self.logger.warning(f"Shift-JIS encoding failed, using UTF-8: {e}")
            encoded_keyword = urllib.parse.quote(self.keyword)

        # 본문 페이지 크롤링용 설정 (마크다운 제너레이터 없이 HTML만 가져오도록 설정)
        article_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

        # 💡 [무한루프 방지] 이전 페이지 URL 집합
        previous_page_urls = set()
        
        # 💡 [Early Stop] 연속 중복 카운터 및 제한 횟수 설정
        consecutive_seen_count = 0
        MAX_CONSECUTIVE_SEEN = 5  # 이미 수집한 기사가 연속 5번 나오면 스크랩 중단 (필요에 따라 조절하세요)

        while True:
            if self.max_items > 0 and yielded_count >= self.max_items:
                break

            search_path = self.config["search_path"].format(keyword=encoded_keyword, page=page_num)
            target_url  = f"{self.config['base_url']}{search_path}"

            list_run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            result = await self.crawler.arun(url=target_url, config=list_run_config)

            if not result.success:
                break

            soup = BeautifulSoup(result.html, "html.parser")
            list_container = soup.select_one(self.config["selectors"]["list_container"])

            if not list_container:
                break

            articles = list_container.select(self.config["selectors"]["article_item"])
            if not articles:
                break

            tasks = []
            reached_old_date = False
            reached_seen_limit = False  # Early Stop 달성 여부 플래그
            current_page_urls = set()   # 현재 페이지 URL 수집용

            for article in articles:
                link_tag = article.select_one(self.config["selectors"]["article_link"])
                if not link_tag:
                    continue

                href = link_tag.get("href")
                if not href:
                    continue

                full_url = f"{self.config['base_url']}{href}" if href.startswith("/") else href
                current_page_urls.add(full_url)

                # 날짜 추출
                time_tag = article.select_one("time")
                date_text = time_tag.get_text(strip=True) if time_tag else article.get_text(strip=True)

                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                if not date_match:
                    continue

                pub_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()

                if pub_date < self.start_date:
                    reached_old_date = True
                    break
                if pub_date > self.end_date:
                    continue

                # 💡 Early Stop 적용: 이미 본 기사인지 체크
                if full_url in self.seen_urls:
                    consecutive_seen_count += 1
                    if consecutive_seen_count >= MAX_CONSECUTIVE_SEEN:
                        self.logger.info(f"이미 수집한 기사가 연속 {MAX_CONSECUTIVE_SEEN}번 발견되어 조기 종료(Early Stop)합니다.")
                        reached_seen_limit = True
                        break
                    continue
                else:
                    # 새로운 기사를 발견하면 연속 카운터 초기화 (가끔 업데이트로 순서가 섞이는 것 방어)
                    consecutive_seen_count = 0

                title = link_tag.get("title") or link_tag.get_text(separator=" ", strip=True)
                title = title.replace(date_match.group(1), "").strip()

                if self.keyword not in title:
                    self.logger.debug(f"Skipping: keyword not in title — {title}")
                    continue

                tasks.append(self._fetch_article(full_url, pub_date, title, article_run_config, sem))

            # 💡 무한 루프 방지 적용: 이전 페이지와 목록이 완전히 같다면 마지막 페이지로 간주
            if current_page_urls and current_page_urls == previous_page_urls:
                self.logger.info("마지막 페이지에 도달했습니다 (이전 페이지와 동일). 수집을 종료합니다.")
                break
            
            # 다음 루프 비교를 위해 현재 페이지 URL 상태 업데이트
            previous_page_urls = current_page_urls

            # 수집된 기사 비동기 실행
            if tasks:
                results = await asyncio.gather(*tasks)
                for article_data in results:
                    if article_data and (self.max_items == 0 or yielded_count < self.max_items):
                        self.seen_urls.add(article_data["url"])
                        yielded_count += 1
                        yield article_data

            # 날짜 제한이거나 Early Stop 조건에 걸렸으면 루프 완전 탈출
            if reached_old_date or reached_seen_limit:
                break

            page_num += 1
            await asyncio.sleep(1)
