# Knit — Claude Code Implementation Guide
**From empty directory to production deploy**

---

## Overview

This guide assumes:
- Empty project directory
- Claude Pro plan (claude.ai + Claude Code terminal access)
- VS Code + Claude extension installed
- Flutter, Python 3.12+, Node.js 18+ already installed
- Git + GitHub CLI (`gh`) installed

The philosophy: Claude Code does the heavy lifting, you review and steer. Every phase ends with working, deployable code — not a half-finished feature.

---

## Phase 0 — Environment & Tooling Setup (Do this once)

### 0.1 Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude --version   # verify
```

### 0.2 Connect MCP Servers

These give Claude Code direct access to your infrastructure. Run these commands **once** — they persist across sessions.

**Supabase MCP** (manages DB, runs migrations, reads schema):
```bash
# Official Supabase MCP — OAuth login, no PAT needed
claude mcp add supabase --transport http https://mcp.supabase.com/mcp
# It will open a browser for OAuth login to your Supabase account
```

**GitHub MCP** (create repos, PRs, manage Actions):
```bash
# Requires a GitHub PAT with repo + workflow scopes
# Create at: https://github.com/settings/tokens
claude mcp add-json github '{
  "type": "http",
  "url": "https://api.githubcopilot.com/mcp",
  "headers": {"Authorization": "Bearer YOUR_GITHUB_PAT"}
}'
```

**Railway MCP** (deploy, check logs, manage env vars):
```bash
npm install -g @railway/cli
railway login
claude mcp add railway-mcp-server -- npx -y @railway/mcp-server
```

**Verify all MCPs are active:**
```bash
claude mcp list
# Should show: supabase ✓   github ✓   railway-mcp-server ✓
```

### 0.3 Create the project directory

```bash
mkdir knit && cd knit
```

### 0.4 Set up the Claude project

Open VS Code:
```bash
code .
```

In the VS Code Claude extension sidebar, create a **New Project** called "Knit". Copy your `CLAUDE.md` content into the project instructions (Settings → Project Instructions). This loads your stack, schema decisions, and MVP scope into every Claude Code session automatically.

Also add your three planning artifacts to the project:
- `knit_schema.sql`
- `knit_api_contracts.md`
- `Design_system.md`

> **Why this matters:** Every Claude Code session in this project will have full context. You won't re-explain the schema, the two-host architecture, or the canonical pair constraint.

---

## Phase 1 — Repository & CI/CD Scaffold

**Goal:** GitHub repo, branch strategy, GitHub Actions pipelines for both backend and frontend — before a single line of app code.

### Prompt 1.1 — Create the repo and monorepo structure

Open Claude Code terminal (`claude` in your project dir). Give it this prompt:

```
Read CLAUDE.md. Then:

Create a GitHub repository called "knit" (private) using the GitHub MCP.

Then scaffold a monorepo with this exact structure:
knit/
  backend/          # FastAPI — Python
  frontend/         # Flutter Web
  supabase/         # migrations, seed data
    migrations/
    seed/
  .github/
    workflows/
  .env.example
  README.md
  CLAUDE.md         # copy from project root

Rules:
- backend/ gets a pyproject.toml (Poetry), not requirements.txt
- frontend/ gets a fresh Flutter web project: `flutter create . --platforms web`
- supabase/migrations/ gets the schema from knit_schema.sql split into numbered files:
    0001_extensions.sql
    0002_profiles.sql
    0003_interest_tags.sql
    0004_events.sql
    0005_event_attendees.sql
    0006_scores_similarity.sql
    0007_connections_icebreaker.sql
    0008_rls_policies.sql
    0009_functions_triggers.sql
- .env.example lists every env var the backend needs (values blank, keys present)
- .gitignore covers Python, Flutter, and Node
- Initial commit and push to main

Do not write any application logic yet. Scaffold only.
```

### Prompt 1.2 — GitHub Actions pipelines

```
Still in the knit repo. Set up three GitHub Actions workflows:

1. backend-ci.yml
   Trigger: push/PR to main affecting backend/**
   Steps:
   - Python 3.12, install Poetry deps
   - ruff lint + format check
   - pytest (even though tests dir is empty, pipeline must pass)
   - On merge to main: deploy to Railway production via railway CLI
     (use RAILWAY_TOKEN secret)

2. frontend-ci.yml
   Trigger: push/PR to main affecting frontend/**
   Steps:
   - Flutter stable channel
   - flutter analyze
   - flutter test (same — empty but pipeline passes)
   - On merge to main: flutter build web, deploy to Firebase Hosting production
     (use FIREBASE_TOKEN secret)

3. supabase-migrations.yml
   Trigger: push to main affecting supabase/migrations/**
   Steps:
   - Install Supabase CLI
   - Run: supabase db push --db-url $SUPABASE_DB_URL
     (use SUPABASE_DB_URL secret for prod)

Add a branch protection rule note in README.md:
- main: requires PR + passing CI before merge
- develop: free push (our dev branch)

All secrets are referenced by name — do not put values in the workflow files.
After creating the files, commit and push. Show me the final Actions tab URL.
```

### Prompt 1.3 — Environments

```
Set up two environments in the repo:

Create backend/.env.qa and backend/.env.prod templates (values blank):
  SUPABASE_URL=
  SUPABASE_ANON_KEY=
  SUPABASE_SERVICE_ROLE_KEY=
  SUPABASE_JWT_SECRET=
  GEMINI_API_KEY=
  LINKD_API_KEY=
  UPSTASH_REDIS_URL=
  UPSTASH_REDIS_TOKEN=
  RESEND_API_KEY=
  ENVIRONMENT=  # "qa" or "prod"
  LOG_LEVEL=    # "DEBUG" for qa, "INFO" for prod

In backend/app/core/config.py, create a Settings class using pydantic-settings:
- Loads from .env file based on ENVIRONMENT variable
- All fields required (fail loudly at startup if missing)
- Expose a get_settings() function with lru_cache

In Railway, we'll have two services: knit-api-qa and knit-api-prod.
The GitHub Actions deploy step should deploy to prod only on merge to main.
Add a manual deploy step for QA in the workflow (workflow_dispatch trigger).

Commit and push.
```

---

## Phase 2 — Database (Supabase)

**Goal:** Schema deployed to Supabase, RLS verified, seed data loaded, pgvector enabled.

### Setup: Create two Supabase projects

Do this manually in the Supabase dashboard before running prompts:
1. Create `knit-qa` project
2. Create `knit-prod` project
3. Copy their DB URLs and service role keys into your .env files

### Prompt 2.1 — Apply schema via MCP

```
Using the Supabase MCP, connect to my knit-qa project.

Apply migrations in order from supabase/migrations/:
  0001 through 0009

After each migration, confirm it applied without errors.

After all migrations:
1. Verify pgvector extension is enabled (SELECT * FROM pg_extension WHERE extname = 'vector')
2. Verify all 8 tables exist with correct columns
3. Verify the interest_tags seed data has 31 rows
4. Run a quick RLS sanity check: confirm RLS is enabled on profiles, events, 
   event_attendees, connections, icebreaker_cache, event_attendee_scores, profile_similarity
5. Test the canonical_pair() function: 
   SELECT * FROM canonical_pair('aaaaaaaa-0000-0000-0000-000000000001'::uuid, 
                                'aaaaaaaa-0000-0000-0000-000000000002'::uuid)
   — should return (000...1, 000...2)
   SELECT * FROM canonical_pair('aaaaaaaa-0000-0000-0000-000000000002'::uuid,
                                'aaaaaaaa-0000-0000-0000-000000000001'::uuid)
   — should also return (000...1, 000...2)

Show me results for each verification step. Fix anything that fails.
```

### Prompt 2.2 — Apply to prod

```
Repeat the same migration + verification process on knit-prod via Supabase MCP.
Same steps, same checks. Confirm both environments are in sync.
```

---

## Phase 3 — FastAPI Backend

**Goal:** All 5 endpoints implemented, tested locally, deployed to Railway QA.

Work in `backend/`. Build one endpoint group at a time, in this order.

### Prompt 3.1 — Project structure and core

```
Read CLAUDE.md and knit_api_contracts.md.

In backend/, set up the FastAPI project structure:

backend/
  app/
    core/
      config.py        # already done in Phase 1
      supabase.py      # Supabase admin client (service role)
      redis.py         # Upstash Redis client
      auth.py          # JWT validation dependency
      logging.py       # structured logging (JSON in prod, pretty in dev)
    models/
      profiles.py      # Pydantic models
      events.py
      attendees.py
    routes/
      events.py        # GET /events/lookup
      profiles.py      # POST /enrich-profile
      embeddings.py    # POST /embeddings/recompute
      icebreaker.py    # GET /icebreaker/stream
      digest.py        # GET /digest/stream
    services/
      gemini.py        # Gemini API wrapper (embed + generate)
      linkd.py         # LinkdAPI wrapper
      scoring.py       # cosine similarity + score upsert logic
    main.py            # FastAPI app, CORS, router registration, health check
  tests/
    conftest.py        # pytest fixtures (mock Supabase, mock Redis, mock Gemini)
    test_events.py
    test_profiles.py
    test_embeddings.py
    test_icebreaker.py
    test_digest.py
  pyproject.toml

Rules:
- Use async throughout (httpx for external calls, asyncpg via supabase-py)
- No global state except the settings singleton and redis client
- Every route has a docstring referencing which section of knit_api_contracts.md it implements
- main.py has GET /health that returns {"status": "ok", "environment": settings.ENVIRONMENT}
- CORS: allow all origins in QA, restrict to joinknit.app in prod
- Do not implement business logic yet — just structure, wiring, and the health endpoint

Commit when done.
```

### Prompt 3.2 — Event lookup endpoint

```
Implement GET /events/lookup (Section 2.5 of knit_api_contracts.md).

This is the only unauthenticated endpoint. It:
1. Takes ?join_code=KN4X2 as query param
2. Queries Supabase with service role key (bypasses RLS)
3. Joins with profiles to get organizer_name
4. Counts event_attendees for attendee_count
5. Returns the response shape from the contracts doc
6. Returns 404 if not found, 410 if is_active = false

Error handling:
- Any Supabase error → 500 with generic message (don't leak DB errors)
- join_code validation: must be 1-10 chars alphanumeric, reject anything else with 400

Write the implementation AND the test in tests/test_events.py.
The test should mock the Supabase client and cover:
- Happy path (returns event)
- 404 (event not found)
- 410 (event inactive)
- 400 (invalid join code format)

Run pytest tests/test_events.py — all tests must pass before we move on.
Commit when green.
```

### Prompt 3.3 — LinkedIn enrichment endpoint

```
Implement POST /enrich-profile (Section 2.1 of knit_api_contracts.md).

This endpoint:
1. Requires JWT auth (use the verify_jwt dependency)
2. Calls LinkdAPI GET /profile/full?username=<extracted_username> with 3s timeout
3. Maps the response: headline → role + company (split on " at ", " @ ", " | " — try in order)
4. Maps skills[] → interest tags: call Gemini to match skills to our 31 predefined tags
   (the Gemini call for tag mapping should be cached in Redis: key "tagmap:{md5(skills_json)}", TTL 7 days)
5. On success: PATCH profiles table via Supabase service role, then return enriched fields
6. Returns 422 on no usable data, 503 on timeout

For the tag-mapping Gemini prompt:
  "Map these LinkedIn skills to the closest tags from this list: {interest_tags_list}.
   Return ONLY a JSON array of matching tags. Max 5. Only include tags from the provided list.
   Skills: {skills}"

Write tests in tests/test_profiles.py covering:
- Happy path (LinkdAPI returns good data)
- 422 (empty/unusable response)
- 503 (timeout)
- Auth failure (no JWT → 401)
- Tag mapping returns only valid tags from our list

Run pytest tests/test_profiles.py — all pass. Commit.
```

### Prompt 3.4 — Embeddings endpoint

```
Implement POST /embeddings/recompute (Section 2.2 of knit_api_contracts.md).

This endpoint:
1. Requires JWT auth
2. Takes {user_id, event_id (nullable)}
3. Fetches profile from Supabase (service role)
4. Builds profile text: "{role} at {company}. Interests: {interests joined with ', '}"
   Handle nulls gracefully — omit fields that are null
5. Calls Gemini text-embedding-004, gets 768d vector
6. PATCH profiles.profile_embedding
7. If event_id provided:
   a. Fetch event_attendees.agenda for this user+event
   b. Build event text: "{profile_text}. Event goal: {agenda}"
   c. Embed → PATCH event_attendees.event_embedding
   d. Fetch ALL other attendees' event_embeddings in this event
   e. Compute cosine similarity between this user and each other
   f. Upsert to event_attendee_scores (canonical pair order — use canonical_pair())
8. Check Redis circuit breaker BEFORE calling Gemini — return 429 if open
9. After Gemini call: INCR gemini:daily_count, set TTL to midnight UTC on first increment

In services/scoring.py:
  def cosine_similarity(a: list[float], b: list[float]) -> float
  — use numpy, return float 0–1

In services/gemini.py:
  async def embed_text(text: str) -> list[float]
  async def next_midnight_utc() -> int  # unix timestamp

Write tests covering:
- Profile-only recompute (no event_id)
- Full recompute with event_id, 3 other attendees → 3 score rows
- Circuit breaker open → 429 before any Gemini call
- Null profile fields handled gracefully

Run pytest tests/test_embeddings.py. Commit.
```

### Prompt 3.5 — Icebreaker streaming endpoint

```
Implement GET /icebreaker/stream (Section 2.3 of knit_api_contracts.md).

SSE endpoint. Requires JWT auth.

Flow (follow this exactly — order matters for cost control):
1. Resolve canonical pair from (jwt.sub, other_user_id)
2. Check Redis: key "icebreaker:{event_id}:{user_a}:{user_b}"
   → cache hit: stream as SSE chunks (split on spaces, ~10 words per chunk), then done event, return
3. Check Postgres icebreaker_cache table
   → hit: write to Redis (TTL 7 days), stream, return
4. Check Redis circuit breaker → 429 if open
5. Fetch both profiles + event data from Supabase (service role)
   → if either user not in the event: 404
6. Build prompt from template in CLAUDE.md
7. Stream Gemini response as SSE: {"chunk": "..."} events
8. On complete:
   a. INSERT to icebreaker_cache (Postgres)
   b. Write to Redis (TTL 7 days)
   c. INCR gemini:daily_count

SSE response format (as in contracts):
  data: {"chunk": "Here's a great opener..."}\n\n
  data: {"done": true}\n\n

Error mid-stream:
  data: {"error": "CIRCUIT_BREAKER_OPEN"}\n\n

Use FastAPI's StreamingResponse with media_type="text/event-stream".
Add headers: Cache-Control: no-cache, X-Accel-Buffering: no

Tests in tests/test_icebreaker.py:
- Redis cache hit (no Gemini call)
- Postgres cache hit (writes to Redis, no Gemini call)
- Full generation (both caches miss)
- Circuit breaker open → 429 before Gemini
- Users not in same event → 404

Run pytest tests/test_icebreaker.py. Commit.
```

### Prompt 3.6 — Digest streaming endpoint

```
Implement GET /digest/stream (Section 2.4 of knit_api_contracts.md).

SSE endpoint. Requires JWT auth. Organizer only.

Flow:
1. Verify jwt.sub == events.organizer_id → 403 if not
2. Fetch events.digest_generation_count
   → if >= 3: return 403 DIGEST_CAP_REACHED
3. Check Redis circuit breaker → 429 if open
4. Fetch stats:
   - attendee_count: COUNT(*) from event_attendees WHERE event_id = ?
   - connection_count: COUNT(*) from connections WHERE event_id = ?
   - top_tags: aggregate interests from all attendees' profiles, top 3 by frequency
   - connection_density: connection_count / (attendee_count * (attendee_count - 1) / 2)
     (handle division by zero when attendee_count < 2)
5. Send stats SSE event FIRST (before streaming starts):
   data: {"stats": {...}}\n\n
6. Fetch all attendees' profiles + agendas
7. Build prompt from template in CLAUDE.md
8. Stream Gemini response as SSE chunks
9. On complete:
   a. ATOMIC increment: UPDATE events SET digest_generation_count = digest_generation_count + 1
      WHERE id = ? AND digest_generation_count < 3
      (if 0 rows updated: someone else hit the cap — return 403)
   b. INCR gemini:daily_count
   c. Send: data: {"done": true, "generations_remaining": <3 - new_count>}\n\n

Tests:
- Organizer generates (count 0 → 1)
- Count already 3 → 403 before any Gemini call
- Non-organizer → 403
- Circuit breaker → 429
- Stats calculation: connection_density with 0 connections

Run pytest tests/test_digest.py. Commit.
```

### Prompt 3.7 — Local run + Railway deploy

```
1. Start the backend locally:
   uvicorn app.main:app --reload --env-file .env.qa
   
   Hit GET /health — confirm {"status": "ok", "environment": "qa"}
   Hit GET /events/lookup?join_code=TEST — confirm 404 (expected, no data yet)

2. Using Railway MCP:
   - Create two Railway services: knit-api-qa and knit-api-prod
   - Set all env vars from .env.qa on knit-api-qa
   - Set all env vars from .env.prod on knit-api-prod
   - Deploy the backend to knit-api-qa from the current main branch
   - Wait for deploy to complete, then hit the Railway URL /health

3. Show me:
   - The Railway QA service URL
   - The /health response from Railway
   - Any deploy errors (if any, fix them)

Commit any fixes. The QA backend must be live before we move to the frontend.
```

---

## Phase 4 — Flutter Frontend

**Goal:** Full UI wired to live backend and Supabase. Build screen by screen.

Work in `frontend/`. Each prompt is one screen or one service module.

### Prompt 4.1 — Flutter project setup and service layer

```
Read CLAUDE.md and knit_api_contracts.md.

In frontend/, set up the Flutter Web project:

1. pubspec.yaml dependencies:
   - supabase_flutter: ^2.x
   - http: ^1.x
   - qr_flutter: ^4.x
   - go_router: ^14.x
   - flutter_dotenv: ^5.x
   - cached_network_image: ^3.x
   - google_fonts (for web fallback)

2. lib/theme/tokens.dart
   All design tokens from CLAUDE.md — colors, radii, typography.
   No magic numbers anywhere else. Use ThemeData with ColorScheme.

3. lib/services/supabase_service.dart
   Skeleton with method stubs (no implementation yet) for every
   Supabase call in the API contracts. Each stub throws UnimplementedError.
   
4. lib/services/knit_api_service.dart
   Skeleton with method stubs for every FastAPI call.
   Includes the SSE streaming pattern from contracts Part 4.
   Base URL from flutter_dotenv.

5. lib/router.dart
   go_router setup with these routes:
   /                    → redirect to /events if authed, /join if not
   /join/:join_code     → EventPreviewScreen
   /auth/callback       → AuthCallbackScreen (Supabase OAuth redirect)
   /onboarding          → OnboardingScreen (new user profile setup)
   /events              → EventsScreen (organizer dashboard)
   /events/new          → CreateEventScreen
   /events/:event_id    → EventDetailScreen (attendee list)
   /connections         → ConnectionsScreen
   /profile             → ProfileScreen
   
   Auth guard: all routes except /join/* and /auth/callback require auth.
   Redirect unauthenticated users to /join (show a generic "sign in" state).

6. lib/main.dart wired up, app runs in browser (flutter run -d chrome)

Do not implement any screen yet. Scaffold and router only.
Confirm: flutter run -d chrome shows a blank scaffold with correct bottom nav.
Commit.
```

### Prompt 4.2 — Auth and join flow

```
Implement the full join flow (Section 6 of knit_api_contracts.md).

Screens to build:

1. EventPreviewScreen (/join/:join_code)
   - On load: call KnitApiService.lookupEvent(joinCode)
   - Show: event title, date/time, location, agenda, organizer name, attendee count
   - Design: clean card layout, agenda in the surface-colored strip (tokens.knitSurface)
   - CTA button: "Join with Google" (knitAccent color)
   - On tap: initiate Supabase Google OAuth
   - Handle ?ref= param: parse and store referred_by UUID in memory (pass through auth flow)
   - Error states: 404 (event not found), 410 (event ended)

2. AuthCallbackScreen (/auth/callback)
   - Supabase handles the OAuth redirect here
   - On session established: check if profile exists
     → exists: navigate to /events/:event_id (resume join) or /events (returning user)
     → not exists: navigate to /onboarding
   - Show loading spinner while checking

3. OnboardingScreen (/onboarding) — new users only
   - Fields: role (text), company (text), interests (chip selector — up to 5)
   - Interest chips: load from Supabase interest_tags, grouped by category
   - LinkedIn URL field (optional): on blur, if URL entered, call POST /enrich-profile
     Show loading state, then pre-fill role/company/interests if enrichment succeeds
     Show "Could not load LinkedIn data" toast on failure — never block the user
   - Save button: PATCH /profiles, then POST /embeddings/recompute (fire and forget),
     then POST /event_attendees (if there's a pending join), then navigate to event list

Design rules (apply to all screens):
- Georgia serif for headings, system sans for body
- All colors from tokens.dart — never hardcode
- Mobile-first: max content width 480px, centered on desktop
- Bottom nav visible only after auth (hide on /join and /onboarding)

Commit when all three screens are working end-to-end.
Run the join flow manually: open /join/TEST, tap Join with Google, complete OAuth,
confirm you land on onboarding.
```

### Prompt 4.3 — Attendee list screen

```
Implement EventDetailScreen (/events/:event_id) — the core screen.

This is the screen attendees use standing in the room. It must be fast and scannable.

Layout:
- Top: event title + live badge (if event is today) + agenda strip (knitSurface bg)
- Body: scrollable list of attendee cards
- Each card shows:
  - Avatar (CircleAvatar, cached)
  - Name (Georgia, 16px bold)
  - Role at Company (14px, knitInk2)
  - Interest tags (horizontal chip row, knitAccentBg bg, knitAccent text, max 3 shown)
  - Relevance score pill (0–100, knitAccent bg if > 60, knitBorder bg if lower)
  - "Met" badge if connection exists (knitMet color)
  - Icebreaker button (subtle, bottom right of card)

Data loading:
1. Fetch attendees: GET /event_attendees (with profiles embedded)
2. Fetch scores: GET /event_attendee_scores (for current user)
3. Sort: by score descending. No score = sort to bottom.
4. Apply privacy filtering client-side:
   For each attendee, merge their default_privacy + privacy_overrides for this event.
   Hide fields where privacy = false.
5. Fetch connections: GET /connections (to know who's already met)
All three fetches happen in parallel (Future.wait).

On tap attendee card:
→ Navigate to AttendeeDetailSheet (bottom sheet, not a new screen)

Bottom sheet:
- Full profile (respecting privacy)
- Icebreaker section:
  - Check Supabase icebreaker_cache first (Section 1.8)
  - If cached: show immediately
  - If not: "Get icebreaker" button → call GET /icebreaker/stream
    Stream text in word by word as it arrives
- "Mark as met" button (knitMet color when active)
- Notes field (auto-save on blur, PATCH /connections)
- LinkedIn button (if visible per privacy)

Organizer sees this same screen PLUS a floating "Generate Digest" button 
(only visible if they're the organizer of this event).

Handle empty state: "No one else has joined yet. Share your link!"

Commit when working. Test with at least one real attendee in QA.
```

### Prompt 4.4 — Organizer screens

```
Implement the organizer-side screens.

1. EventsScreen (/events) — organizer dashboard
   - List of events (organizer_id = current user)
   - Each row: title, date, attendee count, connection count
   - Tap → navigate to EventDetailScreen
   - FAB: "Create Event" → /events/new
   - Empty state: "Create your first event"

2. CreateEventScreen (/events/new)
   - Fields: title (required), description, location, date range (start + end date picker),
     start time, end time, agenda (multiline)
   - join_code: auto-generated (5-char alphanumeric, shown read-only)
     Add a "regenerate" icon button in case they want a different code
   - Submit: POST /events
   - On success: navigate to EventDetailScreen for the new event
   - Show QR code immediately after creation (use qr_flutter package)
     QR encodes: https://joinknit.app/join/{join_code}

3. Digest section (inside EventDetailScreen, organizer only)
   - Stats bar: attendee count, connections made, top 3 tags
     (populated from the stats SSE event when digest is generated)
   - "Generate Digest" button
     - Disabled if digest_generation_count >= 3 (show "3/3 used" label)
     - On tap: call GET /digest/stream
     - Stats arrive first — populate the stats bar
     - Digest text streams in below
   - Copy button (copies digest text to clipboard)
   - Share checklist below the digest:
     [ ] QR code shared at event
     [ ] Posted on LinkedIn
     [ ] Digest shared
     (checkboxes PATCH events.sharing_checklist)

4. QR code display screen (reachable from EventDetailScreen header icon)
   - Full-screen QR for the join link
   - "Your share link" with copy button: https://joinknit.app/join/{join_code}?ref={user_id}
   - Instructions: "Attendees scan this to join and see your profile first"

Commit when working end-to-end.
```

### Prompt 4.5 — Connections and Profile screens

```
Implement the remaining two nav screens.

1. ConnectionsScreen (/connections)
   Shows all connections across all events.
   - Grouped by event (section headers)
   - Each connection: avatar, name, role, company, your notes preview
   - Tap: show full note + edit field
   - Empty state: "Your connections will appear here after events"

2. ProfileScreen (/profile)
   - Show current profile (name, role, company, interests, LinkedIn)
   - Edit button: same form as onboarding
   - On save: PATCH /profiles + POST /embeddings/recompute (fire and forget)
   - Email opt-in toggle
   - Default privacy toggles (role, company, linkedin_url, interests)
   - Sign out button (bottom, subtle, knitInk3 color)

Both screens use the same card/list patterns established in Phase 4.3.
Commit when working.
```

### Prompt 4.6 — Polish and mobile testing

```
Polish pass before deploy.

1. Loading states: every data fetch shows a skeleton loader (not a spinner).
   Use AnimatedOpacity + Container with knitBorder bg for skeleton shapes.

2. Error states: every screen handles network errors gracefully.
   Show a retry button with the error message. Never show a raw exception.

3. Toast notifications: implement a lightweight toast system (no external package).
   Show success/error toasts for: profile saved, icebreaker generated, 
   digest generated, connection marked, link copied.

4. Empty states: every list screen has a meaningful empty state with an illustration
   (SVG inline, using our accent color scheme) and a clear CTA.

5. Mobile viewport: test in Chrome DevTools at 375px width (iPhone SE).
   Fix any overflow, crowded tap targets (min 44px), or text that's too small.

6. Deep link handling: ensure /join/:join_code works when opened directly in browser
   (not navigated to — Firebase Hosting needs a rewrite rule for SPA routing).
   Add firebase.json with the SPA rewrite rule.

7. The bottom nav must show the correct active state for the current route.

Commit when all polish items are done.
```

---

## Phase 5 — Firebase Hosting Deploy

**Goal:** Flutter Web live on Firebase Hosting.

### Setup: Create Firebase project (do manually)
1. Go to console.firebase.google.com
2. Create project "knit-qa" and "knit-prod"
3. Enable Hosting for both
4. Run `npm install -g firebase-tools && firebase login`

### Prompt 5.1 — Firebase deploy

```
In frontend/:

1. Run: firebase init hosting
   - Select knit-qa project
   - Public directory: build/web
   - Single-page app: Yes
   - Don't overwrite index.html

2. Create firebase.json:
{
  "hosting": {
    "public": "build/web",
    "ignore": ["firebase.json", "**/.*"],
    "rewrites": [{"source": "**", "destination": "/index.html"}]
  }
}

3. Create .firebaserc with both qa and prod targets.

4. Update frontend-ci.yml to:
   - Build: flutter build web --release --dart-define=API_BASE_URL=$KNIT_API_URL
   - Deploy QA: firebase deploy --only hosting --project knit-qa
   - Deploy Prod: firebase deploy --only hosting --project knit-prod
     (prod only on merge to main)

5. Build and deploy to QA now:
   flutter build web --release
   firebase deploy --only hosting --project knit-qa

Show me the Firebase Hosting URL. Open it and confirm the app loads.
```

---

## Phase 6 — End-to-End QA

**Goal:** Run the full join flow on QA with real services before touching prod.

### Prompt 6.1 — QA smoke test

```
Run a full end-to-end test on QA. Do this step by step, noting any failures:

Setup:
- Use Railway MCP to confirm knit-api-qa is running
- Use Supabase MCP to confirm knit-qa DB has the correct schema

Test sequence:
1. ORGANIZER FLOW
   a. Open the QA Firebase URL in browser
   b. Sign in with Google (use your real account)
   c. Complete onboarding: role "Senior Technology Associate", company "Morgan Stanley",
      interests ["AI/ML", "Fintech", "Web Dev"]
   d. Create event: "Knit Test Event", today's date, location "Mumbai"
   e. Confirm QR code appears and join code is shown
   f. Copy the join link

2. ATTENDEE FLOW (simulate in incognito tab)
   a. Open the join link in incognito
   b. Confirm event preview screen shows correct event details
   c. Sign in with a second Google account
   d. Complete onboarding with different interests
   e. Confirm you land on the attendee list

3. RELEVANCE
   a. Back to organizer account — refresh attendee list
   b. Confirm the attendee appears with a relevance score
   c. If no score: check Railway logs for embedding errors

4. ICEBREAKER
   a. Tap the attendee card → open bottom sheet
   b. Tap "Get icebreaker"
   c. Confirm text streams in
   d. Tap again — confirm it loads instantly from cache (no streaming)

5. MARK AS MET + NOTES
   a. Tap "Mark as met" — confirm green badge appears
   b. Add a note — confirm it persists on refresh

6. DIGEST (organizer)
   a. Go back to event detail as organizer
   b. Tap "Generate Digest"
   c. Confirm stats bar populates (attendees: 2, connections: 1)
   d. Confirm digest text streams in
   e. Copy and verify text is coherent

Report any failures with the relevant error from Railway/Supabase logs.
Fix each failure before moving on. Do not proceed to prod until all 6 steps pass.
```

---

## Phase 7 — Production Deploy

Only after QA passes completely.

### Prompt 7.1 — Prod deploy checklist

```
Deploy to production. Follow this checklist in order:

1. DATABASE
   Using Supabase MCP, run all migrations on knit-prod.
   Verify schema matches knit-qa exactly.

2. BACKEND
   Using Railway MCP:
   - Set all prod env vars on knit-api-prod (same as qa but with prod keys)
   - ENVIRONMENT=prod
   - CORS: restrict to https://joinknit.app (update main.py if needed)
   - LOG_LEVEL=INFO
   - Deploy to knit-api-prod
   - Confirm /health returns {"status": "ok", "environment": "prod"}

3. FRONTEND
   - flutter build web --release --dart-define=API_BASE_URL=<prod_railway_url>
   - firebase deploy --only hosting --project knit-prod
   - Confirm the prod Firebase URL loads

4. CUSTOM DOMAIN (optional — set up if you have joinknit.app)
   Firebase Hosting → Custom domains → add joinknit.app

5. GITHUB SECRETS
   Add these to the repo so CI/CD can deploy automatically:
   RAILWAY_TOKEN → Railway API token
   FIREBASE_TOKEN → firebase token (run: firebase login:ci)
   SUPABASE_DB_URL_PROD → knit-prod DB URL
   KNIT_API_URL_PROD → knit-api-prod Railway URL

6. FINAL SMOKE TEST
   Repeat the 6-step QA flow on prod. 
   One real organizer (you), one real attendee, one real digest.

Show me the final prod URL and confirm health check passes.
```

---

## Phase 8 — Maintenance Prompts (Use As Needed)

Keep these handy for ongoing work.

### Debug a Railway failure
```
Using Railway MCP, check logs for knit-api-[qa|prod] for the last 100 lines.
I'm seeing [describe the symptom]. Identify the root cause and fix it.
```

### Add a new migration
```
I need to add [describe schema change]. 
Create a new migration file: supabase/migrations/00XX_description.sql
Apply it to knit-qa via Supabase MCP. Verify it runs clean.
Show me the migration SQL before applying it.
```

### Check Gemini quota
```
Using Supabase MCP, run this query on knit-qa:
  -- check today's circuit breaker state
Using Redis (Upstash), check the value of gemini:daily_count.
Tell me how many calls have been made today and how close we are to the 1200 limit.
```

### Fix a UI bug on mobile
```
[Paste a screenshot or describe the issue]
Open EventDetailScreen (or whichever screen). The issue is: [description].
Fix it. Mobile-first — test at 375px. Don't change anything else.
```

---

## Sequence Summary

```
Phase 0  │ Claude Code install, MCP servers (Supabase + GitHub + Railway)
Phase 1  │ Repo, monorepo structure, GitHub Actions, environments
Phase 2  │ Supabase schema deployed (QA + prod)
Phase 3  │ FastAPI: 5 endpoints, tests, Railway QA deploy
Phase 4  │ Flutter: all screens, service layer, full join flow
Phase 5  │ Firebase Hosting QA deploy
Phase 6  │ Full end-to-end QA (all 6 flows pass)
Phase 7  │ Production deploy + final smoke test
```

Each phase ends with a commit and a working deployed state. Never start the next phase if the current one has unresolved errors.

---

## Tips for Working With Claude Code on This Project

**Start every session with context:**
```
We're building Knit. Read CLAUDE.md before doing anything.
Current status: [Phase X, last thing completed].
Today's task: [specific goal].
```

**When Claude drifts from the plan:**
```
Stop. Read CLAUDE.md again — specifically the [relevant section].
You're [describe the drift]. Revert to the architecture we decided.
```

**When you hit a bug:**
```
Using [Railway/Supabase] MCP, get the logs/error.
Here's what's happening: [describe symptom].
Read the relevant endpoint in knit_api_contracts.md, then fix the implementation.
Don't change anything outside [specific file].
```

**Keep Claude focused:**
Give one phase at a time. Claude Code works best with clear scope.
"Implement the icebreaker endpoint and its tests" > "Build the backend".

**Let Claude use its MCPs:**
Don't copy-paste Supabase table contents or Railway logs manually.
Say "check the Supabase MCP" or "check Railway logs" — let Claude look.
