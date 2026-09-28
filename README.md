# Road Health AI — Backend

FastAPI backend for the Road Health AI platform: citizen road-damage reporting,
AI-assisted assessment, geographic authority assignment, repair tracking,
verification, and automatic deadline escalation.

Built to `Road_Health_AI_Backend_Team_Specification.docx`: MVC + Service
architecture, PostgreSQL + PostGIS, SQLAlchemy, Pydantic, JWT auth,
local filesystem image storage, APScheduler for escalation.

## Stack

Python 3.11+ · FastAPI · Uvicorn · SQLAlchemy 2.x · Alembic · PostgreSQL +
PostGIS · Pydantic v2 / pydantic-settings · PyJWT · Argon2/bcrypt (passlib) ·
APScheduler · python-multipart · httpx

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL, JWT_SECRET_KEY, ROBOFLOW_API_KEY, etc.
```

Requires a PostgreSQL database with the PostGIS extension available
(the first migration runs `CREATE EXTENSION IF NOT EXISTS postgis`).

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`  
Health check: `GET /health`

## Project layout

```
app/
├── main.py              FastAPI app, lifespan (scheduler), router mounting
├── config.py             Pydantic Settings — all env-dependent config
├── database.py           Engine/session/Base
├── dependencies.py       JWT auth + role-based dependencies
├── error_handlers.py     Consistent JSON error responses
├── models/               SQLAlchemy ORM entities + enums/status-transition map
├── schemas/               Pydantic request/response contracts
├── controllers/          Coordinate validated requests -> services
├── routes/                Thin FastAPI routers
├── services/              Business rules (auth, report, AI, location/PostGIS,
│                          image, verification, escalation, authority)
├── scheduler/             APScheduler wiring (escalation_scheduler.py)
├── utils/                 jwt.py, security.py, file_utils.py
└── uploads/reports/       Local image storage (gitignored, kept via .gitkeep)
migrations/                Alembic — see 0001_initial.py for the base schema
tests/                     pytest suite — no real API key needed
```

## Architecture

```
Client → FastAPI Route → Controller → Service Layer → SQLAlchemy Model → PostgreSQL + PostGIS
```

Routes stay thin, controllers coordinate, services hold all business rules,
models are pure data. All spatial logic (nearby-report/duplicate detection,
zone-containment, bounding-box queries) is isolated in `location_service.py`.

## Report lifecycle

```
submitted → under_review → assigned → accepted → in_progress
          → repair_completed → verification → resolved

submitted → rejected
repair_completed → verification → rejected_for_rework → in_progress
(any eligible active status) → escalated
```

Transitions are validated against an explicit map
(`app/models/enums.py::ALLOWED_STATUS_TRANSITIONS`) — clients can never set
an arbitrary status string.

## AI service — Roboflow integration

`app/services/ai_service.py` is the **sole integration boundary** for the
road-damage AI model.  Report controllers and services only ever call
`assess_image()` — they never import httpx or touch the Roboflow API directly.

### How it works

```
POST /reports  (image + GPS)
  └─ report_controller.py
       └─ report_service.create_report()
            └─ ai_service.assess_image(image_path)
                 └─ _RoboflowBackend.predict()          ← if ROBOFLOW_API_KEY is set
                      POST https://detect.roboflow.com/rdd-india/9?api_key=...
                      image sent as base64 in request body
                      response: list of {class, confidence, x, y, width, height}
                 └─ _StubBackend.predict()              ← if key is absent
                      returns null fields, model_version="dev-stub-0.1"
            └─ AIResult → AIAssessment row + Report fields
```

### Roboflow model classes (rdd-india/9)

| Class | Stored damage_type    |
|-------|-----------------------|
| D00   | Longitudinal Crack    |
| D20   | Transverse Crack      |
| D40   | Alligator Crack       |
| D44   | Pothole               |

### Severity mapping (confidence-based)

| Confidence range | estimated_severity |
|------------------|--------------------|
| ≥ 0.80           | critical           |
| ≥ 0.60           | high               |
| ≥ 0.40           | medium             |
| < 0.40           | low                |

When multiple detections are present the **highest-confidence** prediction is
used as the primary `damage_type` / `confidence` / `estimated_severity`.
All bounding boxes are preserved in `AIAssessment.bounding_boxes` (JSONB).

### Required environment variables

| Variable           | Required? | Default                        | Description                                |
|--------------------|-----------|--------------------------------|--------------------------------------------|
| `ROBOFLOW_API_KEY` | Yes*      | _(empty)_                      | Roboflow API key — never commit this value |
| `ROBOFLOW_MODEL_ID`| No        | `rdd-india/9`                  | Roboflow model version                     |
| `ROBOFLOW_API_URL` | No        | `https://detect.roboflow.com`  | Roboflow inference endpoint                |

\* Without an API key the backend runs with the safe **development stub** that
returns null AI fields.  All other endpoints remain fully functional.

### Getting a Roboflow API key

1. Sign up at <https://app.roboflow.com/>
2. Go to **Account → API Keys**
3. Copy the key into your `.env` as `ROBOFLOW_API_KEY=<key>`

### Error handling

If the Roboflow API is unreachable, times out (15 s), returns a non-200 status,
or returns an unparseable body:

- `AIServiceUnavailableError` is raised inside `ai_service`.
- `report_service.create_report()` catches it, logs a warning, and stores
  a null `AIAssessment` (`model_version="dev-stub-0.1-error"`).
- The report is **still saved** and the API returns 201.  The citizen is
  never blocked by an AI outage.

The API key is **never** logged, returned in responses, or included in
error messages.

### Testing AI inference (no real key needed)

```bash
# Unit tests — all mocked, no network calls
pytest tests/test_ai_service.py -v

# Manual end-to-end (real key)
curl -X POST http://localhost:8000/api/v1/reports \
  -H "Authorization: Bearer <jwt>" \
  -F "latitude=28.6139" \
  -F "longitude=77.2090" \
  -F "image=@/path/to/road.jpg"
# Response includes ai_assessments with damage_type, confidence, bounding_boxes, severity
```

### Disabling AI inference (development)

Leave `ROBOFLOW_API_KEY` blank in `.env`.  All report creation succeeds;
`AIAssessment.model_version` will be `"dev-stub-0.1"` and all AI fields null.

## Escalation

`app/scheduler/escalation_scheduler.py` starts an APScheduler background job
on FastAPI startup (interval from `ESCALATION_INTERVAL_MINUTES`) that calls
`escalation_service.check_overdue_reports()`. The scheduler holds no business
logic — it's a clock. Escalation is idempotent (one escalation per level),
never fires on resolved/rejected reports, and every event is recorded in the
`escalations` table with the report's `current_escalation_level` kept in
sync.

## Known placeholders — confirm before production

- **SLA hours per priority** (`.env` `SLA_HOURS_*`): example values only,
  per the spec's explicit instruction not to hard-code final durations.
- **Severity → priority mapping** (`report_service._SEVERITY_TO_PRIORITY`):
  works once the AI model returns real severities; adjust as needed.
- **Confidence → severity thresholds** (`ai_service._CONFIDENCE_SEVERITY`):
  calibrate against real model output distributions once you have ground-truth
  data.
- **Escalation hierarchy data**: seed `authorities.parent_authority_id`
  manually or via an admin endpoint — there's no default hierarchy.

## Definition-of-done coverage

Signup/login/JWT, citizen report submission (image + GPS), local image
storage, AI assessment attachment (Roboflow `rdd-india/9`), zone/authority
assignment, status lifecycle + audit trail, repair evidence + verification
(pass → resolved, fail → rework), deadline calculation, scheduled escalation
with history, and dashboard summary/map/overdue/escalated/analytics endpoints
are all implemented per the spec's Definition of Done (§28).
