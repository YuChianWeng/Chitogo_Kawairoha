import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import SessionLocal
from app.services.ingestion import ingest_google_place


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_place.py <payload.json>", file=sys.stderr)
        return 1

    payload_path = Path(sys.argv[1])
    if not payload_path.is_file():
        print(f"File not found: {payload_path}", file=sys.stderr)
        return 1

    with payload_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    db = SessionLocal()
    try:
        result = ingest_google_place(db, payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
