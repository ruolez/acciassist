# AcciAssist

Personal-injury intake & case platform — starting with **auto-accident** cases.
Patients answer a guided questionnaire (no login), see a transparent summary with an
estimated settlement range, and can leave their details to work with the company.
Admins configure the entire experience: injury types, questionnaires, and summary
templates.

This is **Slice 1** (the vertical spine): infrastructure + admin builder + patient
intake. See `~/.claude/plans/i-want-to-create-snazzy-rocket.md` for scope and roadmap.

## Stack

- **Frontend:** React + Vite + TypeScript, React Router, TanStack Query, react-hook-form +
  zod, dnd-kit. Plain CSS with design tokens (`src/styles/tokens.css`).
- **Backend:** FastAPI (async), SQLAlchemy 2.0 + asyncpg, Alembic, Pydantic v2, JWT cookie
  auth (argon2 hashing).
- **Database:** PostgreSQL 16.
- **Infra:** Docker Compose — nginx proxy + frontend + backend + postgres.

## Architecture

```
HOST → nginx proxy → /api/* → backend (FastAPI)
                   → /     → frontend (Vite dev server / built SPA)
                              backend → postgres
```

## Ports (chosen from a free-port scan; edit `.env` to change)

| Service  | Host port |
| -------- | --------- |
| proxy    | 8082      |
| backend  | 8000      |
| postgres | 5432      |

App: <http://localhost:8082>  ·  Admin: <http://localhost:8082/admin>

## Quick start

```bash
cp .env.example .env                 # adjust ports/secrets if needed
docker compose up -d --build         # start all four containers

# First time only: create schema and seed demo data
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed
```

Default seeded admin: `admin@acciassist.com` / `changeme123` (from `.env`).
The seed also creates a published **Auto Accident** questionnaire (11 questions).

## Tests & checks

```bash
# Backend (unit + integration against a throwaway test database)
docker compose run --rm backend pytest -q
docker compose run --rm backend ruff check .

# Frontend
docker compose run --rm --no-deps frontend npm run typecheck
docker compose run --rm --no-deps frontend npm test
```

## Migrations

```bash
# After changing SQLAlchemy models:
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
docker compose run --rm backend alembic upgrade head
```

## Layout

- `backend/app/` — `models.py`, `schemas.py`, `api/` (routers), `services/` (pure logic),
  `security.py`, `deps.py`, `errors.py`, `seed.py`
- `frontend/src/features/intake/` — public patient flow (landing, full-bleed wizard, summary)
- `frontend/src/features/admin/` — admin (login, two-pane questionnaire builder, summary
  template, submissions, leads, admins)
- `nginx/nginx.conf` — reverse proxy (dev)

## Deferred to later slices

Patient accounts & dashboard · payout rules engine · admin theming · doctor/insurance/
attorney portals · Redis & horizontal scaling.
