.PHONY: up down logs api-test ui-build package

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api recovery-worker console ticket-agent-demo

api-test:
	cd services/api && python -m pytest tests

ui-build:
	npm --workspace @tracememory/console run build

package:
	cd .. && zip -qr tracememory-hackathon-vultr.zip tracememory-hackathon-vultr -x "*/node_modules/*" "*/__pycache__/*" "*.pyc" "*/.pytest_cache/*"
