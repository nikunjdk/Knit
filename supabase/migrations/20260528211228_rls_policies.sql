ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE icebreaker_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_attendee_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_similarity ENABLE ROW LEVEL SECURITY;

-- profiles: read own + co-attendees; write own only
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
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- Prevent users from directly changing their own id or email via PostgREST
REVOKE UPDATE (id, email) ON profiles FROM authenticated;

-- events: read if organizer or attendee; insert/update if organizer
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
    USING (organizer_id = auth.uid())
    WITH CHECK (organizer_id = auth.uid());

-- digest_generation_count must only be incremented via increment_digest_count() SECURITY DEFINER
REVOKE UPDATE (digest_generation_count) ON events FROM authenticated;

-- event_attendees: read co-attendees in same event; write own row
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
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Users may only edit agenda/privacy/visibility — not their identity or which event they're in
REVOKE UPDATE (event_id, user_id, referred_by) ON event_attendees FROM authenticated;

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
