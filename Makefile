.PHONY: install backend frontend dev

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting backend on :8000 and frontend on :5173 ..."
	@(cd backend && uvicorn app.main:app --reload --port 8000 &) && \
	 (cd frontend && npm run dev)
