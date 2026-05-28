CREATE TABLE events (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizer_id                UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,

    title                       TEXT NOT NULL,
    description                 TEXT,
    location                    TEXT,

    start_date                  DATE NOT NULL,
    end_date                    DATE NOT NULL,
    start_time                  TIME,
    end_time                    TIME,

    join_code                   TEXT NOT NULL UNIQUE,
    agenda                      TEXT,

    sharing_checklist           JSONB NOT NULL DEFAULT '{}',

    digest_generation_count     INT NOT NULL DEFAULT 0 CHECK (digest_generation_count <= 3),

    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT end_date_gte_start CHECK (end_date >= start_date)
);

CREATE INDEX idx_events_organizer ON events(organizer_id);
CREATE INDEX idx_events_join_code ON events(join_code);
