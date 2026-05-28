-- ============================================================
-- KNIT — Database Schema
-- Supabase Postgres + pgvector
-- All timestamps: timestamptz (UTC)
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- 1. PROFILES
-- Global, 1:1 with auth.users. Persists across events.
-- ============================================================
CREATE TABLE profiles (
    id                  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name           TEXT NOT NULL,
    avatar_url          TEXT,
    email               TEXT NOT NULL,
    email_opt_in        BOOLEAN NOT NULL DEFAULT TRUE,

    -- Professional info (pre-filled from LinkdAPI, editable)
    role                TEXT,
    company             TEXT,
    linkedin_url        TEXT,

    -- Interest tags: validated against interest_tags seed table on write
    -- max 5 enforced via CHECK constraint
    interests           TEXT[] NOT NULL DEFAULT '{}' CHECK (array_length(interests, 1) <= 5),

    -- Profile-level embedding (Gemini text-embedding-004, 768d)
    -- Built from: role + company + interests joined as text
    profile_embedding   vector(768),

    -- Default privacy preferences (can be overridden per event in event_attendees)
    -- Fields: role, company, linkedin_url, interests
    default_privacy     JSONB NOT NULL DEFAULT '{"role": true, "company": true, "linkedin_url": false, "interests": true}',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_profile_embedding ON profiles
    USING hnsw (profile_embedding vector_cosine_ops);

-- ============================================================
-- 2. INTEREST_TAGS (seed / validation table)
-- Not FK-joined to profiles. Backend validates TEXT[] against this.
-- ============================================================
CREATE TABLE interest_tags (
    tag         TEXT PRIMARY KEY,
    category    TEXT NOT NULL,  -- 'Tech', 'Domain', 'Role', 'Goals'
    sort_order  INT NOT NULL DEFAULT 0
);

-- Seed data
INSERT INTO interest_tags (tag, category, sort_order) VALUES
    -- Tech
    ('AI/ML',           'Tech', 1),
    ('Web Dev',         'Tech', 2),
    ('Mobile',          'Tech', 3),
    ('DevOps',          'Tech', 4),
    ('Data',            'Tech', 5),
    ('Cybersecurity',   'Tech', 6),
    ('Open Source',     'Tech', 7),
    ('Blockchain',      'Tech', 8),
    -- Domain
    ('Fintech',         'Domain', 1),
    ('Healthtech',      'Domain', 2),
    ('Edtech',          'Domain', 3),
    ('Climate',         'Domain', 4),
    ('SaaS',            'Domain', 5),
    ('Consumer',        'Domain', 6),
    ('B2B',             'Domain', 7),
    ('Deep Tech',       'Domain', 8),
    -- Role
    ('Founder',         'Role', 1),
    ('Engineer',        'Role', 2),
    ('Designer',        'Role', 3),
    ('PM',              'Role', 4),
    ('Marketer',        'Role', 5),
    ('Researcher',      'Role', 6),
    ('Investor',        'Role', 7),
    ('Student',         'Role', 8),
    -- Goals
    ('Hiring',          'Goals', 1),
    ('Job Hunting',     'Goals', 2),
    ('Cofounder Search','Goals', 3),
    ('Investing',       'Goals', 4),
    ('Mentoring',       'Goals', 5),
    ('Collaborating',   'Goals', 6),
    ('Learning',        'Goals', 7);

-- ============================================================
-- 3. EVENTS
-- Organizer creates. Multi-day supported.
-- ============================================================
CREATE TABLE events (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizer_id                UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,

    title                       TEXT NOT NULL,
    description                 TEXT,
    location                    TEXT,

    -- Multi-day support. end_time nullable — if null, closes EOD on end_date.
    start_date                  DATE NOT NULL,
    end_date                    DATE NOT NULL,
    start_time                  TIME,      -- nullable
    end_time                    TIME,      -- nullable; null = close at end of end_date

    -- Short alphanumeric code for manual join (e.g. "KN4X2")
    join_code                   TEXT NOT NULL UNIQUE,

    -- Agenda shown to attendees on join and in event view
    agenda                      TEXT,

    -- Sharing checklist state for organizer UI (jsonb, flexible)
    -- e.g. {"qr_shared": true, "linkedin_posted": false, "digest_shared": false}
    sharing_checklist           JSONB NOT NULL DEFAULT '{}',

    -- Digest generation cap: max 3. Enforced here (authoritative).
    -- Redis is fast-path only.
    digest_generation_count     INT NOT NULL DEFAULT 0 CHECK (digest_generation_count <= 3),

    -- Soft delete / archival
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT end_date_gte_start CHECK (end_date >= start_date)
);

CREATE INDEX idx_events_organizer ON events(organizer_id);
CREATE INDEX idx_events_join_code ON events(join_code);

-- ============================================================
-- 4. EVENT_ATTENDEES
-- Join table: one row per (user, event). Per-event overrides live here.
-- ============================================================
CREATE TABLE event_attendees (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    -- Optional: who shared the join link with this attendee
    referred_by     UUID REFERENCES profiles(id) ON DELETE SET NULL,

    -- Per-event agenda / intent (optional, shown to matches)
    agenda          TEXT,

    -- Per-event privacy overrides (inherits from profiles.default_privacy if null)
    -- Only overridden fields appear here; null = use profile default
    privacy_overrides JSONB,  -- e.g. {"linkedin_url": true}

    -- Event-level embedding: built from profile fields + this event's agenda
    -- Used for relevance scoring within this specific event context
    event_embedding vector(768),

    -- Whether attendee is visible to others in this event
    is_visible      BOOLEAN NOT NULL DEFAULT TRUE,

    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(event_id, user_id)
);

CREATE INDEX idx_event_attendees_event ON event_attendees(event_id);
CREATE INDEX idx_event_attendees_user ON event_attendees(user_id);
CREATE INDEX idx_event_attendees_event_embedding ON event_attendees
    USING hnsw (event_embedding vector_cosine_ops);

-- ============================================================
-- 5. PROFILE_SIMILARITY
-- Cross-event, computed from profile_embedding only.
-- Recomputed only when either user updates their profile.
-- user_a_id < user_b_id enforced — one row per unique pair.
-- ============================================================
CREATE TABLE profile_similarity (
    user_a_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    score           FLOAT NOT NULL CHECK (score >= 0 AND score <= 1),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);

CREATE INDEX idx_profile_similarity_a ON profile_similarity(user_a_id);
CREATE INDEX idx_profile_similarity_b ON profile_similarity(user_b_id);

-- ============================================================
-- 6. EVENT_ATTENDEE_SCORES
-- Event-specific final score: blends profile_similarity + agenda match.
-- Recomputed when attendee joins or updates event agenda.
-- user_a_id < user_b_id enforced.
-- ============================================================
CREATE TABLE event_attendee_scores (
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_a_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    score           FLOAT NOT NULL CHECK (score >= 0 AND score <= 1),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (event_id, user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);

CREATE INDEX idx_event_scores_event_a ON event_attendee_scores(event_id, user_a_id);
CREATE INDEX idx_event_scores_event_b ON event_attendee_scores(event_id, user_b_id);

-- ============================================================
-- 7. CONNECTIONS (mark-as-met)
-- One row per unique pair per event. user_a_id < user_b_id.
-- ============================================================
CREATE TABLE connections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_a_id   UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id   UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    -- Private notes: each user's notes stored separately
    notes_a     TEXT,   -- notes written by user_a about user_b
    notes_b     TEXT,   -- notes written by user_b about user_a

    met_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(event_id, user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);

CREATE INDEX idx_connections_event_a ON connections(event_id, user_a_id);
CREATE INDEX idx_connections_event_b ON connections(event_id, user_b_id);

-- ============================================================
-- 8. ICEBREAKER_CACHE
-- Persisted in Postgres (durable). Redis is warm cache only.
-- user_a_id < user_b_id enforced.
-- ============================================================
CREATE TABLE icebreaker_cache (
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_a_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (event_id, user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);

-- ============================================================
-- TRIGGERS: updated_at auto-maintenance
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE icebreaker_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_attendee_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_similarity ENABLE ROW LEVEL SECURITY;
-- interest_tags: public read, no RLS needed
GRANT SELECT ON interest_tags TO anon, authenticated;

-- profiles: read own + co-attendees, write own only
CREATE POLICY "profiles_select" ON profiles
    FOR SELECT TO authenticated
    USING (
        id = auth.uid()
        OR id IN (
            SELECT ea2.user_id FROM event_attendees ea1
            JOIN event_attendees ea2 ON ea1.event_id = ea2.event_id
            WHERE ea1.user_id = auth.uid() AND ea2.is_visible = TRUE
        )
    );

CREATE POLICY "profiles_insert" ON profiles
    FOR INSERT TO authenticated
    WITH CHECK (id = auth.uid());

CREATE POLICY "profiles_update" ON profiles
    FOR UPDATE TO authenticated
    USING (id = auth.uid());

-- events: read if organizer or attendee, insert/update if organizer
CREATE POLICY "events_select" ON events
    FOR SELECT TO authenticated
    USING (
        organizer_id = auth.uid()
        OR id IN (SELECT event_id FROM event_attendees WHERE user_id = auth.uid())
    );

CREATE POLICY "events_insert" ON events
    FOR INSERT TO authenticated
    WITH CHECK (organizer_id = auth.uid());

CREATE POLICY "events_update" ON events
    FOR UPDATE TO authenticated
    USING (organizer_id = auth.uid());

-- event_attendees: read co-attendees in same event, write own row
CREATE POLICY "event_attendees_select" ON event_attendees
    FOR SELECT TO authenticated
    USING (
        user_id = auth.uid()
        OR event_id IN (SELECT event_id FROM event_attendees WHERE user_id = auth.uid())
    );

CREATE POLICY "event_attendees_insert" ON event_attendees
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "event_attendees_update" ON event_attendees
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid());

-- connections: read/write own connections only
CREATE POLICY "connections_select" ON connections
    FOR SELECT TO authenticated
    USING (user_a_id = auth.uid() OR user_b_id = auth.uid());

CREATE POLICY "connections_insert" ON connections
    FOR INSERT TO authenticated
    WITH CHECK (user_a_id = auth.uid() OR user_b_id = auth.uid());

CREATE POLICY "connections_update" ON connections
    FOR UPDATE TO authenticated
    USING (user_a_id = auth.uid() OR user_b_id = auth.uid());

-- icebreaker_cache: read if you're one of the pair
CREATE POLICY "icebreaker_select" ON icebreaker_cache
    FOR SELECT TO authenticated
    USING (user_a_id = auth.uid() OR user_b_id = auth.uid());

-- scores: read if you're in the event
CREATE POLICY "scores_select" ON event_attendee_scores
    FOR SELECT TO authenticated
    USING (
        event_id IN (SELECT event_id FROM event_attendees WHERE user_id = auth.uid())
    );

CREATE POLICY "similarity_select" ON profile_similarity
    FOR SELECT TO authenticated
    USING (user_a_id = auth.uid() OR user_b_id = auth.uid());

-- ============================================================
-- HELPER FUNCTION: resolve canonical pair order
-- Use in application code before any insert to similarity/connections/icebreaker
-- ============================================================
CREATE OR REPLACE FUNCTION canonical_pair(a UUID, b UUID)
RETURNS TABLE(user_a UUID, user_b UUID) AS $$
BEGIN
    IF a < b THEN
        RETURN QUERY SELECT a, b;
    ELSE
        RETURN QUERY SELECT b, a;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
