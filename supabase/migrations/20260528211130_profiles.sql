CREATE TABLE profiles (
    id                  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name           TEXT NOT NULL,
    avatar_url          TEXT,
    email               TEXT NOT NULL,
    email_opt_in        BOOLEAN NOT NULL DEFAULT TRUE,

    role                TEXT,
    company             TEXT,
    linkedin_url        TEXT,

    interests           TEXT[] NOT NULL DEFAULT '{}' CHECK (array_length(interests, 1) <= 5),

    profile_embedding   vector(768),

    default_privacy     JSONB NOT NULL DEFAULT '{"role": true, "company": true, "linkedin_url": false, "interests": true}',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_profile_embedding ON profiles
    USING hnsw (profile_embedding vector_cosine_ops);
