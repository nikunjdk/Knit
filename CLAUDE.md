# CLAUDE.md — Knit

> AI assistant context file. Read this before touching any code in this repo.

---

## What is Knit

Lightweight meetup networking web app. Two user types:

- **Organizers**: create events → get QR + join link → receive shareable post-event AI digest
- **Attendees**: join via QR/code → build profile → see relevance-sorted people → get AI icebreakers → mark who they met + notes

Core problem solved: people at in-person meetups don't know who to approach, and forget connections within 48 hours.

GTM: organizer-first. Organizers are the distribution channel. The digest is the organizer's "wow moment." Viral loop: attendees who are organizers become the next organizer.

---

## Tech Stack (locked — do not suggest changes)

| Layer                 | Technology                                                                      |
| --------------------- | ------------------------------------------------------------------------------- |
| Frontend              | Flutter Web (Firebase Hosting)                                                  |
| Backend               | FastAPI (Railway)                                                               |
| Database              | Supabase Postgres + Auth                                                        |
| Auth                  | Google OAuth via Supabase (both organizers and attendees)                       |
| Cache / Rate limiting | Upstash Redis                                                                   |
| AI                    | Gemini 2.0 Flash (icebreakers + digest), `text-embedding-004` 768d (embeddings) |
| Email                 | Resend                                                                          |
| LinkedIn enrichment   | LinkdAPI (manual fallback — NO scraping)                                        |
| Vector search         | pgvector (enabled in Supabase)                                                  |

---

## Architecture

Flutter talks to **two hosts only**:

```
SupabaseService   →  https://<project>.supabase.co   (PostgREST, Supabase JWT)
KnitApiService    →  https://<project>.railway.app   (FastAPI, same Supabase JWT)
```

FastAPI validates Supabase JWTs via `SUPABASE_JWT_SECRET`. No custom auth layer.

FastAPI has **4 endpoints** (plus one pre-auth lookup):

1. `POST /enrich-profile` — LinkedIn enrichment via LinkdAPI
2. `POST /embeddings/recompute` — profile + event embeddings, score upsert
3. `GET /icebreaker/stream` — SSE, cached per pair
4. `GET /digest/stream` — SSE, organizer only, max 3 generations
5. `GET /events/lookup` — pre-auth event preview by join code

Everything else is Flutter → Supabase PostgREST directly.

---

## Key Schema Decisions (hard to change later)

- `profiles` is **global**, not per-event. Persists across events.
- `event_attendees` is the join table with **per-event overrides** (agenda, privacy, visibility).
- Symmetric pairs (`connections`, `icebreaker_cache`, `profile_similarity`, `event_attendee_scores`) always stored as `user_a_id < user_b_id`. Use `canonical_pair()` helper before every insert.
- Two embedding columns: `profiles.profile_embedding` (cross-event) and `event_attendees.event_embedding` (event-scoped, blends profile + agenda).
- `digest_generation_count` cap (≤ 3) enforced in **Postgres** (authoritative). Redis is fast-path only.
- `referred_by` nullable FK on `event_attendees` — populated from `?ref=<user_id>` in join URL.
- `role`/`company` are plain text fields on `profiles` — no enum, no separate organizer role. Organizer vs attendee is derived from context (`events.organizer_id`).
- `email_opt_in` boolean on `profiles`, default `true`.
- Privacy: `profiles.default_privacy` JSONB + per-event `event_attendees.privacy_overrides`. Client-side filtering — never server-filtered.

---

## Data Flow: Embeddings & Scoring

```
Profile save / event agenda update
  → POST /embeddings/recompute (fire-and-forget, non-blocking)
    → Gemini text-embedding-004 → 768d vector
    → PATCH profiles.profile_embedding  (always)
    → If event_id: PATCH event_attendees.event_embedding
    → Cosine similarity vs all event attendees
    → Upsert event_attendee_scores (canonical pair order)
```

Relevance sort in Flutter: fetch scores, build `{ other_uid: score }` map, sort attendee list client-side. Users with no score entry sort to bottom.

---

## Cost Controls (do not remove these)

| Control                | Mechanism                                                                               |
| ---------------------- | --------------------------------------------------------------------------------------- |
| Icebreaker dedup       | Cache per pair in `icebreaker_cache` (Postgres durable) + Redis (warm)                  |
| Digest cap             | Max 3 per event, atomic Postgres increment                                              |
| Global circuit breaker | Redis `gemini:daily_count` ≥ 1200 → set `circuit_breaker:open`, cleared at midnight UTC |

Circuit breaker key schema:

```
gemini:daily_count               String   integer   expires midnight UTC
icebreaker:{event_id}:{a}:{b}    String   text      7 days
circuit_breaker:open             String   "1"       expires midnight UTC
```

---

## Join Flow (most complex — read before touching auth/join code)

```
1. User scans QR / opens https://joinknit.app/join/<join_code>?ref=<referrer_uid>
2. GET /events/lookup (FastAPI, no auth) → event preview screen
3. "Join with Google" → Supabase Google OAuth
4. onAuthStateChange → GET /profiles
   - 404 (new user) → POST /profiles → profile setup screen
   - 200 (returning) → skip to step 7
5. Profile setup (new users): role, company, interests (max 5), optional LinkedIn
   - LinkedIn entered → POST /enrich-profile → pre-fill form → user confirms
   - PATCH /profiles → POST /embeddings/recompute (fire-and-forget)
6. POST /event_attendees (with referred_by from URL if present)
7. Navigate to attendee list (fetch attendees + scores in parallel)
```

---

## MVP Scope (locked)

**In:**

- Event creation + join link + QR display
- Attendee profile (name, role, interests, LinkedIn via LinkdAPI + manual fallback)
- Per-event agenda field
- Attendee list sorted by relevance + agenda
- AI icebreaker per person (streamed, cached)
- Mark as met + private notes
- Attendee share QR with `ref=attendee_id`
- Post-event digest for organizer (streamed, max 3 generations, stats bar)
- Sharing checklist per event

**Explicitly cut from V1:**

- Luma / Meetup.com import
- OAuth for social accounts (plain text handles only)
- Cross-event community graph UI (data model exists, UI hidden)
- Post-event follow-up nudge emails

**V2 (do not implement or suggest):**

- "Run your own event" attendee → organizer CTA
- Cross-event community graph UI
- 48-hour follow-up nudge emails
- Third-party event platform import

---

## Design System (tokens.dart — never hardcode)

```
Accent:       #c4622d   (CTA, active states, score pills)
Accent light: #e8956a   (icebreaker border)
Accent bg:    #fdf1eb   (icebreaker bg, selected tag bg)
Met:          #2d6a4f   / bg #eaf4ee
Live badge:   #1a6e3c   / bg #e2f4ea
App bg:       #faf8f4
Surface:      #f4f0e8   (agenda strip)
Card:         #ffffff
Border:       #e8e2d8 / #d4ccc0 (emphasis)
Ink:          #1a1714 / #5a5550 / #9a948e
```

Typography: **Georgia serif throughout.**
Radii: 8 / 12 / 14 / 20px / full. Horizontal padding: 20px standard.

Navigation:

- Global bottom nav: Events · Connections · Profile
- Event view: back arrow only (drill-down from Events list)

UI is **mobile-first** — used standing in a room on a phone.

---

## Flutter Service Layer

```
lib/services/supabase_service.dart   — all PostgREST calls
lib/services/knit_api_service.dart   — all FastAPI calls
```

Never mix these. `KnitApiService` always attaches `Authorization: Bearer <supabase_access_token>`.

---

## Conventions

- All timestamps: `timestamptz` UTC / ISO 8601 (`2026-05-28T10:00:00Z`)
- All IDs: UUID v4
- Error shape: `{ "error": "human message", "code": "MACHINE_CODE" }`
- Canonical pair ordering: always call `canonical_pair(a, b)` before inserting to any symmetric table
- `join_code`: 5-char uppercase alphanumeric, generated client-side, retry on 409
- Privacy filtering: client-side only. Merge `default_privacy` + `privacy_overrides` in Flutter before rendering.
- Organizer can optionally join their own event as an attendee (no special handling needed — same flow)

---

## Planning Progress

- [x] 1. Problem + solution framing
- [x] 2. User flows
- [x] 3. Data model (`knit_schema.sql`)
- [x] 4. API contracts (`knit_api_contracts.md`)
- [x] 5. API contracts review + finalization
- [x] 6. Design system (`Design_system.md`)
- [x] 7. CLAUDE.md ← you are here
- [ ] 8. Implementation
