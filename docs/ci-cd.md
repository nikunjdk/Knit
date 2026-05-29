# CI/CD Pipeline

Knit uses GitHub Actions for CI and automated deployment. There are three workflows:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [Backend CI](#backend-ci) | Push/PR to `main`, `qa`, `development` (backend changes) | Lint + test |
| [Frontend CI + Deploy](#frontend-ci--deploy) | Push/PR to `main`, `qa`, `development` (frontend changes) | Analyze + test + deploy to Firebase |
| [Supabase Migrations](#supabase-migrations) | Push to `main` or `qa` (migration file changes) | Apply DB migrations |

---

## Branch → Environment Mapping

| Branch | Backend | Frontend | Database |
|--------|---------|----------|----------|
| `development` | CI only (no deploy) | CI only (no deploy) | — |
| `qa` | Railway QA (auto-deploy after CI) | Firebase QA (auto-deploy after CI) | Supabase QA |
| `main` | Railway prod (auto-deploy after CI) | Firebase prod (auto-deploy after CI) | Supabase prod |

---

## Backend CI

**File:** `.github/workflows/backend-ci.yml`  
**Triggers:** Push or PR to `main`, `qa`, `development` when `backend/**` changes.

**Steps:**
1. Set up Python 3.13
2. Install Poetry + dependencies (`poetry install`)
3. Lint: `ruff check . && ruff format --check .`
4. Test: `pytest` with stub env vars (no real Supabase/Gemini connections)

Railway's "Wait for CI" option is enabled — the Railway service only deploys after this workflow passes. This means CI green = deployment triggered automatically.

**Required GitHub Secrets:** None (test env vars are inline in the workflow).

---

## Frontend CI + Deploy

**File:** `.github/workflows/frontend-ci.yml`  
**Triggers:** Push or PR to `main`, `qa`, `development` when `frontend/**` changes.

**Steps (CI — all branches):**
1. Set up Flutter stable
2. `flutter pub get`
3. `flutter analyze`
4. `flutter test`

**Steps (deploy — `qa` branch on push):**
1. `flutter build web --release --dart-define=API_BASE_URL=$KNIT_API_URL_QA`
2. `firebase deploy --only hosting --project qa`

**Steps (deploy — `main` branch on push):**
1. `flutter build web --release --dart-define=API_BASE_URL=$KNIT_API_URL_PROD`
2. `firebase deploy --only hosting --project prod`

`API_BASE_URL` is injected at build time via `--dart-define` and compiled into the Flutter web bundle. There is no runtime config file.

**Required GitHub Secrets:**

| Secret | Used by |
|--------|---------|
| `KNIT_API_URL_QA` | Frontend QA build |
| `KNIT_API_URL_PROD` | Frontend prod build |
| `FIREBASE_TOKEN` | `firebase deploy` authentication |

---

## Supabase Migrations

**File:** `.github/workflows/supabase-migrations.yml`  
**Triggers:** Push to `main` or `qa` when `supabase/migrations/**` changes.

**Steps:**
1. Install Supabase CLI
2. `supabase db push --db-url <DB_URL>` against the environment matching the branch

Migrations are applied sequentially in filename order (`YYYYMMDDHHMMSS_` prefix). The CLI tracks which migrations have been applied in the `supabase_migrations` schema table and skips already-applied ones.

**Required GitHub Secrets:**

| Secret | Used by |
|--------|---------|
| `SUPABASE_DB_URL_QA` | QA migration job |
| `SUPABASE_DB_URL_PROD` | Prod migration job |

---

## Adding a New Migration

1. Create `supabase/migrations/YYYYMMDDHHMMSS_description.sql`
2. Test locally: `supabase db push --db-url <your-local-or-qa-url>`
3. Push to `qa` branch → CI applies migration to Supabase QA
4. Merge to `main` → CI applies migration to Supabase prod

> Never modify an already-applied migration file. Create a new migration instead.
