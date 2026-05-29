# Database Reference

Knit uses Supabase Postgres. Migrations live in `supabase/migrations/` and are applied automatically via CI when changes land on `qa` or `main`.

> **Note:** The schema is used by both the Flutter client (via PostgREST with RLS) and the FastAPI backend (via service role, bypassing RLS). Changes here affect both.

---

## Extensions

```sql
pgcrypto   -- gen_random_uuid()
vector     -- pgvector for 768-d embeddings (HNSW index)
```

---

## Tables

### `profiles`

Global user profile — persists across all events.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | References `auth.users(id)` |
| `full_name` | TEXT NOT NULL | |
| `avatar_url` | TEXT | |
| `email` | TEXT NOT NULL | |
| `email_opt_in` | BOOLEAN | Default `true` |
| `role` | TEXT | Plain text, no enum |
| `company` | TEXT | |
| `linkedin_url` | TEXT | |
| `interests` | TEXT[] | Max 5 elements (DB constraint) |
| `profile_embedding` | vector(768) | Cross-event embedding; HNSW index |
| `default_privacy` | JSONB | `{"role": true, "company": true, "linkedin_url": false, "interests": true}` |
| `created_at` / `updated_at` | TIMESTAMPTZ | `updated_at` auto-set by trigger |

---

### `events`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `organizer_id` | UUID | FK → `profiles(id)`, ON DELETE RESTRICT |
| `title` | TEXT NOT NULL | |
| `description` / `location` / `agenda` | TEXT | |
| `start_date` / `end_date` | DATE | `end_date >= start_date` constraint |
| `start_time` / `end_time` | TIME | |
| `join_code` | TEXT UNIQUE | 5-char uppercase alphanumeric |
| `sharing_checklist` | JSONB | |
| `digest_generation_count` | INT | Max 3 (DB constraint); increment via `increment_digest_count()` only |
| `is_active` | BOOLEAN | Default `true` |

---

### `event_attendees`

Per-event attendee record with event-scoped overrides.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `event_id` | UUID | FK → `events(id)`, ON DELETE CASCADE |
| `user_id` | UUID | FK → `profiles(id)`, ON DELETE CASCADE; UNIQUE with `event_id` |
| `referred_by` | UUID | FK → `profiles(id)`, ON DELETE SET NULL; populated from `?ref=` in join URL |
| `agenda` | TEXT | Individual event goals; used in event embedding |
| `privacy_overrides` | JSONB | Per-event override of `profiles.default_privacy` |
| `event_embedding` | vector(768) | Event-scoped embedding (profile + agenda); HNSW index |
| `is_visible` | BOOLEAN | Default `true`; hides attendee from peer list |
| `joined_at` | TIMESTAMPTZ | |

---

### `event_attendee_scores`

Relevance scores between attendee pairs within an event.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | UUID | PK component |
| `user_a_id` | UUID | PK component; always `< user_b_id` (DB constraint) |
| `user_b_id` | UUID | PK component |
| `score` | FLOAT | Cosine similarity in [0, 1] |
| `computed_at` | TIMESTAMPTZ | |

> **Canonical pair ordering** is enforced by a DB constraint (`user_a_id < user_b_id`) and must be applied in application code via `canonical_pair()` before every write.

---

### `profile_similarity`

Cross-event profile similarity (not actively used in V1 UI but data is captured).

Same structure as `event_attendee_scores` without `event_id`. Canonical pair ordering enforced.

---

### `connections`

"Mark as met" records.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `event_id` | UUID | FK → `events(id)` |
| `user_a_id` / `user_b_id` | UUID | Canonical order enforced; UNIQUE with `event_id` |
| `notes_a` / `notes_b` | TEXT | Private notes per user |
| `met_at` | TIMESTAMPTZ | |

---

### `icebreaker_cache`

Durable icebreaker cache. Redis is the warm cache; this is the source of truth.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | UUID | PK component |
| `user_a_id` / `user_b_id` | UUID | PK components; canonical order enforced |
| `content` | TEXT | Full generated text |
| `generated_at` | TIMESTAMPTZ | |

---

### `interest_tags`

Reference table for the 31-tag taxonomy. Read by Flutter to render interest chips.

| Column | Type | Notes |
|--------|------|-------|
| `tag` | TEXT PK | |
| `category` | TEXT | Tech / Domain / Role / Goals |
| `sort_order` | INT | Display order within category |

`SELECT` granted to `anon` and `authenticated`.

---

## Row-Level Security

RLS is enabled on all tables. The backend API uses `SUPABASE_SERVICE_ROLE_KEY` and bypasses RLS entirely. The Flutter client uses the user's JWT (authenticated role) and is subject to all policies.

| Table | SELECT | INSERT | UPDATE |
|-------|--------|--------|--------|
| `profiles` | Own row + co-attendees (`is_visible=true`) | Own row | Own row; `id` and `email` columns locked |
| `events` | Own events + events user attends | `organizer_id = auth.uid()` | Own events; `digest_generation_count` column locked |
| `event_attendees` | Own row + co-attendees in same event | `user_id = auth.uid()` | Own row; `event_id`, `user_id`, `referred_by` locked |
| `connections` | Own connections | Must be `user_a_id` or `user_b_id` | Own connections |
| `icebreaker_cache` | Must be one of the pair | Backend only (service role) | Backend only |
| `event_attendee_scores` | Must attend the event | Backend only | Backend only |

---

## Functions and Triggers

### `set_updated_at()` (trigger)

Automatically sets `updated_at = NOW()` before any UPDATE on `profiles` and `events`.

### `canonical_pair(a UUID, b UUID)`

Returns `(min(a,b), max(a,b))` as `(user_a, user_b)`. Used in SQL to ensure canonical ordering before inserts into symmetric tables. The Python equivalent in `app/services/scoring.py` must stay in sync.

### `increment_digest_count(p_event_id UUID, p_cap INT)`

Atomically increments `events.digest_generation_count` only if it's below `p_cap`. Returns the updated count row, or empty if already at cap. Called by the backend via Supabase RPC after a successful digest stream.

---

## Migrations

Migrations are in `supabase/migrations/` with filenames in `YYYYMMDDHHMMSS_name.sql` format.

| Migration | Purpose |
|-----------|---------|
| `20260528205827_extensions` | pgcrypto + pgvector |
| `20260528211130_profiles` | profiles table + HNSW index |
| `20260528211144_interest_tags` | 31-tag taxonomy seed data |
| `20260528211152_events` | events table |
| `20260528211158_event_attendees` | event_attendees + HNSW index |
| `20260528211209_scores_similarity` | event_attendee_scores + profile_similarity |
| `20260528211216_connections_icebreaker` | connections + icebreaker_cache |
| `20260528211228_rls_policies` | RLS policies for all tables |
| `20260528211235_functions_triggers` | set_updated_at trigger + canonical_pair function |
| `20260528222848_digest_count_function` | increment_digest_count RPC |
| `20260529000001_fix_rls_with_check` | Security fix: WITH CHECK on UPDATE policies + REVOKE sensitive columns |

Applied automatically on push to `qa` or `main` via the **Supabase Migrations** GitHub Actions workflow.
