# Knit — API Contracts
**Version:** MVP v1.0  
**Last updated:** 2026-05-28

---

## Architecture Overview

Flutter talks to **two hosts**:

| Client | Host | Auth |
|--------|------|------|
| `SupabaseService` | `https://<project>.supabase.co` | Supabase JWT (Bearer) |
| `KnitApiService` | `https://<project>.railway.app` | Same Supabase JWT (Bearer) |

FastAPI validates Supabase JWTs using the shared JWT secret (`SUPABASE_JWT_SECRET` env var). No custom auth layer.

All timestamps: **ISO 8601 UTC** (`2026-05-28T10:00:00Z`).  
All IDs: **UUID v4**.  
Error shape (both hosts):
```json
{ "error": "human-readable message", "code": "MACHINE_READABLE_CODE" }
```

---

## Part 1 — Supabase Direct (Flutter → PostgREST)

Flutter uses `supabase_flutter`. All calls include the Supabase JWT automatically via the client. RLS enforces authorization — no additional checks needed in Flutter.

---

### 1.1 Auth

**Google OAuth Sign-In**
```dart
await supabase.auth.signInWithOAuth(OAuthProvider.google);
// Supabase redirects back with session. Profile creation triggered via onAuthStateChange.
```

**Sign Out**
```dart
await supabase.auth.signOut();
```

**Get current user**
```dart
final user = supabase.auth.currentUser; // User? — null if not signed in
```

---

### 1.2 Profiles

**Create profile** (called once on first sign-in, after Google OAuth)
```
POST /profiles
```
Body:
```json
{
  "id": "<auth.uid()>",
  "full_name": "Nikunj Sharma",
  "email": "nikunj@example.com",
  "avatar_url": "https://lh3.googleusercontent.com/..."
}
```
Notes: `id` must equal `auth.uid()` (enforced by RLS). `role`, `company`, `interests`, `linkedin_url` are null at creation — filled during onboarding or via LinkdAPI enrichment.

**Get own profile**
```
GET /profiles?id=eq.<uid>&select=*
```
Response: `profiles` row.

**Update own profile**
```
PATCH /profiles?id=eq.<uid>
```
Body (partial — only send changed fields):
```json
{
  "role": "Software Engineer",
  "company": "Morgan Stanley",
  "interests": ["AI/ML", "Fintech", "Web Dev"],
  "linkedin_url": "https://linkedin.com/in/nikunj",
  "default_privacy": { "role": true, "company": true, "linkedin_url": false, "interests": true }
}
```
Constraint: `interests` max length 5 enforced by DB CHECK. Backend will also re-trigger embedding recompute via `POST /embeddings/recompute` after this call.

**Get another user's profile** (co-attendee — RLS allows this)
```
GET /profiles?id=eq.<target_uid>&select=id,full_name,avatar_url,role,company,interests,linkedin_url
```
Notes: Only fetch fields the privacy settings allow. Privacy filtering is done client-side by reading `default_privacy` from the target's profile combined with their `event_attendees.privacy_overrides` for the current event.

---

### 1.3 Interest Tags

**Get all tags** (for profile setup UI — grouped by category)
```
GET /interest_tags?select=tag,category,sort_order&order=category.asc,sort_order.asc
```
Response:
```json
[
  { "tag": "AI/ML", "category": "Tech", "sort_order": 1 },
  { "tag": "Web Dev", "category": "Tech", "sort_order": 2 }
]
```
No auth required (public read granted to `anon`).

---

### 1.4 Events

**Create event** (organizer)
```
POST /events
```
Body:
```json
{
  "organizer_id": "<auth.uid()>",
  "title": "Mumbai AI Meetup",
  "description": "Monthly AI/ML networking event",
  "location": "Bombay Connect, BKC",
  "start_date": "2026-05-29",
  "end_date": "2026-05-29",
  "start_time": "18:00",
  "end_time": "21:00",
  "join_code": "KN4X2",
  "agenda": "6pm: Arrivals\n7pm: Lightning talks\n8pm: Networking"
}
```
Notes: `join_code` generated client-side (5-char alphanumeric, uppercase). Generate and retry on 409 conflict. `digest_generation_count` defaults to 0.

Response: full `events` row including `id`.

**Get event by join code** (attendee joining)
```
GET /events?join_code=eq.KN4X2&select=id,title,description,location,start_date,end_date,start_time,end_time,agenda,organizer_id,is_active
```
Notes: Called before auth to show event preview. Requires Supabase anon key with events policy allowing public read by join_code. **Flag:** current RLS requires auth. Either add a public-read policy scoped to `is_active = true` events, or call this from FastAPI as a pre-auth lookup.

**Get own events** (organizer dashboard)
```
GET /events?organizer_id=eq.<uid>&order=start_date.desc&select=*
```

**Get event by ID** (attendee already joined)
```
GET /events?id=eq.<event_id>&select=*
```

**Update sharing checklist**
```
PATCH /events?id=eq.<event_id>
```
Body:
```json
{ "sharing_checklist": { "qr_shared": true, "linkedin_posted": false, "digest_shared": false } }
```

---

### 1.5 Event Attendees

**Join event** (attendee)
```
POST /event_attendees
```
Body:
```json
{
  "event_id": "<event_id>",
  "user_id": "<auth.uid()>",
  "referred_by": "<referrer_uid_or_null>",
  "agenda": "Looking to find a technical cofounder"
}
```
Notes: `referred_by` is populated if the join URL contains `?ref=<user_id>`. On 409 (already joined), treat as success and fetch existing row.

**Get attendees for event** (sorted by relevance — see 1.6)
```
GET /event_attendees?event_id=eq.<event_id>&is_visible=eq.true&select=user_id,agenda,joined_at,profiles(id,full_name,avatar_url,role,company,interests,linkedin_url,default_privacy)
```
Notes: Join with profiles via Supabase's embedded resource syntax. Sort by relevance score is done client-side using pre-fetched scores (see 1.6), not in this query.

**Check if already joined**
```
GET /event_attendees?event_id=eq.<event_id>&user_id=eq.<uid>&select=id
```

**Update own event_attendees row** (agenda, privacy overrides, visibility)
```
PATCH /event_attendees?event_id=eq.<event_id>&user_id=eq.<uid>
```
Body:
```json
{
  "agenda": "Updated intent",
  "privacy_overrides": { "linkedin_url": true },
  "is_visible": true
}
```

---

### 1.6 Relevance Scores

**Get scores for current user in event** (to sort attendee list)
```
GET /event_attendee_scores?event_id=eq.<event_id>&or=(user_a_id.eq.<uid>,user_b_id.eq.<uid>)&select=user_a_id,user_b_id,score
```
Notes: Returns all pairs involving the current user. Flutter maps this to `{ other_user_id: score }` dict and sorts the attendee list by score descending. Users with no score entry sort to the bottom.

---

### 1.7 Connections (Mark as Met)

**Mark as met**
```
POST /connections
```
Body:
```json
{
  "event_id": "<event_id>",
  "user_a_id": "<min(uid, other_uid)>",
  "user_b_id": "<max(uid, other_uid)>"
}
```
Notes: Flutter must enforce min/max ordering before insert. On 409 (already marked), treat as success.

**Add/update note**
```
PATCH /connections?event_id=eq.<event_id>&user_a_id=eq.<a>&user_b_id=eq.<b>
```
Body (current user is a → update notes_a; current user is b → update notes_b):
```json
{ "notes_a": "Wants to collaborate on AI tooling" }
```
Notes: Flutter determines which `notes_` column to update by comparing `auth.uid()` to `user_a_id`.

**Get own connections for event**
```
GET /connections?event_id=eq.<event_id>&or=(user_a_id.eq.<uid>,user_b_id.eq.<uid>)&select=*
```

---

### 1.8 Icebreaker Cache (Read Only from Flutter)

**Check if icebreaker already exists** (before calling FastAPI stream)
```
GET /icebreaker_cache?event_id=eq.<event_id>&user_a_id=eq.<min_uid>&user_b_id=eq.<max_uid>&select=content
```
If row exists, render cached content directly. If not, call `GET /icebreaker/stream`.

---

## Part 2 — FastAPI Endpoints (Flutter → Railway)

Base URL: `https://<project>.railway.app`  
All endpoints require: `Authorization: Bearer <supabase_jwt>`  
FastAPI extracts `sub` (= user UUID) from JWT for all business logic.

### JWT Validation (FastAPI dependency, used by all endpoints)
```python
# Dependency: verify_jwt(token: str = Depends(oauth2_scheme)) -> dict
# Validates against SUPABASE_JWT_SECRET, returns decoded payload
# Raises HTTP 401 on invalid/expired token
```

---

### 2.1 Profile Enrichment

**Enrich profile from LinkedIn URL**
```
POST /enrich-profile
```
Request:
```json
{ "linkedin_url": "https://linkedin.com/in/nikunj-sharma" }
```
Flow:
1. Extract username from URL
2. Call LinkdAPI `GET /profile/full?username=<username>` (3s timeout)
3. Map `headline` → `role` + `company` (split on " at ", " @ ", " | ")
4. Map `skills[]` → interest tags via Gemini tag-mapping call (cached)
5. Extract `profile_picture_url` → `avatar_url`
6. PATCH `/profiles` in Supabase as service role (bypasses RLS)
7. Enqueue embedding recompute

Response `200`:
```json
{
  "role": "Software Engineer",
  "company": "Morgan Stanley",
  "avatar_url": "https://media.linkedin.com/...",
  "interests": ["AI/ML", "Fintech"],
  "enriched_fields": ["role", "company", "avatar_url", "interests"]
}
```
Response `422` (LinkdAPI returned no usable data):
```json
{ "error": "Could not extract profile data. Please fill in manually.", "code": "ENRICHMENT_FAILED" }
```
Response `503` (LinkdAPI timeout):
```json
{ "error": "LinkedIn enrichment timed out. Please fill in manually.", "code": "ENRICHMENT_TIMEOUT" }
```
Notes: Flutter shows enriched fields pre-filled in the profile form. User can edit before saving. Never silently overwrite — always go through the form.

---

### 2.2 Embedding Recompute

**Recompute embeddings after profile or agenda update**
```
POST /embeddings/recompute
```
Request:
```json
{
  "user_id": "<uid>",
  "event_id": "<event_id_or_null>"
}
```
Notes: Called by Flutter after profile save (for profile embedding) or after joining event / updating event agenda (for event embedding). `event_id` null = recompute profile embedding only.

Flow:
1. Fetch profile from Supabase (service role)
2. Build text: `"{role} at {company}. Interests: {interests joined}"`
3. Call Gemini `text-embedding-004` → 768d vector
4. PATCH `profiles.profile_embedding` (always)
5. If `event_id` provided: fetch `event_attendees.agenda`, build event text: `"{role} at {company}. Interests: {interests}. Event goal: {agenda}"`, embed → PATCH `event_attendees.event_embedding`
6. Recompute scores: cosine similarity between this user's event_embedding and all other attendees' event_embeddings in the same event → upsert `event_attendee_scores`

Response `200`:
```json
{ "status": "ok", "scores_updated": 12 }
```
Response `429` (global circuit breaker tripped):
```json
{ "error": "AI quota reached for today. Scores will update tomorrow.", "code": "CIRCUIT_BREAKER_OPEN" }
```
Notes: This is a background operation. Flutter calls it fire-and-forget after profile save. No blocking UI.

---

### 2.3 Icebreaker (Streaming)

**Stream icebreaker for a pair**
```
GET /icebreaker/stream?event_id=<event_id>&other_user_id=<other_uid>
```
Headers:
```
Authorization: Bearer <jwt>
Accept: text/event-stream
```

Flow:
1. Resolve canonical pair: `(min(uid, other_uid), max(uid, other_uid))`
2. Check Redis: key `icebreaker:{event_id}:{user_a}:{user_b}` → if hit, stream cached content as SSE and return
3. Check Postgres `icebreaker_cache` → if hit, write to Redis, stream and return
4. Check Redis circuit breaker: `gemini:daily_count` ≥ 1200 → return 429
5. Fetch both profiles + event agendas from Supabase (service role)
6. Build prompt (see below)
7. Stream Gemini response as SSE
8. On stream complete: persist to `icebreaker_cache`, increment Redis counter

SSE format:
```
data: {"chunk": "Here's something interesting"}

data: {"chunk": " about both of you..."}

data: {"done": true}
```

Error event (mid-stream):
```
data: {"error": "CIRCUIT_BREAKER_OPEN"}
```

Icebreaker prompt template:
```
You are helping two professionals break the ice at a networking event.

Person A: {name_a}, {role_a} at {company_a}. Interests: {interests_a}. Event goal: {agenda_a}
Person B: {name_b}, {role_b} at {company_b}. Interests: {interests_b}. Event goal: {agenda_b}
Event: {event_title}. Agenda: {event_agenda}

Write 2-3 sentences suggesting a natural conversation starter for Person A to use with Person B.
Focus on genuine common ground. Be specific, not generic. Do not use "Hey" or mention their names.
```

Response `429`:
```json
{ "error": "Daily AI quota reached. Try again tomorrow.", "code": "CIRCUIT_BREAKER_OPEN" }
```

---

### 2.4 Post-Event Digest (Streaming)

**Stream digest for an event** (organizer only)
```
GET /digest/stream?event_id=<event_id>
```
Headers:
```
Authorization: Bearer <jwt>
Accept: text/event-stream
```

Authorization check: `events.organizer_id = jwt.sub`. Return 403 if not organizer.

Flow:
1. Fetch `events.digest_generation_count` from Supabase (service role)
2. If count ≥ 3 → return 403 with `DIGEST_CAP_REACHED`
3. Check Redis circuit breaker → if open, return 429
4. Fetch event stats:
   - Total attendees (count from `event_attendees`)
   - Total connections (count from `connections`)
   - Top interest tags (aggregate from attendees' profiles)
   - Connection density (connections / max_possible_connections)
5. Fetch all attendees' profiles + agendas
6. Build prompt (see below)
7. Stream Gemini response as SSE
8. On stream complete:
   - Increment `events.digest_generation_count` in Postgres (atomic: `UPDATE events SET digest_generation_count = digest_generation_count + 1 WHERE id = ? AND digest_generation_count < 3`)
   - Increment Redis counter

SSE format: same as icebreaker (`chunk` / `done` / `error`).

Stats payload (sent before stream starts as a separate SSE event):
```
data: {"stats": {"attendee_count": 34, "connection_count": 47, "top_tags": ["AI/ML", "Fintech", "Founder"], "connection_density": 0.08}}

data: {"chunk": "Tonight brought together 34 people..."}

data: {"done": true, "generations_remaining": 2}
```

Response `403` (not organizer):
```json
{ "error": "Only the event organizer can generate a digest.", "code": "FORBIDDEN" }
```
Response `403` (cap reached):
```json
{ "error": "Maximum 3 digests per event. Limit reached.", "code": "DIGEST_CAP_REACHED" }
```
Response `429`:
```json
{ "error": "Daily AI quota reached.", "code": "CIRCUIT_BREAKER_OPEN" }
```

Digest prompt template:
```
You are writing a post-event summary for a professional networking meetup organizer 
to share on LinkedIn and Instagram.

Event: {event_title}, {event_date}, {location}
Attendees: {attendee_count} people
Connections made: {connection_count}
Top interest areas: {top_tags}

Attendee profiles (for color):
{formatted_attendees_list}

Write a 3-4 paragraph event digest that:
- Opens with energy and highlights the turnout/connections
- Calls out 2-3 interesting themes or conversations (infer from profiles/tags)
- Ends with a forward-looking CTA for the next event
- Tone: warm, professional, shareable on LinkedIn
- Do not mention specific people by name
- Max 250 words
```

---

### 2.5 Event Lookup (Pre-Auth)

**Look up event by join code** (before user is signed in)
```
GET /events/lookup?join_code=KN4X2
```
No auth required.

Flow: FastAPI queries Supabase with service role key (bypasses RLS).

Response `200`:
```json
{
  "id": "<event_id>",
  "title": "Mumbai AI Meetup",
  "description": "Monthly AI/ML networking event",
  "location": "Bombay Connect, BKC",
  "start_date": "2026-05-29",
  "end_date": "2026-05-29",
  "start_time": "18:00",
  "end_time": "21:00",
  "agenda": "6pm: Arrivals\n7pm: Lightning talks\n8pm: Networking",
  "organizer_name": "Nikunj Sharma",
  "attendee_count": 12,
  "is_active": true
}
```
Response `404`:
```json
{ "error": "Event not found. Check your join code.", "code": "EVENT_NOT_FOUND" }
```
Response `410` (event inactive):
```json
{ "error": "This event has ended.", "code": "EVENT_INACTIVE" }
```

---

## Part 3 — Redis Key Schema (Upstash)

All keys managed by FastAPI only. Flutter never touches Redis.

| Key | Type | Value | TTL |
|-----|------|-------|-----|
| `gemini:daily_count` | String | integer (call count) | Expires at midnight UTC |
| `icebreaker:{event_id}:{user_a}:{user_b}` | String | icebreaker text | 7 days |
| `circuit_breaker:open` | String | `"1"` | Set when count ≥ 1200; cleared at midnight |

Circuit breaker logic:
```python
count = await redis.incr("gemini:daily_count")
if count == 1:
    await redis.expireat("gemini:daily_count", next_midnight_utc())
if count > 1200:
    await redis.set("circuit_breaker:open", "1", exat=next_midnight_utc())
    raise HTTPException(429, ...)
```

---

## Part 4 — Flutter Service Layer

Two service classes. Never mix them.

```dart
// lib/services/supabase_service.dart
// Wraps all direct Supabase PostgREST calls
// Uses: Supabase.instance.client

// lib/services/knit_api_service.dart  
// Wraps all FastAPI calls
// Base URL from env: KNIT_API_BASE_URL
// Always attaches: Authorization: Bearer ${supabase.auth.currentSession!.accessToken}
```

**KnitApiService base pattern:**
```dart
Future<http.Response> _post(String path, Map<String, dynamic> body) async {
  final token = Supabase.instance.client.auth.currentSession!.accessToken;
  return http.post(
    Uri.parse('$_baseUrl$path'),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    },
    body: jsonEncode(body),
  );
}
```

**SSE streaming pattern:**
```dart
Stream<String> streamIcebreaker(String eventId, String otherUserId) async* {
  final token = Supabase.instance.client.auth.currentSession!.accessToken;
  final request = http.Request('GET', Uri.parse(
    '$_baseUrl/icebreaker/stream?event_id=$eventId&other_user_id=$otherUserId'
  ));
  request.headers['Authorization'] = 'Bearer $token';
  request.headers['Accept'] = 'text/event-stream';

  final response = await _client.send(request);
  await for (final chunk in response.stream.transform(utf8.decoder)) {
    for (final line in chunk.split('\n')) {
      if (line.startsWith('data: ')) {
        final data = jsonDecode(line.substring(6));
        if (data['chunk'] != null) yield data['chunk'];
        if (data['done'] == true) return;
        if (data['error'] != null) throw KnitApiException(data['error']);
      }
    }
  }
}
```

---

## Part 5 — Error Handling Summary

| HTTP Code | Meaning | Flutter action |
|-----------|---------|----------------|
| 200 | Success | Render response |
| 201 | Created | Update local state |
| 400 | Bad request (validation) | Show field error |
| 401 | JWT invalid/expired | Re-auth flow |
| 403 | Forbidden (RLS or cap) | Show specific message |
| 404 | Not found | Show not-found UI |
| 409 | Conflict (duplicate) | Treat as success for join/mark-as-met |
| 410 | Gone (event ended) | Show event-ended screen |
| 422 | Unprocessable (enrichment failed) | Fallback to manual input |
| 429 | Rate limited / circuit breaker | Show quota message, hide button |
| 503 | External service timeout | Fallback to manual input |

---

## Part 6 — Join Flow (Full Sequence)

The most complex flow — all the pieces together:

```
1. User scans QR / opens join link
   URL format: https://joinknit.app/join/<join_code>?ref=<referrer_uid>

2. GET /events/lookup?join_code=<code>  [FastAPI, no auth]
   → Show event preview screen

3. User taps "Join with Google"
   → Supabase Google OAuth

4. onAuthStateChange fires with new session
   → GET /profiles?id=eq.<uid>  [Supabase]
   
   If 404 (new user):
     → POST /profiles  [Supabase] with name/email/avatar from Google
     → Navigate to profile setup screen
   
   If 200 (returning user):
     → Navigate directly to step 7

5. Profile setup screen (new users only)
   → User fills role, company, interests (up to 5)
   → Optionally enters LinkedIn URL
   
   If LinkedIn URL entered:
     → POST /enrich-profile  [FastAPI]
     → Pre-fill form with enriched data (user confirms)
   
   → PATCH /profiles  [Supabase]
   → POST /embeddings/recompute (fire-and-forget)  [FastAPI]

6. GET /event_attendees?event_id=eq.<id>&user_id=eq.<uid>  [Supabase]
   If 404:
     → POST /event_attendees  [Supabase] with referred_by from URL
   
7. Navigate to event attendee list
   → GET attendees + scores in parallel
   → Sort by score, render list
```

---

*Next session: [6] Design system*
