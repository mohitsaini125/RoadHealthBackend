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
APScheduler · python-multipart · (optional) Ultralytics YOLOv8

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL, JWT_SECRET_KEY, etc.
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

## AI service

`app/services/ai_service.py` is the sole integration boundary for the damage
model. With `AI_MODEL_PATH` unset, it uses a clearly-labeled development
stub (`model_version="dev-stub-0.1"`) so the rest of the backend is testable
without a trained model. Set `AI_MODEL_PATH` and install `ultralytics` to use
a real YOLOv8 model — the raw-output-to-severity mapping in
`_RealModelBackend.predict` is a placeholder pending real labels.

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
- **AI raw-output mapping** (`ai_service._RealModelBackend.predict`): wire up
  once real class labels/severity rules are defined.
- **Escalation hierarchy data**: seed `authorities.parent_authority_id`
  manually or via an admin endpoint — there's no default hierarchy.

## Definition-of-done coverage

Signup/login/JWT, citizen report submission (image + GPS), local image
storage, AI assessment attachment, zone/authority assignment, status
lifecycle + audit trail, repair evidence + verification (pass → resolved,
fail → rework), deadline calculation, scheduled escalation with history,
and dashboard summary/map/overdue/escalated/analytics endpoints are all
implemented per the spec's Definition of Done (§28).
