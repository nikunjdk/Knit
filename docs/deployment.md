# Deployment Guide

Knit has three independently deployed components:

| Component | Platform | Branch → Environment |
|-----------|----------|---------------------|
| Backend API | Railway | `qa` → QA · `main` → prod |
| Frontend | Firebase Hosting | `qa` → QA · `main` → prod |
| Database | Supabase | `qa` → QA project · `main` → prod project |

---

## Backend (Railway)

### How deployment works

Railway is connected to the GitHub repo. When the backend CI workflow passes on `qa` or `main`, Railway auto-deploys the service (requires "Wait for CI" enabled in the Railway dashboard).

The service's **Root Directory** must be set to `backend/` in Railway Settings → Source. Railway reads `backend/railpack.toml` for the start command and health check config.

### Creating a new Railway service

1. In Railway: New Project → Deploy from GitHub repo → select `nikunjdk/Knit`
2. Settings → Source → **Root Directory**: `backend`
3. Settings → Deploy → **Wait for CI**: enabled
4. Variables → add all required env vars (see below)
5. First deploy happens automatically when CI next passes on the connected branch

### Required environment variables (Railway)

| Variable | Where to get it |
|----------|----------------|
| `SUPABASE_URL` | Supabase dashboard → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API |
| `SUPABASE_JWT_SECRET` | Supabase dashboard → Project Settings → API |
| `GEMINI_API_KEY` | Google AI Studio |
| `LINKD_API_KEY` | LinkdAPI dashboard |
| `UPSTASH_REDIS_URL` | Upstash console → REST API |
| `UPSTASH_REDIS_TOKEN` | Upstash console → REST API |
| `ENVIRONMENT` | Set to `prod` for production service, `qa` for QA |
| `LOG_LEVEL` | `INFO` for prod, `DEBUG` for QA |

### Health check

Railway checks `GET /health` every 30 seconds (configured in `railpack.toml`). If the health check fails during deployment, Railway rolls back. The endpoint returns:

```json
{ "status": "ok", "environment": "prod" }
```

### Troubleshooting deployment failures

| Symptom | Likely cause |
|---------|-------------|
| Build fails | Check Railway build logs; usually a Poetry install error |
| Health check times out | Missing env vars cause a startup `ValidationError` before the port binds |
| App crashes after start | Check Railway runtime logs for Python tracebacks |

---

## Frontend (Firebase Hosting)

### How deployment works

The `frontend-ci.yml` GitHub Actions workflow builds and deploys automatically after CI passes on `qa` or `main`.

`API_BASE_URL` is compiled into the Flutter web bundle at build time via `--dart-define`. There is no runtime config — changing the backend URL requires a new build.

### Manual deploy (emergency)

```bash
cd frontend
flutter build web --release --dart-define=API_BASE_URL=https://your-api.railway.app
firebase deploy --only hosting --project prod
```

### Firebase project setup

Two Firebase projects are expected: `qa` and `prod`. Each must have Hosting configured. The `FIREBASE_TOKEN` GitHub secret authenticates the CLI in CI.

---

## Database (Supabase)

### How migrations work

Migrations in `supabase/migrations/` are applied automatically via the Supabase Migrations GitHub Actions workflow when files change on `qa` or `main`.

### Two Supabase projects

Maintain separate projects for QA and prod. Each needs:
- `pgcrypto` and `vector` extensions enabled (first migration handles this)
- A service role key for the Railway backend
- A JWT secret that matches `SUPABASE_JWT_SECRET` in Railway

### Auth setup (per project)

1. Supabase dashboard → Authentication → Providers → Google → enable
2. Set **Authorized redirect URIs** to your app's URL (`https://joinknit.app` for prod)
3. Add Google OAuth credentials (Client ID + Secret)

### First-time database setup

```bash
# Install Supabase CLI
brew install supabase/tap/supabase

# Apply all migrations to a fresh project
supabase db push --db-url "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres"
```

All 11 migrations run in order; they are idempotent (`CREATE OR REPLACE`, `DROP POLICY IF EXISTS`).

---

## Environment Summary

| Config item | QA | Prod |
|-------------|-----|------|
| Backend URL | Railway QA service URL | Railway prod service URL |
| Frontend URL | Firebase QA hosting URL | `https://joinknit.app` |
| Supabase project | knit-qa | knit-prod |
| `ENVIRONMENT` var | `qa` | `prod` |
| Swagger UI at `/docs` | ✅ Enabled | ❌ Disabled |
| CORS origin | `*` | `https://joinknit.app` only |
