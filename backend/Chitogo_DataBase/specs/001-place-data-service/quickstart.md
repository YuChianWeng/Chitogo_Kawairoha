# Quickstart: Place Data Service

**Branch**: `001-place-data-service`
**Database**: `postgresql://chitogo_user:kawairoha@localhost:5432/chitogo`

---

## Prerequisites

- Python 3.11+
- PostgreSQL 12 running locally with `chitogo` database and `chitogo_user` credentials

---

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Create .env to override DATABASE_URL
echo "DATABASE_URL=postgresql://chitogo_user:kawairoha@localhost:5432/chitogo" > .env
```

---

## Run the service

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Tables are created automatically on startup via `Base.metadata.create_all()`.

---

## Seed sample data

```bash
python scripts/seed.py
```

Expected output:
```
[seed] Connecting to database...
[seed] Tables verified.
[seed] Inserted place: 華山1914文化創意產業園區 (id=1)
[seed] Appended raw source row for google_place_id=ChIJH8B5JxapQjQR3KX8A2Q9V4o (total_raw_rows=1)
[seed] Normalized place verification: name=華山1914文化創意產業園區, district=中正區, place_rows=1
[seed] Done.
```

If already seeded:
```
[seed] Place already exists: 華山1914文化創意產業園區 (id=1)
[seed] Appended raw source row for google_place_id=ChIJH8B5JxapQjQR3KX8A2Q9V4o (total_raw_rows=2)
[seed] Normalized place verification: name=華山1914文化創意產業園區, district=中正區, place_rows=1
[seed] Done.
```

---

## Verify endpoints

```bash
# DB health check
curl http://localhost:8000/api/v1/health/db

# List all places
curl http://localhost:8000/api/v1/places

# Filter by district
curl "http://localhost:8000/api/v1/places?district=中正區"

# Filter by type and min rating
curl "http://localhost:8000/api/v1/places?primary_type=tourist_attraction&min_rating=4.0"

# Get place detail
curl http://localhost:8000/api/v1/places/1

# Import a place via HTTP
curl -X POST http://localhost:8000/api/v1/places/import/google \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "id": "ChIJHuashan1914TaipeiNEW01",
      "displayName": { "text": "華山1914文化創意產業園區 測試匯入" },
      "primaryType": "tourist_attraction",
      "types": ["tourist_attraction", "point_of_interest"],
      "formattedAddress": "10058台灣台北市中正區八德路一段1號",
      "addressComponents": [
        { "longText": "中正區", "shortText": "中正區", "types": ["sublocality", "political"] }
      ],
      "location": { "latitude": 25.0441, "longitude": 121.5292 },
      "rating": 4.5,
      "userRatingCount": 12001,
      "businessStatus": "OPERATIONAL",
      "googleMapsUri": "https://maps.google.com/?cid=4342178518828401117"
    }
  }'
```

---

## Verification checklist

- [ ] `GET /api/v1/health/db` returns `{"status": "ok", "database": "connected"}`
- [ ] `python scripts/seed.py` completes without error
- [ ] `GET /api/v1/places` returns at least one place record
- [ ] `GET /api/v1/places/1` returns full place detail
- [ ] `POST /api/v1/places/import/google` with a new payload returns `"action": "created"`
- [ ] Re-submitting the same `google_place_id` returns `"action": "updated"` (no duplicate)
- [ ] `GET /api/v1/places?district=中正區` returns the seeded 華山1914文化創意產業園區 record

---

## Interactive API docs

```
http://localhost:8000/docs
```
