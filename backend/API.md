# Knit API Reference

Base URL: `https://<service>.railway.app` (prod) / `http://localhost:8000` (local)

Interactive docs (Swagger UI) are available at `/docs` when running locally or in QA. FastAPI generates the OpenAPI schema automatically from endpoint docstrings and Pydantic models — no separate spec file is needed.

---

## Authentication

All endpoints except `/health` and `/events/lookup` require a Supabase-issued JWT.

```
Authorization: Bearer <supabase_access_token>
```

The token is validated using HS256 against `SUPABASE_JWT_SECRET`. The `sub` claim is used as the user's UUID throughout the API.

**Auth errors:**

| Status | When |
|--------|------|
| `403 Forbidden` | No `Authorization` header |
| `401 Unauthorized` | Token invalid, expired, or missing `sub` claim |

---

## Endpoints

### `GET /health`

Liveness check. No auth required.

**Response `200`:**
```json
{ "status": "ok", "environment": "prod" }
```

---

### `GET /events/lookup`

Public event preview by join code. Called before the Google OAuth redirect so the user sees event details before signing in.

**Query parameters:**

| Param | Type | Required | Validation |
|-------|------|----------|------------|
| `join_code` | string | ✅ | 1–10 chars, uppercase alphanumeric (`^[A-Z0-9]+$`) |

**Response `200`:**
```json
{
  "id": "uuid",
  "title": "Startup Mixer SF",
  "description": "Monthly founders meetup",
  "location": "Runway, SF",
  "start_date": "2026-06-01",
  "end_date": "2026-06-01",
  "start_time": "18:00:00",
  "end_time": "21:00:00",
  "agenda": "Demo night + networking",
  "organizer_name": "Alice Chen",
  "attendee_count": 42,
  "is_active": true
}
```

| Status | When |
|--------|------|
| `404` | Join code not found |
| `410` | Event ended (`is_active = false`) |
| `422` | Join code fails pattern validation |

---

### `POST /enrich-profile`

Fetch LinkedIn data via LinkdAPI, map skills to interest tags, and persist enriched fields to the caller's profile.

**Request body:**
```json
{ "linkedin_url": "https://linkedin.com/in/username" }
```

**Response `200`:**
```json
{
  "full_name": "Alice Chen",
  "role": "Founder",
  "company": "Acme Inc",
  "interests": ["Founder", "AI/ML", "SaaS"],
  "linkedin_url": "https://linkedin.com/in/alicechen",
  "avatar_url": "https://..."
}
```

| Status | When |
|--------|------|
| `422` | Can't extract username from URL, profile not found, or no usable data returned |
| `503` | LinkdAPI timeout or service error |
| `429` | Gemini circuit breaker open (tag mapping step only) |

---

### `POST /embeddings/recompute`

Recompute profile and/or event embeddings and upsert relevance scores. Returns `202` immediately — intended to be called fire-and-forget from the client after profile save.

**Request body:**
```json
{ "event_id": "uuid" }
```
`event_id` is optional. Omitting it recomputes only the cross-event profile embedding (no scoring).

**Response `202`:**
```json
{ "status": "ok" }
```

| Status | When |
|--------|------|
| `429` | Circuit breaker open |
| `503` | Gemini embedding call failed |

---

### `GET /icebreaker/stream`

Generate 3 personalized icebreaker questions as a Server-Sent Events stream. Served from cache when available.

**Query parameters:**

| Param | Type | Required |
|-------|------|----------|
| `event_id` | string (UUID) | ✅ |
| `other_user_id` | string (UUID) | ✅ |

**Response `200` — SSE stream:**

```
data: {"chunk": "1. How did you get into AI/ML?\n"}

data: {"chunk": "2. What's your biggest challenge right now?\n"}

data: {"chunk": "3. Are you looking for co-founders?\n"}

data: {"done": true}
```

| Frame | When |
|-------|------|
| `{"chunk": "<text>"}` | One or more during streaming |
| `{"done": true}` | Stream complete |
| `{"error": "STREAM_ERROR"}` | Gemini failed mid-stream |

| Status | When |
|--------|------|
| `404` | Either user not found in this event |
| `429` | Circuit breaker open (only checked on cache miss) |

---

### `GET /digest/stream`

Generate a post-event digest as a Server-Sent Events stream. Organizer only; capped at 3 generations per event.

**Query parameters:**

| Param | Type | Required |
|-------|------|----------|
| `event_id` | string (UUID) | ✅ |

**Response `200` — SSE stream:**

```
data: {"stats": {"attendee_count": 42, "connection_count": 18, "top_tags": ["Founder", "AI/ML", "SaaS"], "connection_density": 0.0209}}

data: {"chunk": "Tonight brought together 42 founders and engineers..."}

data: {"chunk": " The energy was electric..."}

data: {"done": true, "generations_remaining": 2}
```

The `stats` frame is always first so the UI can render the stats bar before text arrives.

| Frame | When |
|-------|------|
| `{"stats": {...}}` | Always first |
| `{"chunk": "<text>"}` | One or more during generation |
| `{"done": true, "generations_remaining": int}` | Stream complete |
| `{"error": "STREAM_ERROR"}` | Gemini failed mid-stream |

| Status | When |
|--------|------|
| `403` | Caller is not the event organizer |
| `403` + `"DIGEST_CAP_REACHED"` | 3 digests already generated for this event |
| `429` | Circuit breaker open |

---

## Error Shape

All non-2xx responses return:
```json
{ "detail": "Human-readable message" }
```

Machine-readable codes appear as the `detail` string for programmatic handling:

| Code | Endpoint | Meaning |
|------|----------|---------|
| `"DIGEST_CAP_REACHED"` | `/digest/stream` | Event has used all 3 digest generations |
| `"STREAM_ERROR"` | SSE frame in icebreaker + digest | Gemini failed during streaming |

---

## Rate Limits

| Limit | Mechanism | Reset |
|-------|-----------|-------|
| 1200 Gemini calls/day (global) | Redis counter `gemini:daily_count` | Midnight UTC (auto-expiry) |
| 3 digests per event | Postgres `events.digest_generation_count` | Never resets |
| Icebreaker per pair | Cached permanently in `icebreaker_cache` (Redis 7d + Postgres) | 7-day Redis TTL; Postgres never expires |

When the daily Gemini limit is hit, `circuit_breaker:open` is set in Redis and all AI endpoints (`/enrich-profile` tag mapping, `/embeddings/recompute`, `/icebreaker/stream`, `/digest/stream`) return `429` until midnight UTC.
