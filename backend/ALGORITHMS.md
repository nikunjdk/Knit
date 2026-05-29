# Knit — Core Algorithms

This document describes the three AI/ML algorithms and two supporting systems that power Knit's networking features. Read this before modifying any code in `app/services/` or the embedding/icebreaker/digest routes.

---

## 1. Relevance Matching (Embedding-Based Attendee Scoring)

**What it does:** Ranks every other attendee in an event by how relevant they are to the current user, so the people list is sorted by match quality rather than join time.

**Trigger:** `POST /embeddings/recompute` — called fire-and-forget by the Flutter client after a user saves their profile or joins an event.

### Text construction

Two text representations are generated per user per event:

| Embedding | Text format | Stored in |
|-----------|-------------|-----------|
| **Profile** (cross-event) | `"{role} at {company} Interests: {tag1}, {tag2}"` | `profiles.profile_embedding` |
| **Event** (event-scoped) | Profile text + `" Event goal: {agenda}"` | `event_attendees.event_embedding` |

Fields are omitted if null — the profile text never contains `"None"`. If all fields are empty the text falls back to `"professional"`.

### Embedding model

`text-embedding-004` (Google) → 768-dimensional float32 vector.

The Google genai SDK is synchronous, so `embed_text()` wraps the call in `asyncio.to_thread()` to avoid blocking the FastAPI event loop. Each call consumes one unit of the daily Gemini quota.

### Scoring

After the event embedding is written, cosine similarity is computed against every other attendee who already has an event embedding:

```
score = dot(vec_a, vec_b) / (norm(vec_a) * norm(vec_b))
```

Implemented in `app/services/scoring.py:cosine_similarity`. Returns `0.0` if either vector is zero-norm.

Scores are upserted to `event_attendee_scores` with canonical pair ordering (`user_a_id < user_b_id`) — this is enforced by `canonical_pair()` before every write and must stay in sync with the Postgres `canonical_pair()` function.

### How Flutter uses scores

The Flutter client fetches all scores for the current event and builds a `{other_uid: score}` map. The attendee list is sorted client-side by descending score; users with no score entry sort to the bottom.

### HNSW index

Both embedding columns have HNSW indexes (`vector_cosine_ops`) in Postgres for future pgvector-based queries. Current scoring is computed in Python at recompute time, not via SQL.

---

## 2. Icebreaker Generation

**What it does:** Generates 3 personalized icebreaker questions that Person A can ask Person B, grounded in both profiles and event context.

**Endpoint:** `GET /icebreaker/stream` — returns a Server-Sent Events stream.

### Cache lookup (cheapest first)

```
Redis key: icebreaker:{event_id}:{uid_a}:{uid_b}   (7-day TTL)
  ↓ miss
Postgres table: icebreaker_cache  (permanent, warms Redis on hit)
  ↓ miss
Gemini 2.0 Flash  (streams live; cached to Postgres + Redis on completion)
```

**Canonical pair ordering** (`uid_a < uid_b`, enforced by `canonical_pair()`) ensures both `A→B` and `B→A` requests hit the same cache entry. This must be applied before every Redis key construction and Postgres lookup.

### What context is used

Both attendees' `event_attendees` rows are fetched with a profile join:

```
SELECT user_id, agenda, profiles(role, company, interests)
FROM event_attendees
WHERE event_id = ? AND user_id IN (user_id, other_user_id)
```

The prompt describes each person as: `"{role} at {company}, interests: {tags}, event goal: {agenda}"`.

### Prompt structure

```
You are helping two professionals connect at a networking event.
Create 3 concise, personalized icebreaker questions.

Person A: Founder at Acme, interests: AI/ML, SaaS, event goal: find co-founder
Person B: Engineer at BigCo, interests: Open Source, Deep Tech

Generate 3 specific questions Person A could ask Person B...
Return only the numbered questions.
```

### Streaming and caching

Chunks are yielded to the client as they arrive from Gemini. Once the stream completes, the full text is written to Postgres and Redis. Cache writes are non-fatal — the stream reaches the client even if the write fails.

---

## 3. Digest Generation

**What it does:** Produces a post-event AI summary for the organizer covering attendance, connections, and next-event suggestions.

**Endpoint:** `GET /digest/stream` — organizer only; capped at 3 generations per event.

### Stats computation

Computed before calling Gemini; sent as the first SSE frame so the UI can render the stats bar before text arrives.

| Stat | Formula |
|------|---------|
| `attendee_count` | `len(event_attendees)` |
| `connection_count` | `len(connections WHERE event_id = ?)` |
| `connection_density` | `connections / (n*(n-1)/2)` — `0.0` when `n < 2` |
| `top_tags` | Top 3 tags by frequency across all attendee interest arrays |

### Prompt structure

```
Event: {title}
Attendees: {n}
Connections made: {c}
Top interests: {tags}
Connection density: {density%}

Write a warm, insightful 3-paragraph digest covering:
1) who attended and energy, 2) notable connections and themes,
3) suggestions for next event. Under 250 words.
```

### Digest cap (atomic enforcement)

The cap of 3 is checked before calling Gemini (fast pre-check). After a successful stream, the count is incremented via Postgres RPC:

```sql
-- increment_digest_count(p_event_id, p_cap)
UPDATE events
SET digest_generation_count = digest_generation_count + 1
WHERE id = p_event_id AND digest_generation_count < p_cap
RETURNING digest_generation_count;
```

Using `UPDATE ... WHERE count < cap` in a single statement is atomic — no read-modify-write race condition. The column is also protected by `REVOKE UPDATE (digest_generation_count) ON events FROM authenticated` so clients cannot increment it directly via PostgREST.

---

## 4. LinkedIn Interest Tag Mapping

**What it does:** Converts raw LinkedIn skill strings (e.g. "TensorFlow", "Series A fundraising") into a fixed 31-tag taxonomy that the Flutter UI displays as chips.

**Triggered by:** `POST /enrich-profile` when `skills` are present in the LinkdAPI response.

### Tag taxonomy

31 tags across 4 categories defined in `_VALID_TAGS` in `app/routes/profiles.py` and seeded into the `interest_tags` DB table:

| Category | Tags |
|----------|------|
| Tech | AI/ML, Web Dev, Mobile, DevOps, Data, Cybersecurity, Open Source, Blockchain |
| Domain | Fintech, Healthtech, Edtech, Climate, SaaS, Consumer, B2B, Deep Tech |
| Role | Founder, Engineer, Designer, PM, Marketer, Researcher, Investor, Student |
| Goals | Hiring, Job Hunting, Cofounder Search, Investing, Mentoring, Collaborating, Learning |

> **Changing this taxonomy** requires updating `_VALID_TAGS` in the route, the `interest_tags` DB table seed, and remapping existing `profiles.interests` arrays. The Flutter interest chip UI also depends on this set.

### Gemini prompt

```
Map these LinkedIn skills to the closest tags from this list: [sorted _VALID_TAGS].
Return ONLY a JSON array of matching tags. Max 5. Only include tags from the provided list.
Skills: [raw skills list]
```

Gemini sometimes wraps the JSON in markdown code fences (` ```json ... ``` `); these are stripped with a regex before parsing.

### Caching

Results are cached in Redis for 7 days, keyed by `tagmap:{md5(sorted(skills))}`. The MD5 is over the sorted skill list so equivalent skill sets (regardless of order) share a cache entry. Changing the tag taxonomy does not automatically invalidate existing cache entries.

---

## 5. Circuit Breaker

**What it does:** Prevents runaway Gemini spend by blocking all AI endpoints once 1200 calls are made in a calendar day.

### Mechanics

Every call to `embed_text()` or `generate_stream()` calls `increment_gemini_counter(redis)` after completion:

1. `INCR gemini:daily_count` → returns new count
2. On `count == 1`: set TTL to seconds until midnight UTC (auto-reset, no cron needed)
3. On `count >= 1200`: `SET circuit_breaker:open "1" EX 86400`

### What it blocks

All three AI endpoints check `circuit_breaker:open` before calling Gemini and return `429` if set:
- `/embeddings/recompute` — checked before profile embed
- `/icebreaker/stream` — checked after both cache levels miss
- `/digest/stream` — checked before Gemini is called
- `/enrich-profile` tag mapping — indirectly (Gemini tag call only; LinkdAPI still runs)

### Reset

The `gemini:daily_count` key expires at midnight UTC (set on first increment of each day). The `circuit_breaker:open` key has a 24-hour TTL from when it was set, which may not align exactly with midnight — this is intentional conservatism.
