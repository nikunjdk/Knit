# Knit

Lightweight meetup networking web app.

- **Organizers** create events → share QR → get AI digest
- **Attendees** join via QR → see relevance-sorted people → get AI icebreakers → mark who they met

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Flutter Web (Firebase Hosting) |
| Backend | FastAPI (Railway) |
| Database | Supabase Postgres + Auth |
| Auth | Google OAuth via Supabase |
| Cache | Upstash Redis |
| AI | Gemini 2.0 Flash + text-embedding-004 |

## Structure

```
backend/      FastAPI API (Python, Poetry)
frontend/     Flutter Web app
supabase/     Database migrations + seed
docs/         Planning artifacts (schema, API contracts, design system)
.github/      CI/CD workflows
```

## Local Development

### Backend

```bash
cd backend
poetry install
cp ../env.example .env.qa   # fill in values
uvicorn app.main:app --reload --env-file .env.qa
```

Health check: `curl http://localhost:8000/health`

### Frontend

```bash
cd frontend
flutter pub get
flutter run -d chrome
```

## Deployment

- **Backend:** Railway (`knit-api-qa` + `knit-api-prod`)
- **Frontend:** Firebase Hosting (`knit-qa` + `knit-prod`)
- **Database:** Supabase (`knit-qa` + `knit-prod`)

CI/CD runs automatically on push to `main`. See `.github/workflows/`.

## Docs

- `docs/knit_schema.sql` — database schema reference
- `docs/knit_api_contracts.md` — full API specification
- `docs/Design_system.md` — design tokens + UI rules
- `CLAUDE.md` — AI assistant context (read before touching any code)
