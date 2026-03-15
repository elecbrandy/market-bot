# .env 파일 로드
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

.PHONY: up down build rebuild restart logs logs-backend logs-frontend logs-db logs-vectordb ps up-db scrape test-scraper test-scraper-local embed sh-backend restart-backend rebuild-backend restart-frontend rebuild-frontend flush-db flush-vector flush-all clean fclean

# 1. 서비스 기본 제어
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

rebuild:
	docker compose down && docker compose build && docker compose up -d

restart:
	docker compose restart

ps:
	docker compose ps


# 2. 로그 확인
logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

logs-db:
	docker compose logs -f db

logs-vectordb:
	docker compose logs -f vector_db


# 3. 개발 및 테스트 (단일 컨테이너 제어)
sh-backend:
	docker compose exec backend /bin/bash

restart-backend:
	docker compose restart backend

rebuild-backend:
	docker compose up -d --build backend

restart-frontend:
	docker compose restart frontend

rebuild-frontend:
	docker compose up -d --build frontend


# 4. 데이터 수집 및 임베딩 로직
up-db:
	docker compose up -d db

scrape:
	docker compose --profile tools run --rm scraper

test-scraper:
	docker compose up -d db
	@sleep 3
	docker compose --profile tools run --rm scraper

test-scraper-local:
	docker compose up -d db
	@sleep 3
	cd scraper && DB_CONTAINER=127.0.0.1 venv/bin/python3.11 main.py

embed:
	curl -X POST http://localhost:$(BACKEND_PORT)/embed/run


# 5. 데이터 초기화
flush-db:
	@echo "PostgreSQL 데이터를 삭제하시겠습니까? [y/N] " && read ans && [ $${ans:-N} = y ]
	rm -rf ./volumes/postgres/*
	docker compose exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < flush_db.sql

flush-vector:
	@echo "ChromaDB 데이터를 삭제하시겠습니까? [y/N] " && read ans && [ $${ans:-N} = y ]
	docker compose stop vector_db
	rm -rf ./volumes/chroma/*
	docker compose start vector_db

flush-all: flush-db flush-vector


# 6. 시스템 정리 (Clean up)
clean:
	docker compose down --remove-orphans

fclean:
	docker compose down -v --remove-orphans
	docker image prune -af
	docker builder prune -af
