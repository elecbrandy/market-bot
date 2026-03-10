.PHONY: up down build rebuild restart logs logs-backend logs-frontend logs-db logs-vectordb ps scrape clean fclean

# 전체 서비스 시작 (scraper 제외)
up:
	docker compose up -d

# 전체 서비스 중지
down:
	docker compose down

# 전체 빌드
build:
	docker compose build

# 빌드 후 시작
rebuild:
	docker compose down && docker compose build && docker compose up -d

# 재시작
restart:
	docker compose restart

# 로그 확인 (전체)
logs:
	docker compose logs -f

# 개별 로그
logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

logs-db:
	docker compose logs -f db

logs-vectordb:
	docker compose logs -f vector_db

# 컨테이너 상태 확인
ps:
	docker compose ps

# 스크래퍼 실행 (profiles: tools)
scrape:
	docker compose --profile tools run --rm scraper

# 컨테이너만 삭제
clean:
	docker compose down --remove-orphans

# 컨테이너 + 볼륨 + 이미지 + 빌드캐시 전부 삭제 (주의!)
fclean:
	docker compose down -v --remove-orphans
	docker image prune -af
	docker builder prune -af
	rm -rf ./volumes/*

# DB만 백그라운드로 단독 실행
up-db:
	docker compose up -d db

# DB 실행 후 스크래퍼 원큐에 테스트하기
test-scraper:
	docker compose up -d db
	@echo "DB가 준비될 때까지 3초 대기합니다..."
	@sleep 3
	docker compose --profile tools run --rm scraper

# DB만 띄운 상태에서 스크래퍼 로컬 실행
test-scraper-local:
	docker compose up -d db
	@echo "DB가 준비될 때까지 3초 대기..."
	@sleep 3
	cd scraper && DB_CONTAINER=127.0.0.1 python3.11 main.py
