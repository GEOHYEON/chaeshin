.PHONY: install install-pip test test-unit lint demo clean help

help: ## 도움말
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 개발 의존성 포함 설치 (uv)
	uv sync --all-extras

install-pip: ## 개발 의존성 포함 설치 (pip)
	pip install -e ".[dev]"

test: ## 전체 테스트 실행
	pytest tests/ -v --tb=short

test-unit: ## 유닛 테스트만 실행
	pytest tests/ -v --tb=short -k "not e2e"

lint: ## 코드 검사
	python -m py_compile chaeshin/schema.py
	python -m py_compile chaeshin/graph_executor.py
	python -m py_compile chaeshin/case_store.py
	python -m py_compile chaeshin/planner.py
	@echo "✅ All files compile successfully"

demo: ## 김치찌개 요리사 데모 실행
	python -m examples.cooking.chef_agent

clean: ## 빌드 아티팩트 제거
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf *.egg-info dist build .pytest_cache
	rm -rf .eggs
	@echo "✅ Cleaned"
