-- Cross-event profile similarity (computed from profile_embedding only)
-- user_a_id < user_b_id enforced — one row per unique pair
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

-- Event-specific relevance scores (blends profile + agenda embeddings)
-- user_a_id < user_b_id enforced
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
