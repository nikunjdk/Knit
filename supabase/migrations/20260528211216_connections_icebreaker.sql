-- Mark-as-met. user_a_id < user_b_id enforced.
CREATE TABLE connections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_a_id   UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id   UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,

    notes_a     TEXT,
    notes_b     TEXT,

    met_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(event_id, user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);

CREATE INDEX idx_connections_event_a ON connections(event_id, user_a_id);
CREATE INDEX idx_connections_event_b ON connections(event_id, user_b_id);

-- Durable icebreaker cache. Redis is warm cache only.
-- user_a_id < user_b_id enforced.
CREATE TABLE icebreaker_cache (
    event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_a_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    user_b_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (event_id, user_a_id, user_b_id),
    CONSTRAINT user_a_lt_b CHECK (user_a_id < user_b_id)
);
