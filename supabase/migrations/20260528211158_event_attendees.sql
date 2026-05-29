CREATE TABLE event_attendees (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    referred_by     UUID REFERENCES profiles(id) ON DELETE SET NULL,

    agenda          TEXT,

    privacy_overrides JSONB,

    event_embedding vector(768),

    is_visible      BOOLEAN NOT NULL DEFAULT TRUE,

    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(event_id, user_id)
);

CREATE INDEX idx_event_attendees_event ON event_attendees(event_id);
CREATE INDEX idx_event_attendees_user ON event_attendees(user_id);
CREATE INDEX idx_event_attendees_event_embedding ON event_attendees
    USING hnsw (event_embedding vector_cosine_ops);
